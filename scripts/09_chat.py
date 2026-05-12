from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from rag_common import ensure_runtime_dirs, load_config, resolve_work_path
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

REFUSAL_OUT_OF_SCOPE = "out_of_scope_or_no_relevant_sources"
REFUSAL_SENSITIVE = "sensitive_or_system_request"
REFUSAL_NO_INDEX = "rag_index_not_found"
REFUSAL_LLM_ERROR = "llm_error"

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


def ollama_generate(
    base_url: str,
    model: str,
    prompt: str,
    temperature: float,
    top_p: float,
    num_predict: int,
    timeout: int,
) -> str:
    resp = requests.post(
        f"{base_url.rstrip('/')}/api/generate",
        json={
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "top_p": top_p,
                "num_predict": num_predict,
            },
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json().get("response", "").strip()


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


def source_id(idx: int) -> str:
    return f"SRC-{idx:03d}"


def normalize_source(ctx: dict[str, Any], idx: int) -> dict[str, Any]:
    meta = dict(ctx.get("metadata", {}))
    score = float(ctx.get("score", 1.0 - float(ctx.get("distance", 1.0))))
    return {
        "source_id": source_id(idx),
        "score": score,
        "relative_path": meta.get("relative_path"),
        "chunk_index": meta.get("chunk_index"),
        "chunk_id": meta.get("chunk_id"),
        "chars": meta.get("chars"),
        "preview": preview_text(str(ctx.get("document", ""))),
    }


def build_sources_block(contexts: list[dict[str, Any]], source_char_limit: int) -> str:
    blocks: list[str] = []
    for idx, ctx in enumerate(contexts, start=1):
        meta = ctx.get("metadata", {})
        score = float(ctx.get("score", 1.0 - float(ctx.get("distance", 1.0))))
        blocks.append(
            "\n".join(
                [
                    f"[{source_id(idx)}]",
                    f"Файл: {meta.get('relative_path')}",
                    f"Chunk: {meta.get('chunk_index')}",
                    f"Score: {score:.4f}",
                    "Фрагмент:",
                    compact_document(str(ctx.get("document", "")), source_char_limit),
                ]
            )
        )
    return "\n\n---\n\n".join(blocks)


def build_answer_prompt(question: str, contexts: list[dict[str, Any]], prompt_template: str, source_char_limit: int) -> str:
    return prompt_template.replace("{question}", question).replace("{sources}", build_sources_block(contexts, source_char_limit))


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
            print(
                f"- [{src['source_id']}] score={float(src['score']):.4f} "
                f"file={src.get('relative_path')} chunk={src.get('chunk_index')}"
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
    args = parser.parse_args()

    question = " ".join(args.question).strip()
    if not question:
        result = refusal_response(question, REFUSAL_OUT_OF_SCOPE, "Вопрос пустой. Сформулируйте вопрос по проектным материалам.")
        output_result(result, args.json)
        return

    cfg = load_config()
    ensure_runtime_dirs(cfg)

    if is_sensitive_question(question):
        result = refusal_response(
            question,
            REFUSAL_SENSITIVE,
            "Я отвечаю только по проектным материалам и не раскрываю системные инструкции, секреты или локальные конфигурации.",
        )
        output_result(result, args.json)
        return

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
    accepted_contexts = trim_contexts(accepted_contexts, args.max_context_chars)
    sources = [normalize_source(ctx, idx) for idx, ctx in enumerate(accepted_contexts, start=1)]

    if not accepted_contexts:
        candidate_sources = [normalize_source(ctx, idx) for idx, ctx in enumerate(found_contexts[: min(3, len(found_contexts))], start=1)]
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
        result = answer_response(question, "LLM не вызывалась: показаны найденные проектные источники.", sources, args.score_threshold)
        output_result(result, args.json)
        return

    try:
        prompt_template = read_prompt_template(prompt_path)
        prompt = build_answer_prompt(question, accepted_contexts, prompt_template, args.source_char_limit)
        answer = ollama_generate(base_url, chat_model, prompt, temperature, top_p, args.num_predict, args.timeout_sec)
    except Exception as exc:  # noqa: BLE001 - CLI should return structured error for MVP usage.
        result = refusal_response(
            question,
            REFUSAL_LLM_ERROR,
            "Не удалось получить ответ от локальной LLM. Найденные источники сохранены в ответе.",
            sources=sources,
            details=str(exc),
        )
        output_result(result, args.json)
        return

    result = answer_response(question, answer, sources, args.score_threshold)
    output_result(result, args.json)


if __name__ == "__main__":
    main()
