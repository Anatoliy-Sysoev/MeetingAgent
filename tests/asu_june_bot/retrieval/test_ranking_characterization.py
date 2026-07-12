from __future__ import annotations

import json
from pathlib import Path

import pytest

from asu_june_bot.retrieval.bm25 import BM25SearchAdapter
from asu_june_bot.retrieval.models import SearchResult
from asu_june_bot.retrieval.post_rerank import PostReranker
from asu_june_bot.retrieval.query_intent import classify_query_intent


ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "tests" / "fixtures" / "retrieval" / "ranking_characterization.jsonl"


def _cases() -> list[dict]:
    raw = FIXTURE.read_bytes()
    assert len(raw) <= 128 * 1024
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    assert 10 <= len(rows) <= 100
    return rows


CASES = _cases()


def _metadata(case: dict) -> dict:
    return {
        "chunk_id": case["case_id"],
        "document_type": case["document_type"],
        "relative_path": case["relative_path"],
        "sections": case.get("sections", []),
        "requirement_id": case.get("requirement_id"),
        "source_type": "project_doc",
    }


def _result(case: dict, *, score: float = 1.0) -> SearchResult:
    return SearchResult(
        source_id="RAW-001",
        text=case["text"],
        score=score,
        vector_score=score if "vector" in case["matched_by"] else None,
        bm25_score=score if "bm25" in case["matched_by"] else None,
        metadata=_metadata(case),
        matched_by=list(case["matched_by"]),
        diagnostics={},
    )


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["case_id"])
def test_post_rerank_characterization(case: dict) -> None:
    intent = classify_query_intent(case["query"])
    output = PostReranker().rerank(case["query"], intent, [_result(case)]).results[0]

    assert intent.intent.value == case["expected"]["intent"]
    assert output.diagnostics["rerank_multiplier"] == pytest.approx(
        case["expected"]["post_multiplier"]
    )
    assert output.diagnostics["rerank_labels"] == case["expected"]["post_labels"]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["case_id"])
def test_bm25_intent_characterization(case: dict) -> None:
    adapter = BM25SearchAdapter([{"text": case["text"], **_metadata(case)}])
    multiplier, labels = adapter._intent_boost(case["query"], adapter.documents[0])

    assert round(multiplier, 6) == pytest.approx(case["expected"]["bm25_multiplier"])
    assert labels == case["expected"]["bm25_labels"]


def test_post_rerank_orders_relevant_passport_chunk_before_noise() -> None:
    relevant = CASES[0]
    noise = next(case for case in CASES if case["case_id"] == "passport_support_noise")
    intent = classify_query_intent(relevant["query"])
    output = PostReranker().rerank(
        relevant["query"],
        intent,
        [_result(noise), _result(relevant)],
    )

    assert [item.metadata["chunk_id"] for item in output.results] == [
        "passport_related_documents",
        "passport_support_noise",
    ]


def test_post_rerank_duplicate_and_overflow_diagnostics_are_stable() -> None:
    case = CASES[0]
    intent = classify_query_intent(case["query"])
    first = _result(case, score=2.0)
    duplicate = _result(case, score=1.0)
    other = _result(CASES[1], score=0.5)

    output = PostReranker().rerank(case["query"], intent, [first, duplicate, other], top_k=1)

    assert len(output.results) == 1
    assert output.diagnostics == {
        "reranker": "PostReranker",
        "input_count": 3,
        "output_count": 1,
        "excluded_count": 2,
        "intent": "document_overview",
    }
    assert [item.diagnostics["rerank_labels"][-1] for item in output.excluded] == [
        "excluded:duplicate_chunk",
        "excluded:overflow_after_rerank",
    ]


def test_characterization_fixture_is_public_and_synthetic() -> None:
    for case in CASES:
        assert case["relative_path"].startswith("synthetic/")
        assert ":\\" not in case["relative_path"]
        assert set(case) <= {
            "case_id",
            "query",
            "text",
            "document_type",
            "relative_path",
            "matched_by",
            "sections",
            "requirement_id",
            "expected",
        }
