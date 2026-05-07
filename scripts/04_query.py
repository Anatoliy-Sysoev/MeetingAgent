from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import requests

from rag_common import ensure_runtime_dirs, is_excluded_by_path_patterns, jsonl_read, load_config, resolve_work_path, stable_id
from rag_numpy_backend import index_exists, load_index


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


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


def ollama_chat(base_url: str, model: str, prompt: str, temperature: float, top_p: float) -> str:
    resp = requests.post(
        f"{base_url.rstrip('/')}/api/generate",
        json={
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "top_p": top_p,
            },
        },
        timeout=300,
    )
    resp.raise_for_status()
    return resp.json().get("response", "").strip()


def build_prompt(question: str, contexts: list[dict[str, Any]]) -> str:
    blocks = []
    for i, ctx in enumerate(contexts, start=1):
        meta = ctx["metadata"]
        blocks.append(
            "\n".join(
                [
                    f"[Источник {i}]",
                    f"Файл: {meta.get('relative_path')}",
                    f"Chunk: {meta.get('chunk_index')}",
                    ctx["document"],
                ]
            )
        )

    context_text = "\n\n---\n\n".join(blocks)
    return f"""Ты локальный RAG-ассистент по проекту АСУ.

Отвечай только по предоставленным источникам. Если данных недостаточно, прямо скажи, что в найденных фрагментах недостаточно информации.
В конце добавь раздел "Источники" со списком использованных файлов.

Вопрос:
{question}

Найденные фрагменты:
{context_text}
"""


def load_embedding_cache(path: Path, expected_model: str, chunk_ids: set[str]) -> dict[str, list[float]]:
    cache: dict[str, list[float]] = {}
    for rec in jsonl_read(path):
        if rec.get("embedding_model") != expected_model:
            continue
        chunk_id = rec.get("chunk_id")
        embedding = rec.get("embedding")
        if chunk_id in chunk_ids and isinstance(embedding, list):
            cache[chunk_id] = embedding
    return cache


def query_from_jsonl_cache(
    chunks_path: Path,
    embeddings_cache_path: Path,
    embedding_model: str,
    query_embedding: list[float],
    top_k: int,
    exclude_path_patterns: list[str] | None = None,
    dedupe_by_chunk_id: bool = True,
) -> list[dict[str, Any]]:
    exclude_path_patterns = exclude_path_patterns or []
    chunks = list(jsonl_read(chunks_path))
    chunk_ids = {chunk["chunk_id"] for chunk in chunks}
    embedding_cache = load_embedding_cache(embeddings_cache_path, embedding_model, chunk_ids)

    rows: list[dict[str, Any]] = []
    embeddings: list[list[float]] = []
    for chunk in chunks:
        embedding = embedding_cache.get(chunk["chunk_id"])
        if embedding is None:
            continue
        rows.append(chunk)
        embeddings.append(embedding)

    if not rows:
        raise RuntimeError("No current chunk embeddings found in embeddings cache")

    matrix = np.asarray(embeddings, dtype=np.float32)
    query = np.asarray(query_embedding, dtype=np.float32)
    matrix_norms = np.linalg.norm(matrix, axis=1)
    query_norm = np.linalg.norm(query)
    scores = matrix @ query / np.maximum(matrix_norms * query_norm, 1e-12)
    top_indices = np.argsort(-scores)
    duplicate_counts: dict[str, int] = {}

    if dedupe_by_chunk_id:
        for chunk in rows:
            if is_excluded_by_path_patterns(str(chunk.get("relative_path", "")), exclude_path_patterns):
                continue
            dedupe_key = stable_id(str(chunk.get("text", "")))
            duplicate_counts[dedupe_key] = duplicate_counts.get(dedupe_key, 0) + 1

    contexts = []
    seen_dedupe_keys: set[str] = set()
    for idx in top_indices:
        chunk = rows[int(idx)]
        if is_excluded_by_path_patterns(str(chunk.get("relative_path", "")), exclude_path_patterns):
            continue
        metadata = {
            "chunk_id": chunk["chunk_id"],
            "source_path": chunk["source_path"],
            "relative_path": chunk["relative_path"],
            "extension": chunk["extension"],
            "sha256": chunk["sha256"],
            "mtime": float(chunk["mtime"]),
            "chunk_index": int(chunk["chunk_index"]),
            "chars": int(chunk["chars"]),
        }
        if dedupe_by_chunk_id:
            dedupe_key = stable_id(str(chunk.get("text", "")))
            if dedupe_key in seen_dedupe_keys:
                continue
            seen_dedupe_keys.add(dedupe_key)
            duplicate_count = duplicate_counts.get(dedupe_key, 1) - 1
            if duplicate_count > 0:
                metadata["duplicate_count"] = duplicate_count
        contexts.append(
            {
                "document": chunk["text"],
                "metadata": metadata,
                "distance": float(1.0 - scores[int(idx)]),
                "score": float(scores[int(idx)]),
            }
        )
        if len(contexts) >= top_k:
            break
    return contexts


