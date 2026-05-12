from __future__ import annotations

from dataclasses import replace
from typing import Any

from .bm25 import BM25SearchAdapter
from .models import SearchResult
from .source_policy import SourcePolicy
from .vector import VectorSearchAdapter


def _chunk_key(result: SearchResult) -> str:
    return str(result.metadata.get("chunk_id") or f"{result.metadata.get('relative_path')}#{result.metadata.get('chunk_index')}")


def _normalize_scores(results: list[SearchResult], attr: str) -> dict[str, float]:
    values = [float(getattr(result, attr) or 0.0) for result in results]
    if not values:
        return {}
    min_v = min(values)
    max_v = max(values)
    if max_v <= min_v:
        return {_chunk_key(result): 1.0 for result in results}
    return {_chunk_key(result): (float(getattr(result, attr) or 0.0) - min_v) / (max_v - min_v) for result in results}


class HybridRetriever:
    def __init__(
        self,
        vector_search: VectorSearchAdapter | None,
        bm25_search: BM25SearchAdapter | None,
        source_policy: SourcePolicy | None = None,
        vector_weight: float = 0.65,
        bm25_weight: float = 0.35,
    ):
        self.vector_search = vector_search
        self.bm25_search = bm25_search
        self.source_policy = source_policy or SourcePolicy()
        self.vector_weight = vector_weight
        self.bm25_weight = bm25_weight

    def search(
        self,
        query: str,
        top_k: int = 10,
        include_source_types: list[str] | None = None,
        mode: str = "hybrid",
    ) -> list[SearchResult]:
        candidate_k = max(top_k * 3, top_k)
        vector_results: list[SearchResult] = []
        bm25_results: list[SearchResult] = []

        if mode in ("hybrid", "vector") and self.vector_search is not None:
            vector_results = self.vector_search.search(query, candidate_k, include_source_types=include_source_types)
        if mode in ("hybrid", "bm25") and self.bm25_search is not None:
            bm25_results = self.bm25_search.search(query, candidate_k, include_source_types=include_source_types)

        if mode == "vector":
            return self._renumber(vector_results[:top_k])
        if mode == "bm25":
            return self._renumber(bm25_results[:top_k])

        vector_norm = _normalize_scores(vector_results, "score")
        bm25_norm = _normalize_scores(bm25_results, "score")

        merged: dict[str, SearchResult] = {}
        for result in vector_results + bm25_results:
            key = _chunk_key(result)
            existing = merged.get(key)
            vector_component = vector_norm.get(key, 0.0)
            bm25_component = bm25_norm.get(key, 0.0)
            score = self.vector_weight * vector_component + self.bm25_weight * bm25_component

            if existing is None:
                merged[key] = replace(
                    result,
                    score=score,
                    vector_score=result.vector_score,
                    bm25_score=result.bm25_score,
                    matched_by=list(result.matched_by),
                )
            else:
                matched_by = sorted(set(existing.matched_by + result.matched_by))
                merged[key] = replace(
                    existing,
                    score=max(existing.score, score),
                    vector_score=existing.vector_score if existing.vector_score is not None else result.vector_score,
                    bm25_score=existing.bm25_score if existing.bm25_score is not None else result.bm25_score,
                    matched_by=matched_by,
                )

        ranked = sorted(merged.values(), key=lambda item: item.score, reverse=True)
        return self._renumber(ranked[:top_k])

    @staticmethod
    def _renumber(results: list[SearchResult]) -> list[SearchResult]:
        return [replace(result, source_id=f"SRC-{idx:03d}") for idx, result in enumerate(results, start=1)]


def build_hybrid_retriever(
    cfg: dict[str, Any],
    rows: list[dict[str, Any]],
    mode: str = "hybrid",
) -> HybridRetriever:
    ajb_cfg = cfg.get("asu_june_bot", {})
    retrieval_cfg = ajb_cfg.get("retrieval", {})
    source_policy_cfg = ajb_cfg.get("source_policy", {})
    source_policy = SourcePolicy(source_policy_cfg)

    vector_search = None
    bm25_search = None
    if mode in ("hybrid", "vector"):
        vector_search = VectorSearchAdapter(cfg, source_policy)
    if mode in ("hybrid", "bm25"):
        bm25_search = BM25SearchAdapter(rows, source_policy)

    return HybridRetriever(
        vector_search=vector_search,
        bm25_search=bm25_search,
        source_policy=source_policy,
        vector_weight=float(retrieval_cfg.get("vector_weight", 0.65)),
        bm25_weight=float(retrieval_cfg.get("bm25_weight", 0.35)),
    )
