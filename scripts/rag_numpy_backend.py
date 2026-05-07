from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from rag_common import is_excluded_by_path_patterns, jsonl_read, stable_id


INDEX_VERSION = 1
EMBEDDINGS_FILE = "embeddings.npy"
METADATA_FILE = "metadata.jsonl"
MANIFEST_FILE = "manifest.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_matrix(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix / np.maximum(norms, 1e-12)


def _normalize_vector(vector: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vector)
    return vector / max(float(norm), 1e-12)


def _source_snapshot(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path),
        "size": stat.st_size,
        "mtime": stat.st_mtime,
    }


def index_exists(index_dir: Path) -> bool:
    return (
        (index_dir / EMBEDDINGS_FILE).exists()
        and (index_dir / METADATA_FILE).exists()
        and (index_dir / MANIFEST_FILE).exists()
    )


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


def build_index(
    chunks_path: Path,
    embeddings_cache_path: Path,
    index_dir: Path,
    embedding_model: str,
) -> dict[str, Any]:
    chunks = list(jsonl_read(chunks_path))
    if not chunks:
        raise RuntimeError(f"No chunks found: {chunks_path}")

    chunk_ids = {str(chunk["chunk_id"]) for chunk in chunks}
    embedding_cache = load_embedding_cache(embeddings_cache_path, embedding_model, chunk_ids)
    missing = [str(chunk["chunk_id"]) for chunk in chunks if str(chunk["chunk_id"]) not in embedding_cache]
    if missing:
        preview = ", ".join(missing[:10])
        raise RuntimeError(f"Missing embeddings for {len(missing)} current chunks: {preview}")

    rows: list[dict[str, Any]] = []
    vectors: list[list[float]] = []
    embedding_dim: int | None = None

    for row_id, chunk in enumerate(chunks):
        chunk_id = str(chunk["chunk_id"])
        embedding = embedding_cache[chunk_id]
        if embedding_dim is None:
            embedding_dim = len(embedding)
        elif len(embedding) != embedding_dim:
            raise RuntimeError(f"Embedding dimension mismatch for chunk {chunk_id}: {len(embedding)} != {embedding_dim}")

        vectors.append(embedding)
        rows.append(
            {
                "row_id": row_id,
                "document": chunk["text"],
                "metadata": {
                    "chunk_id": chunk_id,
                    "db_id": chunk.get("db_id"),
                    "source_path": chunk["source_path"],
                    "relative_path": chunk["relative_path"],
                    "extension": chunk["extension"],
                    "sha256": chunk["sha256"],
                    "mtime": float(chunk["mtime"]),
                    "chunk_index": int(chunk["chunk_index"]),
                    "chars": int(chunk["chars"]),
                },
            }
        )

    matrix = np.asarray(vectors, dtype=np.float32)
    matrix = _normalize_matrix(matrix)

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
        "embedding_model": embedding_model,
        "embedding_dim": int(matrix.shape[1]),
        "count": int(matrix.shape[0]),
        "created_at": _utc_now(),
        "source": {
            "chunks": _source_snapshot(chunks_path),
            "embeddings_cache": _source_snapshot(embeddings_cache_path),
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


class NumpyRagIndex:
    def __init__(self, index_dir: Path):
        self.index_dir = index_dir
        self.manifest = json.loads((index_dir / MANIFEST_FILE).read_text(encoding="utf-8"))
        self.embeddings = np.load(index_dir / EMBEDDINGS_FILE, mmap_mode="r")
        self.metadata = list(jsonl_read(index_dir / METADATA_FILE))

        count = int(self.manifest["count"])
        if self.embeddings.shape[0] != count or len(self.metadata) != count:
            raise RuntimeError(
                f"Numpy index is inconsistent: embeddings={self.embeddings.shape[0]}, metadata={len(self.metadata)}, manifest={count}"
            )

    def query(
        self,
        query_embedding: list[float],
        top_k: int,
        exclude_path_patterns: list[str] | None = None,
        dedupe_by_chunk_id: bool = True,
    ) -> list[dict[str, Any]]:
        if top_k <= 0:
            return []

        exclude_path_patterns = exclude_path_patterns or []
        query = _normalize_vector(np.asarray(query_embedding, dtype=np.float32))
        scores = np.asarray(self.embeddings @ query, dtype=np.float32)
        top_indices = np.argsort(-scores)
        duplicate_counts: dict[str, int] = {}

        if dedupe_by_chunk_id:
            for row in self.metadata:
                meta = row["metadata"]
                if is_excluded_by_path_patterns(str(meta.get("relative_path", "")), exclude_path_patterns):
                    continue
                dedupe_key = stable_id(row["document"])
                duplicate_counts[dedupe_key] = duplicate_counts.get(dedupe_key, 0) + 1

        contexts: list[dict[str, Any]] = []
        seen_dedupe_keys: set[str] = set()
        for idx in top_indices:
            score = float(scores[int(idx)])
            row = self.metadata[int(idx)]
            meta = dict(row["metadata"])
            if is_excluded_by_path_patterns(str(meta.get("relative_path", "")), exclude_path_patterns):
                continue
            if dedupe_by_chunk_id:
                dedupe_key = stable_id(row["document"])
                if dedupe_key in seen_dedupe_keys:
                    continue
                seen_dedupe_keys.add(dedupe_key)
                duplicate_count = duplicate_counts.get(dedupe_key, 1) - 1
                if duplicate_count > 0:
                    meta["duplicate_count"] = duplicate_count
            contexts.append(
                {
                    "document": row["document"],
                    "metadata": meta,
                    "distance": float(1.0 - score),
                    "score": score,
                }
            )
            if len(contexts) >= top_k:
                break
        return contexts


def load_index(index_dir: Path) -> NumpyRagIndex:
    if not index_exists(index_dir):
        raise FileNotFoundError(f"Numpy RAG index not found: {index_dir}")
    return NumpyRagIndex(index_dir)
