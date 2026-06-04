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


def result(
    source_id: str,
    text: str,
    *,
    document_type: str = "СоИ AD",
    score: float = 1.0,
    chunk_index: int = 1,
    matched_by: list[str] | None = None,
    relative_path: str = "doc.md",
    title: str | None = None,
    diagnostics: dict | None = None,
) -> SearchResult:
    return SearchResult(
        source_id=source_id,
        text=text,
        score=score,
        vector_score=None,
        bm25_score=score,
        matched_by=matched_by or ["bm25"],
        metadata={
            "chunk_id": source_id,
            "relative_path": relative_path,
            "document_type": document_type,
            "chunk_index": chunk_index,
            "section": "Авторизация",
            "title": title,
        },
        diagnostics=diagnostics or {},
    )


def integration_intent() -> QueryIntentResult:
    return QueryIntentResult(intent=QueryIntent.INTEGRATION_OVERVIEW, confidence=0.88, is_project_related=True)


def test_context_builder_demotes_weak_primary_candidate_to_supporting() -> None:
    weak = result("weak", "Рисунок 1. UML: PROJECT -> AD -> PROJECT", score=10.0, chunk_index=1)
    strong = result(
        "strong",
        "Интеграция с Active Directory используется для получения актуального перечня пользователей на основании членства в группах безопасности. " * 4,
        score=5.0,
        chunk_index=2,
    )

    context = ContextBuilder(primary_limit=2, supporting_limit=3, enable_parent_expansion=False).build(
        "СоИ AD как происходит авторизация пользователей?",
        integration_intent(),
        [weak, strong],
        [],
    )

    assert [item.metadata["chunk_id"] for item in context.primary_sources] == ["strong"]
    assert "weak" in [item.metadata["chunk_id"] for item in context.supporting_sources]
    assert context.diagnostics["source_quality_filter"]["source_quality_excluded_primary"] == 1


def test_context_builder_parent_expands_weak_supporting_source() -> None:
    weak = result("weak", "Рисунок 1. UML: PROJECT -> AD -> PROJECT", score=10.0, chunk_index=1)
    neighbor = result(
        "neighbor",
        "Диаграмма относится к разделу, где описано получение пользователей из групп безопасности Active Directory. " * 4,
        score=5.0,
        chunk_index=2,
    )

    context = ContextBuilder(primary_limit=1, supporting_limit=3, enable_parent_expansion=True).build(
        "СоИ AD как происходит авторизация пользователей?",
        integration_intent(),
        [weak, neighbor],
        [],
    )

    supporting_text = "\n".join(item.text for item in context.supporting_sources)
    assert "Active Directory" in supporting_text
    assert context.diagnostics["parent_expansion"]["supporting"]["expanded_count"] >= 1


def test_context_builder_keeps_nsi_regulation_doc_as_primary_for_inventory_query() -> None:
    regulation = result(
        "regulation",
        "РЕГЛАМЕНТ ВЕДЕНИЯ СПРАВОЧНИКА «РЕЕСТР НОРМАТИВНЫХ ДОКУМЕНТОВ». СОДЕРЖАНИЕ 1. ОБЩИЕ ПОЛОЖЕНИЯ.",
        document_type="Методика/Регламент НСИ",
        relative_path="Этап 1.1/10. Регламент ведения объекта НСИ/Регламент_ведения_данных_справочника_РЕЕСТР_НОРМАТИВНЫХ_ДОКУМЕНТОВ.docx",
        title="Регламент_ведения_данных_справочника_РЕЕСТР_НОРМАТИВНЫХ_ДОКУМЕНТОВ.docx",
        score=10.0,
    )
    registry_note = result(
        "note",
        "Документ: Реестр замечаний. Наименование документа: Регламент ведения объекта НСИ.",
        document_type="Методика/Регламент НСИ",
        relative_path="Этап 1.1/10. Регламент ведения объекта НСИ/Реестр_замечаний.xlsx",
        title="Реестр замечаний",
        score=9.0,
    )

    context = ContextBuilder(primary_limit=2, supporting_limit=3, enable_parent_expansion=False).build(
        "Какие регламенты ведения объектов НСИ есть в корпусе?",
        QueryIntentResult(intent=QueryIntent.GENERAL_PROJECT_QUESTION, confidence=0.72, is_project_related=True),
        [regulation, registry_note],
        [],
    )

    assert [item.metadata["chunk_id"] for item in context.primary_sources] == ["regulation"]
    assert "note" in [item.metadata["chunk_id"] for item in context.supporting_sources]


