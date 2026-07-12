from __future__ import annotations

from dataclasses import dataclass

import pytest

from asu_june_bot.retrieval.hybrid import (
    HybridRetriever,
    _normalize_scores,
    _select_fusion_policy,
)
from asu_june_bot.retrieval.models import SearchResult
from asu_june_bot.retrieval.ranking_profile import default_ranking_profile
from asu_june_bot.retrieval.vector import OllamaUnavailableError


def _result(
    chunk_id: str,
    score: float,
    matched_by: str,
) -> SearchResult:
    return SearchResult(
        source_id=chunk_id,
        text=f"synthetic evidence {chunk_id}",
        score=score,
        vector_score=score if matched_by == "vector" else None,
        bm25_score=score if matched_by == "bm25" else None,
        metadata={
            "chunk_id": chunk_id,
            "chunk_index": 1,
            "relative_path": f"synthetic/{chunk_id}.md",
            "source_type": "project_doc",
        },
        matched_by=[matched_by],
        diagnostics={f"{matched_by}_diagnostic": True},
    )


@dataclass
class FakeSearch:
    results: list[SearchResult] | None = None
    error: Exception | None = None

    def search(self, query: str, top_k: int, include_source_types=None) -> list[SearchResult]:
        if self.error:
            raise self.error
        return list(self.results or [])[:top_k]


class FakeExpander:
    def expand(self, query: str) -> tuple[str, list[str]]:
        return f"{query}\nsynthetic expansion", ["synthetic expansion"]


@pytest.mark.parametrize(
    ("query", "policy", "vector_weight", "bm25_weight"),
    [
        ("обычный вопрос об архитектуре", "default", 0.65, 0.35),
        ("какой project_role передаётся", "lexical", 0.42, 0.58),
        ("какие статусы замечаний", "strong_lexical", 0.25, 0.75),
    ],
)
def test_fusion_policy_is_profile_driven(
    query: str,
    policy: str,
    vector_weight: float,
    bm25_weight: float,
) -> None:
    decision = _select_fusion_policy(
        query,
        default_ranking_profile(),
        vector_weight=0.65,
        bm25_weight=0.35,
    )
    assert (decision.policy, decision.vector_weight, decision.bm25_weight) == (
        policy,
        vector_weight,
        bm25_weight,
    )


def test_score_normalization_handles_empty_equal_and_range() -> None:
    low = _result("low", 2.0, "vector")
    high = _result("high", 6.0, "vector")
    assert _normalize_scores([], "score") == {}
    assert _normalize_scores([low], "score") == {"low": 1.0}
    assert _normalize_scores([low, high], "score") == {"low": 0.0, "high": 1.0}


def test_hybrid_merge_preserves_both_signals_and_trace() -> None:
    retriever = HybridRetriever(
        vector_search=FakeSearch([_result("shared", 9.0, "vector")]),
        bm25_search=FakeSearch([_result("shared", 4.0, "bm25")]),
        query_expander=FakeExpander(),
    )

    results = retriever.search("какие статусы замечаний", top_k=3)

    assert len(results) == 1
    result = results[0]
    assert result.source_id == "SRC-001"
    assert result.matched_by == ["bm25", "vector"]
    assert result.score == pytest.approx(1.0)
    assert result.diagnostics["fusion_policy"] == "strong_lexical"
    assert result.diagnostics["vector_weight"] == 0.25
    assert result.diagnostics["bm25_weight"] == 0.75
    assert result.diagnostics["expanded_terms"] == ["synthetic expansion"]
    assert result.diagnostics["ranking_profile_version"] == 1


def test_hybrid_falls_back_to_bm25_with_bounded_diagnostics() -> None:
    retriever = HybridRetriever(
        vector_search=FakeSearch(error=OllamaUnavailableError("offline")),
        bm25_search=FakeSearch([_result("fallback", 4.0, "bm25")]),
        query_expander=FakeExpander(),
    )

    results = retriever.search("архитектура", top_k=1)

    assert [item.metadata["chunk_id"] for item in results] == ["fallback"]
    assert results[0].diagnostics["fallback_mode"] == "bm25"
    assert "vector_unavailable_fallback_to_bm25" in results[0].diagnostics["retrieval_warning"]


def test_vector_mode_propagates_unavailable_error() -> None:
    retriever = HybridRetriever(
        vector_search=FakeSearch(error=OllamaUnavailableError("offline")),
        bm25_search=None,
        query_expander=FakeExpander(),
    )
    with pytest.raises(OllamaUnavailableError):
        retriever.search("архитектура", top_k=1, mode="vector")


def test_vector_and_bm25_modes_return_only_requested_backend() -> None:
    vector = _result("vector-only", 3.0, "vector")
    lexical = _result("bm25-only", 2.0, "bm25")
    retriever = HybridRetriever(
        vector_search=FakeSearch([vector]),
        bm25_search=FakeSearch([lexical]),
        query_expander=FakeExpander(),
    )

    vector_results = retriever.search("архитектура", top_k=1, mode="vector")
    bm25_results = retriever.search("архитектура", top_k=1, mode="bm25")

    assert vector_results[0].metadata["chunk_id"] == "vector-only"
    assert bm25_results[0].metadata["chunk_id"] == "bm25-only"
    assert vector_results[0].diagnostics["expanded_query"].endswith("synthetic expansion")
    assert bm25_results[0].diagnostics["expanded_query"].endswith("synthetic expansion")
