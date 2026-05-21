from __future__ import annotations

from typing import Any

from asu_june_bot.core.config import resolve_work_path
from asu_june_bot.llm.ollama_common import OllamaUnavailableError, ollama_embed
from .metadata import enrich_metadata
from .models import SearchResult
from .numpy_backend import index_exists, load_index
from .source_policy import SourcePolicy


class VectorSearchAdapter:
    def __init__(self, cfg: dict[str, Any], source_policy: SourcePolicy | None = None):
        self.cfg = cfg
        self.source_policy = source_policy or SourcePolicy()
        paths = cfg.get("paths", {})
        self.index_path = resolve_work_path(cfg, paths.get("numpy_index", "data/numpy_index"))
        if not index_exists(self.index_path):
            raise FileNotFoundError(f"Numpy index not found: {self.index_path}")
        self.index = load_index(self.index_path)
        self.base_url = cfg["ollama"]["base_url"]
        self.embedding_model = cfg["ollama"]["embedding_model"]
        self.embedding_num_ctx = int(cfg["ollama"].get("embedding_num_ctx", 8192))
        self.keep_alive = str(cfg["ollama"].get("keep_alive", "24h"))
        self.exclude_path_patterns = list(cfg.get("exclude_path_patterns", []))

    def search(
        self,
        query: str,
        top_k: int,
        include_source_types: list[str] | None = None,
        no_dedupe: bool = False,
    ) -> list[SearchResult]:
        embedding = ollama_embed(self.base_url, self.embedding_model, query, self.embedding_num_ctx, self.keep_alive)
        # Fetch more than needed because source policy may filter out noisy sources.
        contexts = self.index.query(
            embedding,
            max(top_k * 4, top_k),
            exclude_path_patterns=self.exclude_path_patterns,
            dedupe_by_chunk_id=not no_dedupe,
        )

        results: list[SearchResult] = []
        for ctx in contexts:
            text = str(ctx.get("document") or "")
            metadata = enrich_metadata(dict(ctx.get("metadata") or {}), text)
            if not self.source_policy.is_allowed(metadata, query, include_source_types):
                continue
            vector_score = float(ctx.get("score", 0.0))
            policy_weight = self.source_policy.weight(metadata)
            weighted_score = vector_score * policy_weight
            results.append(
                SearchResult(
                    source_id=f"VEC-{len(results) + 1:03d}",
                    text=text,
                    score=weighted_score,
                    vector_score=vector_score,
                    bm25_score=None,
                    metadata=metadata,
                    matched_by=["vector"],
                    diagnostics={"policy_weight": policy_weight},
                )
            )
            if len(results) >= top_k:
                break
        return results
