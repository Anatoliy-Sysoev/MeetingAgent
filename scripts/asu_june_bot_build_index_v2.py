from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import requests
from tqdm import tqdm


WORK_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = WORK_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from asu_june_bot.core.config import load_config, resolve_work_path  # noqa: E402


INDEX_VERSION = 2
EMBEDDINGS_FILE = "embeddings.npy"
METADATA_FILE = "metadata.jsonl"
MANIFEST_FILE = "manifest.json"
DEFAULT_CHUNKS_PATH = "data/asu_june_bot/chunks_v2.jsonl"
DEFAULT_EMBEDDINGS_CACHE = "data/asu_june_bot/embeddings_cache_v2.jsonl"
DEFAULT_INDEX_DIR = "data/asu_june_bot/numpy_index_v2"
DEFAULT_REPORT_PATH = "data/asu_june_bot/index_v2_report.json"
DEFAULT_MAX_EMBEDDING_CHARS = 3000
MIN_EMBEDDING_CHARS = 800
DEFAULT_INDEX_SOURCE_TYPES = ["project_doc", "meeting_artifact", "analytical_note", "instruction"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"JSONL file not found: {path}")
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fp:
        fp.write(json.dumps(row, ensure_ascii=False) + "\n")


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
                cache[str(chunk_id)] = rec
    return cache


def compact_embedding_text(text: str, max_chars: int) -> str:
    text = str(text or "").strip()
    if len(text) <= max_chars:
        return text
    head_size = max_chars // 2
    tail_size = max_chars - head_size
    return text[:head_size].rstrip() + "\n\n[...chunk truncated for embedding...]\n\n" + text[-tail_size:].lstrip()


def is_context_length_error(exc: Exception, response_text: str) -> bool:
    message = f"{exc} {response_text}".lower()
    return "input length exceeds" in message or "context length" in message


