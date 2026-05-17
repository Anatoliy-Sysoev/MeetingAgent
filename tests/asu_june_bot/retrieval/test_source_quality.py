from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.retrieval.models import SearchResult  # noqa: E402
from asu_june_bot.retrieval.query_intent import QueryIntent, QueryIntentResult  # noqa: E402
from asu_june_bot.retrieval.source_quality import assess_source_quality, is_primary_eligible, is_weak_source, with_source_quality  # noqa: E402


def result(text: str, *, matched_by: list[str] | None = None, metadata: dict | None = None) -> SearchResult:
    return SearchResult(
        source_id="SRC-001",
        text=text,
        score=1.0,
        vector_score=None,
        bm25_score=1.0,
        matched_by=matched_by or ["bm25"],
        metadata=metadata or {"chunk_id": "chunk-1", "relative_path": "doc.md", "document_type": "ФТТ"},
    )


def intent(sections: list[str] | None = None) -> QueryIntentResult:
    return QueryIntentResult(
        intent=QueryIntent.REQUIREMENT_LOOKUP,
        confidence=0.9,
        is_project_related=True,
        mentioned_sections=sections or [],
    )


def test_short_diagram_like_source_is_weak_and_not_primary_eligible() -> None:
    item = result("Рисунок 1. UML: CCPM -> AD -> CCPM")

    assessment = assess_source_quality(item, intent())

    assert assessment.weak is True
    assert "caption_or_diagram_like" in assessment.reasons
    assert assessment.primary_eligible is False


def test_exact_requirement_short_text_can_remain_primary_eligible() -> None:
    item = result(
        "4.2.5 Интеграция с НОВАДОК. Требуется обеспечить подписание ЭЦП.",
        metadata={"chunk_id": "chunk-1", "relative_path": "ФТТ.docx", "document_type": "ФТТ", "sections": ["4.2.5"]},
    )

    assessment = assess_source_quality(item, intent(["4.2.5"]))

    assert assessment.primary_eligible is True
    assert "short_text" not in assessment.reasons


def test_with_source_quality_adds_diagnostics_and_label() -> None:
    item = result("Диаграмма: короткий фрагмент", matched_by=["vector"])

    updated = with_source_quality(item, intent())

    assert is_weak_source(updated) is True
    assert is_primary_eligible(updated) is False
    assert updated.diagnostics["source_quality"]["weak"] is True
    assert "quality:weak_source" in updated.diagnostics["rerank_labels"]
