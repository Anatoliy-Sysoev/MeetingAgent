from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.retrieval.context_builder import ContextBuilder  # noqa: E402
from asu_june_bot.retrieval.models import SearchResult  # noqa: E402
from asu_june_bot.retrieval.query_intent import QueryIntent, QueryIntentResult  # noqa: E402


def _result(
    source_id: str,
    text: str,
    *,
    document_type: str = "Прочее",
    matched_by: list[str] | None = None,
    diagnostics: dict | None = None,
    section: str = "Общие сведения",
    table_id: str | None = None,
    row_index: int | None = None,
) -> SearchResult:
    metadata = {
        "chunk_id": source_id,
        "relative_path": "public-fixture.md",
        "document_type": document_type,
        "chunk_index": 1,
        "section": section,
        "title": "Public fixture",
    }
    if table_id is not None:
        metadata["table_id"] = table_id
    if row_index is not None:
        metadata["row_index"] = row_index
    return SearchResult(
        source_id=source_id,
        text=text,
        score=1.0,
        vector_score=1.0 if matched_by == ["vector"] else None,
        bm25_score=1.0 if matched_by != ["vector"] else None,
        matched_by=matched_by or ["bm25"],
        metadata=metadata,
        diagnostics=diagnostics or {},
    )


def _intent(kind: QueryIntent, *, sections: list[str] | None = None) -> QueryIntentResult:
    return QueryIntentResult(
        intent=kind,
        confidence=0.9,
        is_project_related=True,
        mentioned_sections=sections or [],
    )