def test_context_builder_promotes_nsi_reference_table_even_if_vector_only() -> None:
    soi_table = result(
        "soi-table8",
        "Документ: СоИ Справочники. Таблица: Table 8. Справочники: Единицы измерения; Должности; Отделы; Контрагенты; Организации; Объекты строительства.",
        document_type="СоИ Справочники",
        matched_by=["vector"],
        relative_path="Этап 1.1/11. Соглашения об интеграции для интерфейсов/PROJECT SYSTEM_СоИ_Справочники_v2.2.1.docx",
        title="Цели и задачи интеграции",
        score=1.0,
    )
    ftt = result(
        "ftt",
        "Требования к нормативно-справочной информации. Корпоративный реестр НСИ.",
        document_type="ФТТ",
        matched_by=["vector"],
        relative_path="ФТТ.docx",
        title="Требования к нормативно-справочной информации",
        score=1.2,
    )

    context = ContextBuilder(primary_limit=2, supporting_limit=3, enable_parent_expansion=False).build(
        "Какие справочники НСИ перечислены в корпусе?",
        QueryIntentResult(intent=QueryIntent.GENERAL_PROJECT_QUESTION, confidence=0.72, is_project_related=True),
        [ftt, soi_table],
        [],
    )

    assert [item.metadata["chunk_id"] for item in context.primary_sources] == ["soi-table8"]
    assert "ftt" in [item.metadata["chunk_id"] for item in context.supporting_sources]


def test_context_builder_promotes_passport_related_documents_table() -> None:
    related_docs = result(
        "passport-table2",
        "Документ: Паспорт ИС. Таблица: Table 2. Связанные документы (этот документ должен читаться вместе с). Название документа: Целевая техническая архитектура (ЦТА). Номер версии /Имя файла: 1./ЦТА_PROJECT_SYSTEM_Этап_1.",
        document_type="Паспорт ИС",
        relative_path="Этап 1.2/8. Паспорт информационной системы/PROJECT SYSTEM_Паспорт ИС_v1.3.3.docx",
        title="Связанные документы",
        score=4.0,
        diagnostics={"rerank_labels": ["boost:passport_related_documents"]},
    )
    scope = result(
        "passport-scope",
        "Настоящий Паспорт ИС подготовлен для информационной системы PROJECT SYSTEM. В границы описания включены архитектурные и эксплуатационные сведения.",
        document_type="Паспорт ИС",
        relative_path="Этап 1.2/8. Паспорт информационной системы/PROJECT SYSTEM_Паспорт ИС_v1.3.3.docx",
        title="Границы описания",
        score=10.0,
    )

    context = ContextBuilder(primary_limit=2, supporting_limit=3, enable_parent_expansion=False).build(
        "Что входит в Паспорт ИС и какие связанные документы в нём указаны?",
        QueryIntentResult(intent=QueryIntent.DOCUMENT_OVERVIEW, confidence=0.88, is_project_related=True),
        [scope, related_docs],
        [],
    )

    assert "passport-table2" in [item.metadata["chunk_id"] for item in context.primary_sources]


def test_context_builder_promotes_passport_appendices_table() -> None:
    appendices = result(
        "passport-table3",
        "Документ: Паспорт ИС. Таблица: Table 3. Приложение №1 План послеаварийного восстановления. Приложение №2 Список источников.",
        document_type="Паспорт ИС",
        relative_path="Этап 1.2/8. Паспорт информационной системы/PROJECT SYSTEM_Паспорт ИС_v1.3.3.docx",
        title="Приложения",
        score=4.0,
        diagnostics={"rerank_labels": ["boost:passport_appendices"]},
    )
    support_noise = result(
        "passport-support",
        "Документ: Паспорт ИС. Роль: Поддержка приложения. Регламентные операции.",
        document_type="Паспорт ИС",
        relative_path="Этап 1.2/8. Паспорт информационной системы/PROJECT SYSTEM_Паспорт ИС_v1.3.3.docx",
        title="Услуга по поддержке",
        score=10.0,
    )

    context = ContextBuilder(primary_limit=2, supporting_limit=3, enable_parent_expansion=False).build(
        "Какие приложения перечислены в Паспорте ИС?",
        QueryIntentResult(intent=QueryIntent.DOCUMENT_OVERVIEW, confidence=0.88, is_project_related=True),
        [support_noise, appendices],
        [],
    )

    assert "passport-table3" in [item.metadata["chunk_id"] for item in context.primary_sources]


def test_context_builder_promotes_passport_system_purpose() -> None:
    purpose = result(
        "passport-purpose",
        "Основное назначение системы: Система предназначена для формирования единой информационной среды для автоматизации и цифровизации бизнес-процессов управления строительными проектами.",
        document_type="Паспорт ИС",
        relative_path="Этап 1.2/8. Паспорт информационной системы/PROJECT SYSTEM_Паспорт ИС_v1.3.3.docx",
        title="Описание и область применения",
        score=4.0,
        diagnostics={"rerank_labels": ["boost:passport_system_purpose", "boost:passport_exact_system_purpose"]},
    )
    support_noise = result(
        "passport-integration",
        "Документ: Паспорт ИС. Таблица: Table 23. Параметр интеграции: Область применения. Описание: Все контуры системы.",
        document_type="Паспорт ИС",
        relative_path="Этап 1.2/8. Паспорт информационной системы/PROJECT SYSTEM_Паспорт ИС_v1.3.3.docx",
        title="Информация по интеграции",
        score=10.0,
    )

    context = ContextBuilder(primary_limit=2, supporting_limit=3, enable_parent_expansion=False).build(
        "Какие сведения о системе и назначении ИС указаны в Паспорте ИС?",
        QueryIntentResult(intent=QueryIntent.DOCUMENT_OVERVIEW, confidence=0.88, is_project_related=True),
        [support_noise, purpose],
        [],
    )

    assert "passport-purpose" in [item.metadata["chunk_id"] for item in context.primary_sources]