def ollama_embed(base_url: str, model: str, text: str, num_ctx: int, keep_alive: str, timeout_sec: int) -> list[float]:
    last_error: Exception | None = None
    max_attempts = 10
    current_text = text
    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.post(
                f"{base_url.rstrip('/')}/api/embeddings",
                json={
                    "model": model,
                    "prompt": current_text,
                    "keep_alive": keep_alive,
                    "options": {"num_ctx": num_ctx},
                },
                timeout=timeout_sec,
            )
            resp.raise_for_status()
            data = resp.json()
            embedding = data.get("embedding")
            if not isinstance(embedding, list):
                raise RuntimeError(f"Embedding response has no list embedding: {data.keys()}")
            return embedding
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            response_text = ""
            if isinstance(exc, requests.HTTPError) and exc.response is not None:
                response_text = exc.response.text[:1000]
            if is_context_length_error(exc, response_text) and len(current_text) > MIN_EMBEDDING_CHARS:
                new_len = max(MIN_EMBEDDING_CHARS, len(current_text) // 2)
                current_text = compact_embedding_text(current_text, new_len)
                print(
                    f"Ollama embedding context error on attempt {attempt}/{max_attempts}. "
                    f"Truncate embedding input to {len(current_text)} chars and retry.",
                    flush=True,
                )
                continue
            wait_sec = min(120, 5 * attempt)
            print(
                f"Ollama embedding failed on attempt {attempt}/{max_attempts}: {exc}. "
                f"Response: {response_text!r}. Retry in {wait_sec}s",
                flush=True,
            )
            time.sleep(wait_sec)
    raise RuntimeError(f"Ollama embedding failed after retries: {last_error}") from last_error


def normalize_matrix(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix / np.maximum(norms, 1e-12)


def source_snapshot(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {"path": str(path), "size": stat.st_size, "mtime": stat.st_mtime}


def chunk_metadata(chunk: dict[str, Any]) -> dict[str, Any]:
    metadata = {key: value for key, value in chunk.items() if key != "text"}
    metadata.setdefault("chunk_id", chunk.get("chunk_id"))
    metadata.setdefault("relative_path", chunk.get("relative_path"))
    metadata.setdefault("source_path", chunk.get("source_path"))
    metadata.setdefault("document_type", chunk.get("document_type"))
    metadata.setdefault("source_type", chunk.get("source_type"))
    metadata.setdefault("chunk_level", chunk.get("chunk_level"))
    metadata.setdefault("chars", len(str(chunk.get("text") or "")))
    return metadata


def filter_chunks_by_source_type(chunks: list[dict[str, Any]], allowed_source_types: set[str]) -> tuple[list[dict[str, Any]], Counter[str], Counter[str]]:
    kept: list[dict[str, Any]] = []
    kept_counter: Counter[str] = Counter()
    skipped_counter: Counter[str] = Counter()
    for chunk in chunks:
        source_type = str(chunk.get("source_type") or "unknown")
        if source_type in allowed_source_types:
            kept.append(chunk)
            kept_counter[source_type] += 1
        else:
            skipped_counter[source_type] += 1
    return kept, kept_counter, skipped_counter


def build_numpy_index(chunks: list[dict[str, Any]], embedding_cache: dict[str, dict[str, Any]], index_dir: Path, embedding_model: str, chunks_path: Path, cache_path: Path, allowed_source_types: list[str]) -> dict[str, Any]:
    if not chunks:
        raise RuntimeError("No chunks to index")

    missing = [str(chunk.get("chunk_id")) for chunk in chunks if str(chunk.get("chunk_id")) not in embedding_cache]
    if missing:
        preview = ", ".join(missing[:10])
        raise RuntimeError(f"Missing embeddings for {len(missing)} chunks: {preview}")

    vectors: list[list[float]] = []
    rows: list[dict[str, Any]] = []
    embedding_dim: int | None = None

    for row_id, chunk in enumerate(chunks):
        chunk_id = str(chunk.get("chunk_id"))
        embedding = embedding_cache[chunk_id]["embedding"]
        if embedding_dim is None:
            embedding_dim = len(embedding)
        elif len(embedding) != embedding_dim:
            raise RuntimeError(f"Embedding dimension mismatch for {chunk_id}: {len(embedding)} != {embedding_dim}")
        text = str(chunk.get("text") or "")
        vectors.append(embedding)
        rows.append(
            {
                "row_id": row_id,
                "document": text,
                "metadata": chunk_metadata(chunk),
            }
        )

    matrix = np.asarray(vectors, dtype=np.float32)
    matrix = normalize_matrix(matrix)

    tmp_dir = index_dir.with_name(f"{index_dir.name}.tmp")
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=False)

    np.save(tmp_dir / EMBEDDINGS_FILE, matrix)
    with (tmp_dir / METADATA_FILE).open("w", encoding="utf-8", newline="\n") as fp:
        for row in rows:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")

    manifest = {
        "version": INDEX_VERSION,
        "backend": "numpy",
        "corpus": "asu_june_bot_v2",
        "allowed_source_types": allowed_source_types,
        "embedding_model": embedding_model,
        "embedding_dim": int(matrix.shape[1]),
        "count": int(matrix.shape[0]),
        "created_at": utc_now(),
        "source": {
            "chunks": source_snapshot(chunks_path),
            "embeddings_cache": source_snapshot(cache_path),
        },
        "files": {
            "embeddings": EMBEDDINGS_FILE,
            "metadata": METADATA_FILE,
        },
    }
    (tmp_dir / MANIFEST_FILE).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    if index_dir.exists():
        shutil.rmtree(index_dir)
    index_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(tmp_dir), str(index_dir))
    return manifest


def make_report(*, chunks_total_before_filter: int, chunks: list[dict[str, Any]], kept_by_source_type: Counter[str], skipped_by_source_type: Counter[str], cached_before: int, cached_after: int, embedded_this_run: int, cache_path: Path, index_dir: Path, manifest: dict[str, Any] | None, dry_run: bool, embed_only: bool, index_only: bool, embedding_model: str, max_embedding_chars: int, allowed_source_types: list[str]) -> dict[str, Any]:
    return {
        "generated_at": utc_now(),
        "index_version": INDEX_VERSION,
        "dry_run": dry_run,
        "embed_only": embed_only,
        "index_only": index_only,
        "embedding_model": embedding_model,
        "max_embedding_chars": max_embedding_chars,
        "allowed_source_types": allowed_source_types,
        "summary": {
            "chunks_total_before_filter": chunks_total_before_filter,
            "chunks_total": len(chunks),
            "chunks_skipped_by_source_type": sum(skipped_by_source_type.values()),
            "cached_before": cached_before,
            "embedded_this_run": embedded_this_run,
            "cached_after": cached_after,
            "missing_after": max(0, len(chunks) - cached_after),
            "index_built": manifest is not None,
            "index_count": manifest.get("count") if manifest else 0,
        },
        "kept_by_source_type": dict(sorted(kept_by_source_type.items())),
        "skipped_by_source_type": dict(sorted(skipped_by_source_type.items())),
        "paths": {
            "embeddings_cache_v2": str(cache_path),
            "numpy_index_v2": str(index_dir),
        },
        "manifest": manifest,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Asu June Bot embeddings cache and numpy index v2")
    parser.add_argument("--chunks-path", default=DEFAULT_CHUNKS_PATH)
    parser.add_argument("--cache-path", default=DEFAULT_EMBEDDINGS_CACHE)
    parser.add_argument("--index-dir", default=DEFAULT_INDEX_DIR)
    parser.add_argument("--report-path", default=DEFAULT_REPORT_PATH)
    parser.add_argument("--limit", type=int, default=0, help="Limit chunks for smoke/debug after source_type filtering")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--embed-only", action="store_true", help="Fill embeddings cache but do not build numpy index")
    parser.add_argument("--index-only", action="store_true", help="Do not call Ollama; build index from existing cache")
    parser.add_argument("--timeout-sec", type=int, default=240)
    parser.add_argument("--max-embedding-chars", type=int, default=DEFAULT_MAX_EMBEDDING_CHARS)
    parser.add_argument(
        "--include-source-type",
        action="append",
        dest="include_source_types",
        help="Source type to include in index. Can be repeated. Default: project_doc, meeting_artifact, analytical_note, instruction.",
    )
    args = parser.parse_args()

    if args.embed_only and args.index_only:
        raise ValueError("--embed-only and --index-only are mutually exclusive")

    cfg = load_config()
    chunks_path = resolve_work_path(cfg, args.chunks_path)
    cache_path = resolve_work_path(cfg, args.cache_path)
    index_dir = resolve_work_path(cfg, args.index_dir)
    report_path = resolve_work_path(cfg, args.report_path)

    base_url = cfg["ollama"]["base_url"]
    embedding_model = cfg["ollama"]["embedding_model"]
    embedding_num_ctx = int(cfg["ollama"].get("embedding_num_ctx", 8192))
    keep_alive = str(cfg["ollama"].get("keep_alive", "24h"))
    max_embedding_chars = max(MIN_EMBEDDING_CHARS, int(args.max_embedding_chars))
    allowed_source_types = list(args.include_source_types or DEFAULT_INDEX_SOURCE_TYPES)
    allowed_source_type_set = set(allowed_source_types)

    all_chunks = read_jsonl(chunks_path)
    all_chunks = [chunk for chunk in all_chunks if chunk.get("chunk_id") and str(chunk.get("text") or "").strip()]
    chunks_total_before_filter = len(all_chunks)
    chunks, kept_by_source_type, skipped_by_source_type = filter_chunks_by_source_type(all_chunks, allowed_source_type_set)
    if args.limit and args.limit > 0:
        chunks = chunks[: args.limit]
        kept_by_source_type = Counter(str(chunk.get("source_type") or "unknown") for chunk in chunks)

    cache = load_embedding_cache(cache_path, embedding_model)
    chunk_ids = {str(chunk["chunk_id"]) for chunk in chunks}
    cached_before = len([chunk_id for chunk_id in chunk_ids if chunk_id in cache])
    embedded_this_run = 0

    print(
        json.dumps(
            {
                "chunks_total_before_filter": chunks_total_before_filter,
                "chunks_total": len(chunks),
                "chunks_skipped_by_source_type": sum(skipped_by_source_type.values()),
                "kept_by_source_type": dict(sorted(kept_by_source_type.items())),
                "skipped_by_source_type": dict(sorted(skipped_by_source_type.items())),
                "cached_before": cached_before,
                "missing_before": len(chunks) - cached_before,
                "embedding_model": embedding_model,
                "embedding_num_ctx": embedding_num_ctx,
                "max_embedding_chars": max_embedding_chars,
                "allowed_source_types": allowed_source_types,
                "cache_path": str(cache_path),
                "index_dir": str(index_dir),
                "dry_run": args.dry_run,
                "embed_only": args.embed_only,
                "index_only": args.index_only,
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )

    if not args.index_only:
        for chunk in tqdm(chunks, desc="Embedding v2 cache", unit="chunk"):
            chunk_id = str(chunk["chunk_id"])
            if chunk_id in cache:
                continue
            if args.dry_run:
                continue
            text = str(chunk.get("text") or "")
            embedding_text = compact_embedding_text(text, max_embedding_chars)
            embedding = ollama_embed(base_url, embedding_model, embedding_text, embedding_num_ctx, keep_alive, args.timeout_sec)
            rec = {
                "chunk_id": chunk_id,
                "embedding_model": embedding_model,
                "embedding": embedding,
                "text_hash": chunk.get("text_hash"),
                "chars": chunk.get("chars", len(text)),
                "embedding_chars": len(embedding_text),
                "embedding_truncated": len(embedding_text) < len(text),
                "chunk_level": chunk.get("chunk_level"),
                "document_type": chunk.get("document_type"),
                "source_type": chunk.get("source_type"),
                "relative_path": chunk.get("relative_path"),
                "created_at": utc_now(),
            }
            append_jsonl(cache_path, rec)
            cache[chunk_id] = rec
            embedded_this_run += 1

    cached_after = len([chunk_id for chunk_id in chunk_ids if chunk_id in cache])
    manifest: dict[str, Any] | None = None
    if not args.dry_run and not args.embed_only:
        manifest = build_numpy_index(chunks, cache, index_dir, embedding_model, chunks_path, cache_path, allowed_source_types)

    report = make_report(
        chunks_total_before_filter=chunks_total_before_filter,
        chunks=chunks,
        kept_by_source_type=kept_by_source_type,
        skipped_by_source_type=skipped_by_source_type,
        cached_before=cached_before,
        cached_after=cached_after,
        embedded_this_run=embedded_this_run,
        cache_path=cache_path,
        index_dir=index_dir,
        manifest=manifest,
        dry_run=args.dry_run,
        embed_only=args.embed_only,
        index_only=args.index_only,
        embedding_model=embedding_model,
        max_embedding_chars=max_embedding_chars,
        allowed_source_types=allowed_source_types,
    )

    if not args.dry_run:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