@pytest.mark.parametrize(
    ("query", "intent", "item", "expected"),
    [
        (
            "Обзор проекта",
            _intent(QueryIntent.GENERAL_PROJECT_QUESTION),
            _result(
                "noise",
                "Служебная обложка",
                diagnostics={"rerank_labels": ["penalty:front_matter"]},
            ),
            "excluded",
        ),
        (
            "Какие связанные документы указаны в Паспорте ИС?",
            _intent(QueryIntent.DOCUMENT_OVERVIEW),
            _result(
                "related",
                "Таблица: Table 2. Название документа: ЦТА. Номер версии: 1.0.",
                document_type="Паспорт ИС",
            ),
            "primary",
        ),
        (
            "Какие связанные документы указаны в Паспорте ИС?",
            _intent(QueryIntent.DOCUMENT_OVERVIEW),
            _result("other-passport", "Иные сведения", document_type="Паспорт ИС"),
            "supporting",
        ),
        (
            "Какие приложения перечислены в Паспорте ИС?",
            _intent(QueryIntent.DOCUMENT_OVERVIEW),
            _result(
                "appendix",
                "Таблица: Table 3. Приложение №1. План послеаварийного восстановления.",
                document_type="Паспорт ИС",
            ),
            "primary",
        ),
        (
            "Каково назначение ИС в Паспорте ИС?",
            _intent(QueryIntent.DOCUMENT_OVERVIEW),
            _result("purpose", "Основное назначение системы", document_type="Паспорт ИС"),
            "primary",
        ),
        (
            "Дайте обзор документа",
            _intent(QueryIntent.DOCUMENT_OVERVIEW),
            _result(
                "overview",
                "Настоящий паспорт ИС подготовлен. В границы описания включены сведения.",
                document_type="Паспорт ИС",
            ),
            "primary",
        ),
        (
            "Как устроена интеграция?",
            _intent(QueryIntent.INTEGRATION_OVERVIEW),
            _result("integration", "Интеграционный поток", document_type="СоИ AD"),
            "primary",
        ),
        (
            "Как устроена интеграция?",
            _intent(QueryIntent.INTEGRATION_OVERVIEW),
            _result(
                "integration-vector",
                "Интеграционный поток",
                document_type="СоИ AD",
                matched_by=["vector"],
            ),
            "supporting",
        ),
        (
            "Как устроена интеграция?",
            _intent(QueryIntent.INTEGRATION_OVERVIEW),
            _result("integration-pr", "Проектное решение", document_type="ПР"),
            "supporting",
        ),
        (
            "Каковы RTO и RPO?",
            _intent(QueryIntent.CTA_RECOVERY_RTO_RPO),
            _result("cta-rto", "RTO: 4 часа. RPO: 1 час.", document_type="ЦТА"),
            "primary",
        ),
        (
            "Каковы RTO и RPO?",
            _intent(QueryIntent.CTA_RECOVERY_RTO_RPO),
            _result("cta-general", "Общая архитектура", document_type="ЦТА"),
            "supporting",
        ),
        (
            "Что требует пункт 4.2.5?",
            _intent(QueryIntent.REQUIREMENT_LOOKUP, sections=["4.2.5"]),
            _result("exact-ftt", "Точное требование", document_type="ФТТ", section="4.2.5"),
            "primary",
        ),
        (
            "Что требует пункт 4.2.5?",
            _intent(QueryIntent.REQUIREMENT_LOOKUP, sections=["4.2.5"]),
            _result("adjacent-ftt", "Смежное требование", document_type="ФТТ", section="4.2.6"),
            "supporting",
        ),
        (
            "Какие требования действуют?",
            _intent(QueryIntent.REQUIREMENT_LOOKUP),
            _result(
                "labelled-ftt",
                "Требование",
                document_type="ФТТ",
                matched_by=["vector"],
                diagnostics={"rerank_labels": ["boost:exact_section_mention"]},
            ),
            "primary",
        ),
        (
            "Какие регламенты ведения НСИ действуют?",
            _intent(QueryIntent.GENERAL_PROJECT_QUESTION),
            _result(
                "nsi-regulation",
                "Регламент ведения справочника. Общие положения и правила ведения.",
                document_type="Методика/Регламент НСИ",
            ),
            "primary",
        ),
        (
            "Какие справочники НСИ перечислены?",
            _intent(QueryIntent.GENERAL_PROJECT_QUESTION),
            _result(
                "nsi-reference",
                "Таблица: Table 8. Справочники: организации, контрагенты.",
                document_type="СоИ Справочники",
            ),
            "primary",
        ),
        (
            "Общий вопрос по проекту",
            _intent(QueryIntent.GENERAL_PROJECT_QUESTION),
            _result("general", "Подтверждённый проектный факт"),
            "primary",
        ),
        (
            "Общий вопрос по проекту",
            _intent(QueryIntent.GENERAL_PROJECT_QUESTION),
            _result("general-vector", "Семантический кандидат", matched_by=["vector"]),
            "supporting",
        ),
        (
            "Непроектный вопрос",
            _intent(QueryIntent.OUT_OF_SCOPE_CANDIDATE),
            _result("out", "Нерелевантный фрагмент"),
            "excluded",
        ),
    ],
    ids=[
        "noise",
        "passport-related-primary",
        "passport-related-supporting",
        "passport-appendix-primary",
        "passport-purpose-primary",
        "document-overview-primary",
        "integration-primary",
        "integration-vector-supporting",
        "integration-pr-supporting",
        "cta-recovery-primary",
        "cta-general-supporting",
        "requirement-exact-primary",
        "requirement-adjacent-supporting",
        "requirement-label-primary",
        "nsi-regulation-primary",
        "nsi-reference-primary",
        "general-primary",
        "general-vector-supporting",
        "out-of-scope-excluded",
    ],
)
def test_bucket_policy_characterization(
    query: str,
    intent: QueryIntentResult,
    item: SearchResult,
    expected: str,
) -> None:
    builder = ContextBuilder(enable_source_quality_filter=False, enable_parent_expansion=False)

    assert builder._bucket(query, intent, item) == expected


def test_passport_table_expansion_combines_rows_in_source_order() -> None:
    first = _result(
        "table-2-row-1",
        "Таблица: Table 2. Название документа: ЦТА. Номер версии: 1.0.",
        document_type="Паспорт ИС",
        table_id="Table 2",
        row_index=1,
    )
    second = _result(
        "table-2-row-2",
        "Таблица: Table 2. Название документа: ФТТ. Номер версии: 2.0.",
        document_type="Паспорт ИС",
        table_id="Table 2",
        row_index=2,
    )
    context = ContextBuilder(
        enable_source_quality_filter=False,
        enable_parent_expansion=False,
        table_header_maps={},
    ).build(
        "Какие связанные документы указаны в Паспорте ИС?",
        _intent(QueryIntent.DOCUMENT_OVERVIEW),
        [second, first],
    )

    assert len(context.primary_sources) == 1
    assert "Название документа: ЦТА" in context.primary_sources[0].text
    assert "Название документа: ФТТ" in context.primary_sources[0].text
    assert context.primary_sources[0].text.index("ЦТА") < context.primary_sources[0].text.index(
        "ФТТ"
    )
    assert context.diagnostics["passport_table_expansion"] == {
        "applied": True,
        "table_id": "Table 2",
        "expanded_count": 2,
        "expanded_keys": ["table-2-row-1", "table-2-row-2"],
    }