def preview_text(text: str, limit: int = 220) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def print_compact_contexts(contexts: list[dict[str, Any]]) -> None:
    for i, ctx in enumerate(contexts, start=1):
        meta = ctx["metadata"]
        score = float(ctx.get("score", 1.0 - float(ctx.get("distance", 1.0))))
        distance = float(ctx.get("distance", 1.0 - score))
        duplicates = int(meta.get("duplicate_count", 0) or 0)
        duplicate_suffix = f" duplicates=+{duplicates}" if duplicates else ""
        print(
            f"[{i}] score={score:.4f} distance={distance:.4f} "
            f"file={meta.get('relative_path')} chunk={meta.get('chunk_index')} chars={meta.get('chars')}{duplicate_suffix}"
        )
        print(f"    {preview_text(ctx['document'])}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Запрос к локальному RAG-индексу проекта АСУ")
    parser.add_argument("question", nargs="+", help="Вопрос к RAG-индексу")
    parser.add_argument("--top-k", type=int, default=None, help="Сколько chunks искать")
    parser.add_argument("--raw", action="store_true", help="Показать найденные chunks в JSON без LLM-ответа")
    parser.add_argument("--compact", action="store_true", help="Показать компактный список найденных источников без LLM-ответа")
    parser.add_argument("--include-excluded", action="store_true", help="Не применять query-фильтр служебных и архивных путей")
    parser.add_argument("--no-dedupe", action="store_true", help="Не дедуплицировать одинаковые chunks по тексту")
    args = parser.parse_args()

    question = " ".join(args.question).strip()
    cfg = load_config()
    ensure_runtime_dirs(cfg)

    base_url = cfg["ollama"]["base_url"]
    embedding_model = cfg["ollama"]["embedding_model"]
    embedding_num_ctx = int(cfg["ollama"].get("embedding_num_ctx", 8192))
    keep_alive = str(cfg["ollama"].get("keep_alive", "24h"))
    chat_model = cfg["ollama"]["chat_model"]
    generation_cfg = cfg.get("generation", {})
    temperature = float(generation_cfg.get("temperature", 0.2))
    top_p = float(generation_cfg.get("top_p", 0.9))
    chunks_path = resolve_work_path(cfg, cfg["paths"]["chunks"])
    embeddings_cache_path = resolve_work_path(cfg, cfg["paths"].get("embeddings_cache", "data/embeddings_cache.jsonl"))
    numpy_index_path = resolve_work_path(cfg, cfg["paths"].get("numpy_index", "data/numpy_index"))
    top_k = args.top_k or int(cfg["rag"]["top_k"])
    max_context_chars = int(cfg["rag"]["max_context_chars"])
    exclude_path_patterns = [] if args.include_excluded else list(cfg.get("exclude_path_patterns", []))
    dedupe_by_chunk_id = not args.no_dedupe

    query_embedding = ollama_embed(base_url, embedding_model, question, embedding_num_ctx, keep_alive)

    if index_exists(numpy_index_path):
        index = load_index(numpy_index_path)
        found_contexts = index.query(
            query_embedding,
            top_k,
            exclude_path_patterns=exclude_path_patterns,
            dedupe_by_chunk_id=dedupe_by_chunk_id,
        )
    else:
        print(f"ПРЕДУПРЕЖДЕНИЕ: numpy-индекс RAG не найден, используется JSONL-cache: {numpy_index_path}", flush=True)
        found_contexts = query_from_jsonl_cache(
            chunks_path,
            embeddings_cache_path,
            embedding_model,
            query_embedding,
            top_k,
            exclude_path_patterns=exclude_path_patterns,
            dedupe_by_chunk_id=dedupe_by_chunk_id,
        )

    contexts = []
    used_chars = 0
    for ctx in found_contexts:
        doc = ctx["document"]
        if used_chars + len(doc) > max_context_chars and contexts:
            break
        contexts.append(ctx)
        used_chars += len(doc)

    if args.raw:
        print(
            json.dumps(
                {
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "question": question,
                    "top_k": top_k,
                    "contexts": contexts,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    if args.compact:
        print_compact_contexts(contexts)
        return

    prompt = build_prompt(question, contexts)
    answer = ollama_chat(base_url, chat_model, prompt, temperature, top_p)
    print(answer)


if __name__ == "__main__":
    main()
