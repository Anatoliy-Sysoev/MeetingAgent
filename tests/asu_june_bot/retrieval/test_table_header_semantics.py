from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.retrieval.context_builder import ContextBuilder  # noqa: E402
from asu_june_bot.retrieval.models import SearchResult  # noqa: E402
from asu_june_bot.retrieval.query_intent import QueryIntent, QueryIntentResult  # noqa: E402


def ftt_table_8_row(
    *,
    document_type: str = "ФТТ",
    table_id: str | None = "Table 8",
    cells: dict | None = None,
    include_cells: bool = True,
) -> SearchResult:
    metadata = {
        "chunk_id": "ftt-table8-row-11",
        "relative_path": "ФТТ.docx",
        "document_type": document_type,
        "chunk_index": 11,
        "table_id": table_id,
        "requirement_id": "1.1",
    }
    if include_cells:
        metadata["cells"] = cells if cells is not None else {"№": "1.1", "Входит в объём проекта_3": "Х"}
    if table_id is None:
        metadata.pop("table_id")
    return SearchResult(
        source_id="ftt-table8-row-11",
        text="Таблица: Table 8\n№: 1.1\nНаименование: Технический документооборот\nВходит в объём проекта_3: Х",
        score=1.0,
        vector_score=None,
        bm25_score=1.0,
        metadata=metadata,
        matched_by=["bm25"],
        diagnostics={},
    )


def project_intent() -> QueryIntentResult:
    return QueryIntentResult(intent=QueryIntent.GENERAL_PROJECT_QUESTION, confidence=0.9, is_project_related=True)


def build_context(result: SearchResult):
    return ContextBuilder(
        primary_limit=2,
        supporting_limit=2,
        enable_source_quality_filter=False,
        enable_parent_expansion=False,
    ).build("К какому этапу ФТ отнесено требование 1.1?", project_intent(), [result], [])


def test_context_builder_adds_ftt_table_8_stage_semantics_without_changing_chunk_id() -> None:
    context = build_context(ftt_table_8_row())

    source = context.primary_sources[0]
    assert "Требование 1.1 относится к Этапу 3 (ФТ3)." in source.text
    assert "Каноническое значение: Этап 3 (ФТ3)." in source.text
    assert "Основание: заполнена колонка «Входит в объём проекта_3»." in source.text
    assert source.metadata["chunk_id"] == "ftt-table8-row-11"
    assert source.metadata["table_header_semantics_applied"] is True
    assert source.metadata["table_header_semantics_facts"]
    assert context.diagnostics["table_header_semantics"]["applied"] is True
    assert context.diagnostics["table_header_semantics"]["enriched_count"] == 1


def test_context_builder_changes_only_built_context_result_not_original_result() -> None:
    original = ftt_table_8_row()
    original_text = original.text
    original_metadata = dict(original.metadata)

    context = build_context(original)

    assert context.primary_sources[0].text != original_text
    assert original.text == original_text
    assert original.metadata == original_metadata
    assert context.primary_sources[0].metadata["chunk_id"] == original.metadata["chunk_id"]


def test_context_builder_skips_non_ftt_or_non_table_8_or_missing_cells() -> None:
    cases = [
        ftt_table_8_row(document_type="ПР"),
        ftt_table_8_row(table_id="Table 9"),
        ftt_table_8_row(cells={}),
        ftt_table_8_row(include_cells=False),
    ]

    for item in cases:
        context = build_context(item)
        assert "Нормализованная семантика таблицы" not in context.primary_sources[0].text
        assert "table_header_semantics_applied" not in context.primary_sources[0].metadata
        assert context.diagnostics["table_header_semantics"]["applied"] is False
