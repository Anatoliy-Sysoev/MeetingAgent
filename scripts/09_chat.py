from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from rag_common import ensure_runtime_dirs, jsonl_read, load_config, resolve_work_path
from rag_numpy_backend import index_exists, load_index


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


DEFAULT_PROMPT_PATH = "configs/prompts/project_only_chat.md"
DEFAULT_SCORE_THRESHOLD = 0.35
DEFAULT_MIN_SOURCES = 1
DEFAULT_TOP_K = 4
DEFAULT_MAX_CONTEXT_CHARS = 6000
DEFAULT_NUM_PREDICT = 700
DEFAULT_TIMEOUT_SEC = 180
DEFAULT_DOCUMENT_EXPANSION_CHUNKS = 6
DEFAULT_EXPAND_TOP_DOCUMENTS = 1

REFUSAL_OUT_OF_SCOPE = "out_of_scope_or_no_relevant_sources"
REFUSAL_OBVIOUSLY_OUT_OF_SCOPE = "obviously_out_of_project_scope"
REFUSAL_SENSITIVE = "sensitive_or_system_request"
REFUSAL_NO_INDEX = "rag_index_not_found"
REFUSAL_LLM_ERROR = "llm_error"
REFUSAL_LLM_EMPTY = "llm_empty_response"

SENSITIVE_PATTERNS = (
    ".env",
    "config.yaml",
    "пароль",
    "пароли",
    "password",
    "token",
    "токен",
    "secret",
    "секрет",
    "system prompt",
    "системный промпт",
    "инструкции модели",
    "developer message",
    "api key",
    "ключ api",
)

OBVIOUS_OUT_OF_SCOPE_PATTERNS = (
    r"\bпогод[аеуы]\b",
    r"\bпрогноз\s+погоды\b",
    r"\bкурс\s+(доллар|доллара|евро|валют)",
    r"\bдоллар\b",
    r"\bбиткоин\b",
    r"\bbitcoin\b",
    r"\bрецепт\b",
    r"\bприготов(ить|ление)\b",
    r"\bборщ\b",
    r"\bновост[ьи]\b",
    r"\bкто\s+такой\s+наполеон\b",
)

