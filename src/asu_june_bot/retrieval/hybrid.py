from __future__ import annotations

from dataclasses import replace
from typing import Any

from .bm25 import BM25SearchAdapter
from .models import SearchResult
from .query_expansion import QueryExpander
from .source_policy import SourcePolicy
from .vector import OllamaUnavailableError, VectorSearchAdapter


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


def _prefers_lexical_signal(query: str) -> bool:
    lowered = query.lower()
    exact_markers = (
        "app_ccpm",
        "bearer",
        "bearer token",
        "2520",
        "600 одновременно",
        "rto",
        "rpo",
        "4.1",
        "4.2",
        "4.2.5",
        "9.6",
        "10.8",
        "ldaps",
        "порт 636",
        "регламент ведения",
        "реестр нси",
        "pdf",
        "csv",
    )
    return any(marker in lowered for marker in exact_markers)


class HybridRetriever:
    def __init__(
        self,
        vector_search: VectorSearchAdapter | None,
        bm25_search: BM25SearchAdapter | None,
        source_policy: SourcePolicy | None = None,
        query_expander: QueryExpander | None = None,
        vector_weight: float = 0.65,
        bm25_weight: float = 0.35,
        hybrid_fallback_to_bm25: bool = True,
    ):
        self.vector_search = vector_search
        self.bm25_search = bm25_search
        self.source_policy = source_policy or SourcePolicy()
        self.query_expander = query_expander or QueryExpander()
        self.vector_weight = vector_weight
        self.bm25_weight = bm25_weight
        self.hybrid_fallback_to_bm25 = hybrid_fallback_to_bm25
        self.last_warnings: list[str] = []

    def search(
        self,
        query: str,
        top_k: int = 10,
        include_source_types: list[str] | None = None,
        mode: str = "hybrid",
    ) -> list[SearchResult]:
        self.last_warnings = []
        expanded_query, expansions = self.query_expander.expand(query)
        search_query = expanded_query if mode in ("hybrid", "vector") else query
        candidate_k = max(top_k * 3, top_k)
        vector_results: list[SearchResult] = []
        bm25_results: list[SearchResult] = []

        if mode in ("hybrid", "vector") and self.vector_search is not None:
            try:
                vector_results = self.vector_search.search(search_query, candidate_k, include_source_types=include_source_types)
            except OllamaUnavailableError as exc:
                if mode == "vector" or not self.hybrid_fallback_to_bm25:
                    raise
                self.last_warnings.append(f"vector_unavailable_fallback_to_bm25: {exc}")
                vector_results = []

        if mode in ("hybrid", "bm25") and self.bm25_search is not None:
            # BM25 receives the expanded query too, because exact words like MDR/LDAPS/Blitz are useful.
            bm25_results = self.bm25_search.search(expanded_query, candidate_k, include_source_types=include_source_types)

        if mode == "vector":
            return self._renumber(self._with_expansion_diagnostics(vector_results[:top_k], expansions, expanded_query))
        if mode == "bm25":
            return self._renumber(self._with_expansion_diagnostics(bm25_results[:top_k], expansions, expanded_query))

        if not vector_results and bm25_results and self.last_warnings:
            fallback_results = self._with_expansion_diagnostics(bm25_results[:top_k], expansions, expanded_query)
            fallback_results = [
                replace(
                    result,
                    diagnostics={
                        **result.diagnostics,
                        "retrieval_warning": "; ".join(self.last_warnings),
                        "fallback_mode": "bm25",
                    },
                )
                for result in fallback_results
            ]
            return self._renumber(fallback_results)

        vector_norm = _normalize_scores(vector_results, "score")
        bm25_norm = _normalize_scores(bm25_results, "score")
        vector_weight = self.vector_weight
        bm25_weight = self.bm25_weight
        if _prefers_lexical_signal(query):
            vector_weight = 0.42
            bm25_weight = 0.58

        merged: dict[str, SearchResult] = {}
        for result in vector_results + bm25_results:
            key = _chunk_key(result)
            existing = merged.get(key)
            vector_component = vector_norm.get(key, 0.0)
            bm25_component = bm25_norm.get(key, 0.0)
            score = vector_weight * vector_component + bm25_weight * bm25_component

            diagnostics = dict(result.diagnostics)
            diagnostics.update(
                {
                    "vector_component": vector_component,
                    "bm25_component": bm25_component,
                    "vector_weight": vector_weight,
                    "bm25_weight": bm25_weight,
                    "expanded_terms": expansions,
                    "expanded_query": expanded_query if expansions else None,
                }
            )
            if self.last_warnings:
                diagnostics["retrieval_warning"] = "; ".join(self.last_warnings)

            if existing is None:
                merged[key] = replace(
                    result,
                    score=score,
                    vector_score=result.vector_score,
                    bm25_score=result.bm25_score,
                    matched_by=list(result.matched_by),
                    diagnostics=diagnostics,
                )
            else:
                matched_by = sorted(set(existing.matched_by + result.matched_by))
                merged[key] = replace(
                    existing,
                    score=max(existing.score, score),
                    vector_score=existing.vector_score if existing.vector_score is not None else result.vector_score,
                    bm25_score=existing.bm25_score if existing.bm25_score is not None else result.bm25_score,
                    matched_by=matched_by,
                    diagnostics={**existing.diagnostics, **diagnostics},
                )

        ranked = sorted(merged.values(), key=lambda item: item.score, reverse=True)
        return self._renumber(ranked[:top_k])

    @staticmethod
    def _with_expansion_diagnostics(results: list[SearchResult], expansions: list[str], expanded_query: str) -> list[SearchResult]:
        return [
            replace(
                result,
                diagnostics={
                    **result.diagnostics,
                    "expanded_terms": expansions,
                    "expanded_query": expanded_query if expansions else None,
                },
            )
            for result in results
        ]

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
    query_expansion_cfg = ajb_cfg.get("query_expansion", {})
    source_policy = SourcePolicy(source_policy_cfg)
    query_expander = QueryExpander(query_expansion_cfg)

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
        query_expander=query_expander,
        vector_weight=float(retrieval_cfg.get("vector_weight", 0.65)),
        bm25_weight=float(retrieval_cfg.get("bm25_weight", 0.35)),
        hybrid_fallback_to_bm25=bool(retrieval_cfg.get("hybrid_fallback_to_bm25", True)),
    )
