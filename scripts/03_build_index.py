from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import requests
from tqdm import tqdm

from rag_common import FileLock, chunk_text, ensure_runtime_dirs, jsonl_read, jsonl_write, load_config, resolve_work_path, stable_id


def ollama_embed(base_url: str, model: str, text: str, num_ctx: int, keep_alive: str) -> list[float]:
    last_error: Exception | None = None
    max_attempts = 15
    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.post(
                f"{base_url.rstrip('/')}/api/embeddings",
                json={
                    "model": model,
                    "prompt": text,
                    "keep_alive": keep_alive,
                    "options": {
                        "num_ctx": num_ctx,
                    },
                },
                timeout=240,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["embedding"]
        except Exception as exc:
            last_error = exc
            response_text = ""
            if isinstance(exc, requests.HTTPError) and exc.response is not None:
                response_text = exc.response.text[:1000]
            wait_sec = min(180, 10 * attempt)
            print(
                f"Ollama embedding failed on attempt {attempt}/{max_attempts}: {exc}. "
                f"Response: {response_text!r}. Retry in {wait_sec}s",
                flush=True,
            )
            time.sleep(wait_sec)
    raise RuntimeError(f"Ollama embedding failed after retries: {last_error}") from last_error


def make_chunks(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    extracted_dir = resolve_work_path(cfg, cfg["paths"]["extracted_text_dir"])
    metadata_path = extracted_dir / "_metadata.jsonl"
    chunk_size = int(cfg["rag"]["chunk_size_chars"])
    overlap = int(cfg["rag"]["chunk_overlap_chars"])

    chunks = []
    for meta in jsonl_read(metadata_path):
        if meta.get("error"):
            continue
        extracted_path = Path(meta["extracted_path"])
        if not extracted_path.exists():
            continue
        text = extracted_path.read_text(encoding="utf-8", errors="replace")
        for index, chunk in enumerate(chunk_text(text, chunk_size, overlap)):
            chunk_id = stable_id(f"{meta['sha256']}:{index}:{chunk[:120]}")
            db_id = stable_id(f"{meta['relative_path']}:{meta['sha256']}:{index}:{chunk[:120]}")
            chunks.append(
                {
                    "chunk_id": chunk_id,
                    "db_id": db_id,
                    "text": chunk,
                    "source_path": meta["source_path"],
                    "relative_path": meta["relative_path"],
                    "extension": meta["extension"],
                    "sha256": meta["sha256"],
                    "mtime": meta["mtime"],
                    "chunk_index": index,
                    "chars": len(chunk),
                }
            )
    return chunks


def load_embedding_cache(path: Path, expected_model: str) -> dict[str, dict[str, Any]]:
    cache: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return cache
    with path.open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("embedding_model") != expected_model:
                continue
            chunk_id = rec.get("chunk_id")
            embedding = rec.get("embedding")
            if chunk_id and isinstance(embedding, list):
                cache[chunk_id] = rec
    return cache


def append_embedding_cache(path: Path, rec: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fp:
        fp.write(json.dumps(rec, ensure_ascii=False) + "\n")


def main() -> None:
    cfg = load_config()
    ensure_runtime_dirs(cfg)

    lock_path = resolve_work_path(cfg, "logs/build_index.lock")
    chunks_path = resolve_work_path(cfg, cfg["paths"]["chunks"])
    embeddings_cache_path = resolve_work_path(cfg, cfg["paths"].get("embeddings_cache", "data/embeddings_cache.jsonl"))
    base_url = cfg["ollama"]["base_url"]
    embedding_model = cfg["ollama"]["embedding_model"]
    embedding_num_ctx = int(cfg["ollama"].get("embedding_num_ctx", 8192))
    keep_alive = str(cfg["ollama"].get("keep_alive", "24h"))

    with FileLock(lock_path):
        chunks = make_chunks(cfg)
        jsonl_write(chunks_path, chunks)

        embedding_cache = load_embedding_cache(embeddings_cache_path, embedding_model)
        chunk_ids = {chunk["chunk_id"] for chunk in chunks}
        stale_count = len([chunk_id for chunk_id in embedding_cache if chunk_id not in chunk_ids])
        print(
            json.dumps(
                {
                    "chunks": len(chunks),
                    "cached_embeddings": len([chunk_id for chunk_id in chunk_ids if chunk_id in embedding_cache]),
                    "stale_cached_embeddings": stale_count,
                    "embedding_cache": str(embeddings_cache_path),
                    "embedding_num_ctx": embedding_num_ctx,
                    "chunk_size_chars": int(cfg["rag"]["chunk_size_chars"]),
                },
                ensure_ascii=False,
                indent=2,
            ),
            flush=True,
        )

        for chunk in tqdm(chunks, desc="Embedding cache", unit="chunk"):
            if chunk["chunk_id"] in embedding_cache:
                continue
            emb = ollama_embed(base_url, embedding_model, chunk["text"], embedding_num_ctx, keep_alive)
            rec = {
                "chunk_id": chunk["chunk_id"],
                "embedding_model": embedding_model,
                "embedding": emb,
                "source_path": chunk["source_path"],
                "relative_path": chunk["relative_path"],
                "extension": chunk["extension"],
                "sha256": chunk["sha256"],
                "mtime": chunk["mtime"],
                "chunk_index": chunk["chunk_index"],
                "chars": chunk["chars"],
            }
            append_embedding_cache(embeddings_cache_path, rec)
            embedding_cache[chunk["chunk_id"]] = rec

        print(
            json.dumps(
                {
                    "chunks": len(chunks),
                    "chunks_path": str(chunks_path),
                    "embeddings_cache": str(embeddings_cache_path),
                    "embedding_model": embedding_model,
                    "next_step": "Запустите scripts/05_build_numpy_index.py для пересборки локального numpy-индекса.",
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