PROJECT_HINT_PATTERNS = (
    r"\bпроект\b",
    r"\bцп\s*упкс\b",
    r"\bноватэк\b",
    r"\bпаспорт\s+ис\b",
    r"\bфтт\b",
    r"\bцта\b",
    r"\bпми\b",
    r"\bинтеграц",
    r"\bmdr\b",
    r"\bad\b",
    r"\bblitz\b",
    r"\bсием\b",
    r"\bsiem\b",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ollama_embed(base_url: str, model: str, text: str, num_ctx: int = 8192, keep_alive: str = "24h") -> list[float]:
    resp = requests.post(
        f"{base_url.rstrip('/')}/api/embeddings",
        json={
            "model": model,
            "prompt": text,
            "keep_alive": keep_alive,
            "options": {"num_ctx": num_ctx},
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["embedding"]


def normalize_llm_answer(raw: str) -> str:
    """Remove model-internal thinking blocks and normalize whitespace."""
    text = raw or ""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"^Thinking\.\.\..*?\.\.\.done thinking\.\s*", "", text, flags=re.IGNORECASE | re.DOTALL)
    return text.strip()


def ollama_chat(
    base_url: str,
    model: str,
    prompt: str,
    temperature: float,
    top_p: float,
    num_predict: int,
    timeout: int,
    think: bool = False,
) -> str:
    """Call Ollama chat API.

    Qwen 3 is a thinking-capable model. The CLI may still print thinking by default;
    the application path must disable it via top-level `think: false`.
    """
    resp = requests.post(
        f"{base_url.rstrip('/')}/api/chat",
        json={
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Ты ProjectBot. Отвечай только по переданным проектным источникам. "
                        "Не используй общие знания. Если данных недостаточно — откажись. "
                        "Не выводи рассуждения, chain-of-thought или внутренний анализ."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "think": think,
            "options": {
                "temperature": temperature,
                "top_p": top_p,
                "num_predict": num_predict,
            },
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    payload = resp.json()
    message = payload.get("message") or {}
    return normalize_llm_answer(message.get("content") or payload.get("response") or "")


def preview_text(text: str, limit: int = 280) -> str:
    normalized = " ".join(str(text).split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def compact_document(text: str, limit: int = 1800) -> str:
    normalized = " ".join(str(text).split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def read_prompt_template(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    return path.read_text(encoding="utf-8")


def is_sensitive_question(question: str) -> bool:
    lowered = question.lower()
    return any(pattern.lower() in lowered for pattern in SENSITIVE_PATTERNS)


def has_project_hint(question: str) -> bool:
    lowered = question.lower()
    return any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in PROJECT_HINT_PATTERNS)


def is_obviously_out_of_scope_question(question: str) -> bool:
    lowered = question.lower()
    if has_project_hint(lowered):
        return False
    return any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in OBVIOUS_OUT_OF_SCOPE_PATTERNS)


def source_id(idx: int) -> str:
    return f"SRC-{idx:03d}"


def load_source_links(cfg: dict[str, Any]) -> dict[str, str]:
    raw_path = cfg.get("paths", {}).get("source_links", "data/source_links.json")
    path = resolve_work_path(cfg, raw_path)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    links: dict[str, str] = {}
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, str):
                links[str(key)] = value
            elif isinstance(value, dict) and isinstance(value.get("url"), str):
                links[str(key)] = value["url"]
    return links


def normalize_source(ctx: dict[str, Any], idx: int, source_links: dict[str, str] | None = None) -> dict[str, Any]:
    meta = dict(ctx.get("metadata", {}))
    relative_path = meta.get("relative_path")
    score = float(ctx.get("score", 1.0 - float(ctx.get("distance", 1.0))))
    source = {
        "source_id": source_id(idx),
        "score": score,
        "relative_path": relative_path,
        "chunk_index": meta.get("chunk_index"),
        "chunk_id": meta.get("chunk_id"),
        "chars": meta.get("chars"),
        "preview": preview_text(str(ctx.get("document", ""))),
    }
    if source_links and relative_path in source_links:
        source["source_url"] = source_links[relative_path]
    if meta.get("retrieval"):
        source["retrieval"] = meta.get("retrieval")
    if meta.get("expanded_from_chunk_index") is not None:
        source["expanded_from_chunk_index"] = meta.get("expanded_from_chunk_index")
    return source


def build_sources_block(contexts: list[dict[str, Any]], source_char_limit: int, source_links: dict[str, str] | None = None) -> str:
    blocks: list[str] = []
    for idx, ctx in enumerate(contexts, start=1):
        meta = ctx.get("metadata", {})
        relative_path = meta.get("relative_path")
        score = float(ctx.get("score", 1.0 - float(ctx.get("distance", 1.0))))
        retrieval = meta.get("retrieval", "vector_search")
        lines = [
            f"[{source_id(idx)}]",
            f"Файл: {relative_path}",
            f"Chunk: {meta.get('chunk_index')}",
            f"Retrieval: {retrieval}",
            f"Score: {score:.4f}",
        ]
        if source_links and relative_path in source_links:
            lines.append(f"Ссылка: {source_links[relative_path]}")
        lines.extend(
            [
                "Фрагмент:",
                compact_document(str(ctx.get("document", "")), source_char_limit),
            ]
        )
        blocks.append("\n".join(lines))
    return "\n\n---\n\n".join(blocks)


def build_answer_prompt(
    question: str,
    contexts: list[dict[str, Any]],
    prompt_template: str,
    source_char_limit: int,
    source_links: dict[str, str] | None = None,
) -> str:
    return prompt_template.replace("{question}", question).replace(
        "{sources}", build_sources_block(contexts, source_char_limit, source_links)
    )


def confidence_from_sources(sources: list[dict[str, Any]], threshold: float) -> float:
    if not sources:
        return 0.0
    top_score = max(float(src.get("score", 0.0)) for src in sources)
    if top_score <= 0:
        return 0.0
    return round(min(1.0, top_score / max(threshold, 1e-6)), 4)


def refusal_response(
    question: str,
    refusal_reason: str,
    message: str,
    sources: list[dict[str, Any]] | None = None,
    details: str | None = None,
) -> dict[str, Any]:
    return {
        "created_at": utc_now(),
        "query": question,
        "status": "refused",
        "answer": message,
        "sources": sources or [],
        "refusal_reason": refusal_reason,
        "confidence": 0.0,
        "details": details,
    }


def answer_response(question: str, answer: str, sources: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    return {
        "created_at": utc_now(),
        "query": question,
        "status": "answered",
        "answer": answer,
        "sources": sources,
        "refusal_reason": None,
        "confidence": confidence_from_sources(sources, threshold),
    }


def filter_contexts_by_score(contexts: list[dict[str, Any]], threshold: float, min_sources: int) -> list[dict[str, Any]]:
    accepted = [ctx for ctx in contexts if float(ctx.get("score", 0.0)) >= threshold]
    if len(accepted) >= min_sources:
        return accepted
    return []


def query_contexts(
    cfg: dict[str, Any],
    question: str,
    top_k: int,
    include_excluded: bool,
    no_dedupe: bool,
) -> list[dict[str, Any]]:
    base_url = cfg["ollama"]["base_url"]
    embedding_model = cfg["ollama"]["embedding_model"]
    embedding_num_ctx = int(cfg["ollama"].get("embedding_num_ctx", 8192))
    keep_alive = str(cfg["ollama"].get("keep_alive", "24h"))
    numpy_index_path = resolve_work_path(cfg, cfg["paths"].get("numpy_index", "data/numpy_index"))

    if not index_exists(numpy_index_path):
        raise FileNotFoundError(f"Numpy RAG index not found: {numpy_index_path}")

    exclude_path_patterns = [] if include_excluded else list(cfg.get("exclude_path_patterns", []))
    dedupe_by_chunk_id = not no_dedupe
    query_embedding = ollama_embed(base_url, embedding_model, question, embedding_num_ctx, keep_alive)
    index = load_index(numpy_index_path)
    return index.query(
        query_embedding,
        top_k,
        exclude_path_patterns=exclude_path_patterns,
        dedupe_by_chunk_id=dedupe_by_chunk_id,
    )


def chunk_row_to_context(row: dict[str, Any], parent_score: float, parent_chunk_index: int) -> dict[str, Any]:
    meta = {
        "chunk_id": row.get("chunk_id"),
        "db_id": row.get("db_id"),
        "source_path": row.get("source_path"),
        "relative_path": row.get("relative_path"),
        "extension": row.get("extension"),
        "sha256": row.get("sha256"),
        "mtime": float(row.get("mtime", 0.0)),
        "chunk_index": int(row.get("chunk_index", 0)),
        "chars": int(row.get("chars", len(str(row.get("text", ""))))),
        "retrieval": "document_expansion",
        "expanded_from_chunk_index": parent_chunk_index,
    }
    return {
        "document": row.get("text", ""),
        "metadata": meta,
        "distance": float(1.0 - parent_score),
        "score": parent_score,
    }


def load_document_chunks(cfg: dict[str, Any], relative_path: str) -> list[dict[str, Any]]:
    chunks_path = resolve_work_path(cfg, cfg["paths"].get("chunks", "data/chunks.jsonl"))
    rows = [row for row in jsonl_read(chunks_path) if row.get("relative_path") == relative_path]
    rows.sort(key=lambda row: int(row.get("chunk_index", 0)))
    return rows


def expand_contexts_by_document(
    cfg: dict[str, Any],
    contexts: list[dict[str, Any]],
    expand_top_documents: int,
    document_expansion_chunks: int,
) -> list[dict[str, Any]]:
    if expand_top_documents <= 0 or document_expansion_chunks <= 0 or not contexts:
        return contexts

    selected_docs: list[tuple[str, int, float]] = []
    seen_docs: set[str] = set()
    for ctx in contexts:
        meta = ctx.get("metadata", {})
        relative_path = str(meta.get("relative_path") or "")
        if not relative_path or relative_path in seen_docs:
            continue
        seen_docs.add(relative_path)
        selected_docs.append(
            (
                relative_path,
                int(meta.get("chunk_index", 0)),
                float(ctx.get("score", 0.0)),
            )
        )
        if len(selected_docs) >= expand_top_documents:
            break

    expanded: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, int]] = set()

    for relative_path, parent_chunk_index, parent_score in selected_docs:
        rows = load_document_chunks(cfg, relative_path)
        if not rows:
            continue

        chunk_indices = [int(row.get("chunk_index", 0)) for row in rows]
        if parent_chunk_index <= min(chunk_indices, default=0):
            selected_rows = rows[:document_expansion_chunks]
        else:
            half_window = max(1, document_expansion_chunks // 2)
            start = max(0, parent_chunk_index - half_window)
            end = parent_chunk_index + half_window + 1
            selected_rows = [row for row in rows if start <= int(row.get("chunk_index", 0)) < end]
            selected_rows = selected_rows[:document_expansion_chunks]

        for row in selected_rows:
            key = (str(row.get("relative_path")), int(row.get("chunk_index", 0)))
            if key in seen_keys:
                continue
            seen_keys.add(key)
            expanded.append(chunk_row_to_context(row, parent_score, parent_chunk_index))

    for ctx in contexts:
        meta = ctx.get("metadata", {})
        key = (str(meta.get("relative_path")), int(meta.get("chunk_index", 0)))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        expanded.append(ctx)

    return expanded or contexts


def trim_contexts(contexts: list[dict[str, Any]], max_context_chars: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    used_chars = 0
    for ctx in contexts:
        doc = str(ctx.get("document", ""))
        if selected and used_chars + len(doc) > max_context_chars:
            break
        selected.append(ctx)
        used_chars += len(doc)
    return selected


def print_human(result: dict[str, Any]) -> None:
    print(result["answer"])
    print()
    print(f"Статус: {result['status']}")
    if result.get("refusal_reason"):
        print(f"Причина отказа: {result['refusal_reason']}")
    print(f"Уверенность: {result.get('confidence', 0.0)}")
    if result.get("sources"):
        print("\nИсточники:")
        for src in result["sources"]:
            retrieval = f" retrieval={src.get('retrieval')}" if src.get("retrieval") else ""
            url = f" url={src.get('source_url')}" if src.get("source_url") else ""
            print(
                f"- [{src['source_id']}] score={float(src['score']):.4f} "
                f"file={src.get('relative_path')} chunk={src.get('chunk_index')}{retrieval}{url}"
            )
            print(f"  {src.get('preview')}")


def output_result(result: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_human(result)


def main() -> None:
    parser = argparse.ArgumentParser(description="Project-only чат-бот MeetingAgent поверх локального RAG")
    parser.add_argument("question", nargs="+", help="Вопрос к проектной базе знаний")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help="Сколько chunks искать до фильтрации")
    parser.add_argument("--score-threshold", type=float, default=DEFAULT_SCORE_THRESHOLD, help="Минимальный score источника")
    parser.add_argument("--min-sources", type=int, default=DEFAULT_MIN_SOURCES, help="Минимальное число источников выше порога")
    parser.add_argument("--max-context-chars", type=int, default=DEFAULT_MAX_CONTEXT_CHARS, help="Максимальный размер контекста для LLM")
    parser.add_argument("--source-char-limit", type=int, default=1800, help="Максимум символов одного источника в prompt")
    parser.add_argument("--document-expansion-chunks", type=int, default=DEFAULT_DOCUMENT_EXPANSION_CHUNKS, help="Сколько chunks брать из top-документа для LLM-контекста")
    parser.add_argument("--expand-top-documents", type=int, default=DEFAULT_EXPAND_TOP_DOCUMENTS, help="Сколько top-документов расширять соседними chunks")
    parser.add_argument("--no-document-expansion", action="store_true", help="Отключить расширение контекста по top-документу")
    parser.add_argument("--model", default=None, help="Ollama model для генерации ответа")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT_PATH, help="Путь к prompt-шаблону")
    parser.add_argument("--temperature", type=float, default=None, help="Температура генерации")
    parser.add_argument("--top-p", type=float, default=None, help="top_p генерации")
    parser.add_argument("--num-predict", type=int, default=DEFAULT_NUM_PREDICT, help="Ограничение длины ответа Ollama")
    parser.add_argument("--timeout-sec", type=int, default=DEFAULT_TIMEOUT_SEC, help="Timeout LLM-вызова")
    parser.add_argument("--json", action="store_true", help="Вывести полный JSON-ответ")
    parser.add_argument("--sources-only", action="store_true", help="Не вызывать LLM, показать только найденные источники/отказ")
    parser.add_argument("--include-excluded", action="store_true", help="Не применять query-фильтр служебных и архивных путей")
    parser.add_argument("--no-dedupe", action="store_true", help="Не дедуплицировать одинаковые chunks по тексту")
    parser.add_argument("--think", action="store_true", help="Разрешить thinking-режим Ollama. По умолчанию выключен")
    args = parser.parse_args()

    question = " ".join(args.question).strip()
    if not question:
        result = refusal_response(question, REFUSAL_OUT_OF_SCOPE, "Вопрос пустой. Сформулируйте вопрос по проектным материалам.")
        output_result(result, args.json)
        return

    if is_sensitive_question(question):
        result = refusal_response(
            question,
            REFUSAL_SENSITIVE,
            "Я отвечаю только по проектным материалам и не раскрываю системные инструкции, секреты или локальные конфигурации.",
        )
        output_result(result, args.json)
        return

    if is_obviously_out_of_scope_question(question):
        result = refusal_response(
            question,
            REFUSAL_OBVIOUSLY_OUT_OF_SCOPE,
            "Этот вопрос не относится к текущему проекту. Я отвечаю только по проектной базе знаний и найденным источникам.",
        )
        output_result(result, args.json)
        return

    cfg = load_config()
    ensure_runtime_dirs(cfg)
    source_links = load_source_links(cfg)

    generation_cfg = cfg.get("generation", {})
    temperature = float(args.temperature if args.temperature is not None else generation_cfg.get("temperature", 0.1))
    top_p = float(args.top_p if args.top_p is not None else generation_cfg.get("top_p", 0.8))
    chat_model = args.model or cfg["ollama"]["chat_model"]
    base_url = cfg["ollama"]["base_url"]
    prompt_path = resolve_work_path(cfg, args.prompt)

    try:
        found_contexts = query_contexts(cfg, question, args.top_k, args.include_excluded, args.no_dedupe)
    except FileNotFoundError as exc:
        result = refusal_response(
            question,
            REFUSAL_NO_INDEX,
            "Локальный RAG-индекс не найден. Сначала соберите индекс проекта.",
            details=str(exc),
        )
        output_result(result, args.json)
        return

    accepted_contexts = filter_contexts_by_score(found_contexts, args.score_threshold, args.min_sources)
    raw_sources = [normalize_source(ctx, idx, source_links) for idx, ctx in enumerate(accepted_contexts, start=1)]

    if not accepted_contexts:
        candidate_sources = [
            normalize_source(ctx, idx, source_links) for idx, ctx in enumerate(found_contexts[: min(3, len(found_contexts))], start=1)
        ]
        result = refusal_response(
            question,
            REFUSAL_OUT_OF_SCOPE,
            "В проектных источниках не найдено подтверждение для ответа. Переформулируйте вопрос в рамках проектной документации.",
            sources=candidate_sources,
            details=f"min_sources={args.min_sources}, score_threshold={args.score_threshold}",
        )
        output_result(result, args.json)
        return

    if args.sources_only:
        result = answer_response(question, "LLM не вызывалась: показаны найденные проектные источники.", raw_sources, args.score_threshold)
        output_result(result, args.json)
        return

    llm_contexts = accepted_contexts
    if not args.no_document_expansion:
        llm_contexts = expand_contexts_by_document(
            cfg,
            accepted_contexts,
            args.expand_top_documents,
            args.document_expansion_chunks,
        )
    llm_contexts = trim_contexts(llm_contexts, args.max_context_chars)
    llm_sources = [normalize_source(ctx, idx, source_links) for idx, ctx in enumerate(llm_contexts, start=1)]

    try:
        prompt_template = read_prompt_template(prompt_path)
        prompt = build_answer_prompt(question, llm_contexts, prompt_template, args.source_char_limit, source_links)
        answer = ollama_chat(
            base_url,
            chat_model,
            prompt,
            temperature,
            top_p,
            args.num_predict,
            args.timeout_sec,
            think=args.think,
        )
    except Exception as exc:  # noqa: BLE001 - CLI should return structured error for MVP usage.
        result = refusal_response(
            question,
            REFUSAL_LLM_ERROR,
            "Не удалось получить ответ от локальной LLM. Найденные источники сохранены в ответе.",
            sources=llm_sources,
            details=str(exc),
        )
        output_result(result, args.json)
        return

    if not answer:
        result = refusal_response(
            question,
            REFUSAL_LLM_EMPTY,
            "Локальная LLM вернула пустой ответ. Найденные источники сохранены в ответе.",
            sources=llm_sources,
            details=f"model={chat_model}, num_predict={args.num_predict}, top_k={args.top_k}",
        )
        output_result(result, args.json)
        return

    result = answer_response(question, answer, llm_sources, args.score_threshold)
    output_result(result, args.json)


if __name__ == "__main__":
    main()
