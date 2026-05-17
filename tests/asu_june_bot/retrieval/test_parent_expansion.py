from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.retrieval.models import SearchResult  # noqa: E402
from asu_june_bot.retrieval.parent_expansion import ParentExpander  # noqa: E402
from asu_june_bot.retrieval.query_intent import QueryIntent, QueryIntentResult  # noqa: E402
from asu_june_bot.retrieval.source_quality import with_source_quality  # noqa: E402


def intent() -> QueryIntentResult:
    return QueryIntentResult(intent=QueryIntent.GENERAL_PROJECT_QUESTION, confidence=0.9, is_project_related=True)


def result(chunk_id: str, text: str, *, chunk_index: int, section: str = "AD") -> SearchResult:
    return SearchResult(
        source_id=chunk_id,
        text=text,
        score=1.0,
        vector_score=None,
        bm25_score=1.0,
        matched_by=["bm25"],
        metadata={
            "chunk_id": chunk_id,
            "relative_path": "doc.md",
            "document_type": "СоИ AD",
            "chunk_index": chunk_index,
            "section": section,
        },
    )


def test_parent_expansion_enriches_weak_source_with_same_section_neighbor() -> None:
    weak = with_source_quality(result("chunk-1", "Рисунок 1. UML: CCPM -> AD", chunk_index=1), intent())
    neighbor = result("chunk-2", "Раздел описывает получение пользователей из групп безопасности Active Directory.", chunk_index=2)

    expanded, diagnostics = ParentExpander(max_parent_chars=400).expand([weak], [weak, neighbor])

    assert diagnostics["expanded_count"] == 1
    assert "Active Directory" in expanded[0].text
    assert expanded[0].diagnostics["parent_expansion"]["applied"] is True


def test_parent_expansion_skips_strong_source() -> None:
    strong = result("chunk-1", "Это длинный содержательный фрагмент. " * 30, chunk_index=1)

    expanded, diagnostics = ParentExpander(max_parent_chars=400).expand([strong], [strong])

    assert expanded[0].text == strong.text
    assert diagnostics["skipped_not_weak"] == 1
