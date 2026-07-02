"""Semantic (vector) retrieval over one meeting's chunks (MA-MEETING-QA-V2, #111).

Reuses the project's Ollama embedding backend (``bge-m3`` by default) with a
lazy per-chunk embeddings cache, so:

- the first semantic query for a meeting embeds its chunks once and appends
  them to ``data/meeting_embeddings_cache.jsonl``;
- subsequent queries embed only the query string (one Ollama call);
- if Ollama is unavailable the retriever reports failure and the caller
  falls back to lexical scoring — meeting Q&A never hard-fails on this path.

No filesystem paths from this module ever reach API responses.
"""
from __future__ import annotations

import json
import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

from asu_june_bot.llm.ollama_common import ollama_embed

EmbedFn = Callable[[str], list[float]]

DEFAULT_MEETING_EMBEDDINGS_CACHE = "data/meeting_embeddings_cache.jsonl"
DEFAULT_EMBEDDING_MODEL = "bge-m3"


def _l2_normalize(vector: list[float]) -> list[float] | None:
    norm = math.sqrt(sum(component * component for component in vector))
    if norm <= 0:
        return None
    return [component / norm for component in vector]


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


class MeetingVectorRetriever:
    """Cosine-similarity scorer for meeting chunk rows with a JSONL cache.

    Cache row format (compatible with the corpus embeddings cache):
        {"chunk_id": ..., "embedding_model": ..., "embedding": [...]}
    """

    def __init__(
        self,
        embed_fn: EmbedFn,
        cache_path: Path | str,
        embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    ) -> None:
        self.embed_fn = embed_fn
        self.cache_path = Path(cache_path)
        self.embedding_model = embedding_model
        self._cache: dict[str, list[float]] | None = None

    # -- cache ---------------------------------------------------------------

    def _load_cache(self) -> dict[str, list[float]]:
        if self._cache is not None:
            return self._cache
        cache: dict[str, list[float]] = {}
        if self.cache_path.exists():
            with self.cache_path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(row, dict):
                        continue
                    if row.get("embedding_model") != self.embedding_model:
                        continue
                    chunk_id = row.get("chunk_id")
                    embedding = row.get("embedding")
                    if chunk_id and isinstance(embedding, list):
                        normalized = _l2_normalize(embedding)
                        if normalized is not None:
                            cache[str(chunk_id)] = normalized
        self._cache = cache
        return cache

    def _append_to_cache(self, entries: list[tuple[str, list[float]]]) -> None:
        if not entries:
            return
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with self.cache_path.open("a", encoding="utf-8") as fh:
            for chunk_id, embedding in entries:
                fh.write(
                    json.dumps(
                        {
                            "chunk_id": chunk_id,
                            "embedding_model": self.embedding_model,
                            "embedding": embedding,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

    # -- scoring ---------------------------------------------------------------

    def score_rows(
        self, query: str, rows: list[dict[str, Any]]
    ) -> list[float] | None:
        """Return one cosine score per row, or None when embeddings unavailable.

        Missing chunk embeddings are computed lazily and appended to the cache.
        Any embedding failure (Ollama down, bad response) returns None so the
        caller can fall back to lexical scoring.
        """
        if not rows:
            return []
        try:
            query_vector = _l2_normalize(self.embed_fn(query))
        except Exception:  # noqa: BLE001 — includes OllamaUnavailableError
            return None
        if query_vector is None:
            return None

        cache = self._load_cache()
        new_entries: list[tuple[str, list[float]]] = []
        row_vectors: list[list[float] | None] = []
        try:
            for row in rows:
                chunk_id = str(row.get("chunk_id") or "")
                vector = cache.get(chunk_id) if chunk_id else None
                if vector is None:
                    raw = self.embed_fn(str(row.get("text") or ""))
                    vector = _l2_normalize(raw)
                    if vector is None:
                        row_vectors.append(None)
                        continue
                    if chunk_id:
                        cache[chunk_id] = vector
                        new_entries.append((chunk_id, raw))
                row_vectors.append(vector)
        except Exception:  # noqa: BLE001 — includes OllamaUnavailableError
            return None

        self._append_to_cache(new_entries)
        return [
            max(0.0, _dot(query_vector, vector)) if vector is not None else 0.0
            for vector in row_vectors
        ]


def build_meeting_vector_retriever(
    config: dict[str, Any] | None,
    cache_path: Path | str | None = None,
) -> MeetingVectorRetriever | None:
    """Build a retriever from runtime config, or None when config is missing.

    Uses the same ``ollama`` config block as the project corpus embeddings.
    Construction never touches the network; failures surface only at query
    time as a lexical fallback.
    """
    if not isinstance(config, dict):
        return None
    ollama_cfg = config.get("ollama")
    if not isinstance(ollama_cfg, dict):
        return None
    base_url = str(ollama_cfg.get("base_url") or "").strip()
    if not base_url:
        return None
    model = str(ollama_cfg.get("embedding_model") or DEFAULT_EMBEDDING_MODEL)
    num_ctx = int(ollama_cfg.get("embedding_num_ctx") or 8192)
    keep_alive = str(ollama_cfg.get("keep_alive") or "24h")

    def _embed(text: str) -> list[float]:
        return ollama_embed(base_url, model, text, num_ctx=num_ctx, keep_alive=keep_alive)

    if cache_path is None:
        paths_cfg = config.get("paths") if isinstance(config.get("paths"), dict) else {}
        configured = paths_cfg.get("meeting_embeddings_cache") if isinstance(paths_cfg, dict) else None
        raw_path = configured or DEFAULT_MEETING_EMBEDDINGS_CACHE
        from asu_june_bot.core.config import resolve_work_path

        cache_path = resolve_work_path(config, raw_path)
    return MeetingVectorRetriever(_embed, cache_path, embedding_model=model)
