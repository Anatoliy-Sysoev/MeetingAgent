from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.retrieval.bm25 import BM25SearchAdapter  # noqa: E402
from asu_june_bot.retrieval.hybrid import HybridRetriever  # noqa: E402
from asu_june_bot.retrieval.query_expansion import QueryExpander  # noqa: E402


def _bm25_retriever(rows: list[dict]) -> HybridRetriever:
    return HybridRetriever(
        vector_search=None,
        bm25_search=BM25SearchAdapter(rows),
        query_expander=QueryExpander(),
    )


def test_mvp2_005_expands_to_ftt_notification_sources() -> None:
    expanded, terms = QueryExpander().expand("Что в ФТТ сказано про уведомление контрагента о необходимости устранить замечание?")

    assert "4.2.6" in terms
    assert "СФТ 7" in terms
    assert "возможность рассылки уведомления контрагенту" in expanded


def test_mvp2_007_expands_to_ftt_analytics_and_dashboard_sources() -> None:
    expanded, terms = QueryExpander().expand("Что в ФТТ сказано про аналитику и дашборды строительного контроля?")

    assert "4.2.8" in terms
    assert "4.3" in terms
    assert "СФТ 12" in terms
    assert "динамика замечаний" in expanded


def test_mvp2_009_expands_to_ftt_cross_module_coding_sources() -> None:
    expanded, terms = QueryExpander().expand("Что ФТТ говорит про сквозное кодирование и связи между модулями?")

    assert "9.6" in terms
    assert "формирование связей между модулями" in expanded
    assert "тэгирования данных" in expanded


def test_mvp2_005_bm25_prefers_ftt_notification_requirement() -> None:
    rows = [
        {
            "text": "ФТТ. Общие требования к уведомлениям пользователей системы.",
            "metadata": {"document_type": "ФТТ", "relative_path": "docs/ftt.docx"},
        },
        {
            "text": "ФТТ. 4.2.6. Возможность рассылки уведомления контрагенту для вызова инспектора строительного контроля на объект для приёмки работ.",
            "metadata": {"document_type": "ФТТ", "relative_path": "docs/ftt.docx", "requirement_id": "4.2.6", "sections": ["4.2.6"]},
        },
        {
            "text": "ПМИ. СФТ 7. Проверка отправки уведомлений контрагенту о вызове инспектора и сопутствующих сообщений.",
            "metadata": {"document_type": "ПМИ", "relative_path": "docs/pmi.docx", "requirement_id": "4.2.6", "sections": ["4.2.6"]},
        },
    ]

    results = _bm25_retriever(rows).search(
        "Что в ФТТ сказано про уведомление контрагента о необходимости устранить замечание?",
        top_k=3,
        mode="bm25",
    )

    assert results
    assert results[0].metadata.get("requirement_id") == "4.2.6"
    assert "рассылки уведомления контрагенту" in results[0].text.lower()


def test_mvp2_007_bm25_prefers_ftt_dashboard_requirements() -> None:
    rows = [
        {
            "text": "ФТТ. Аналитические дашборды по функциональному направлению модуля ПИР.",
            "metadata": {"document_type": "ФТТ", "relative_path": "docs/ftt.docx", "requirement_id": "1.10", "sections": ["1.10"]},
        },
        {
            "text": "ФТТ. 4.2.8. Формирование аналитической информации по недостаткам/замечаниям по объектам/видам работ с автоматическим отслеживанием предписанных дат устранения.",
            "metadata": {"document_type": "ФТТ", "relative_path": "docs/ftt.docx", "requirement_id": "4.2.8", "sections": ["4.2.8"]},
        },
        {
            "text": "ФТТ. 4.3. Аналитические дашборды по функциональному направлению модуля: прогресс, аналитика.",
            "metadata": {"document_type": "ФТТ", "relative_path": "docs/ftt.docx", "requirement_id": "4.3", "sections": ["4.3"]},
        },
        {
            "text": "ПМИ. СФТ 12. Проверка аналитических дашбордов модуля Стройконтроль: динамика замечаний, распределение по статусам, рейтинг подрядчиков.",
            "metadata": {"document_type": "ПМИ", "relative_path": "docs/pmi.docx", "requirement_id": "4.3", "sections": ["4.3"]},
        },
    ]

    results = _bm25_retriever(rows).search(
        "Что в ФТТ сказано про аналитику и дашборды строительного контроля?",
        top_k=4,
        mode="bm25",
    )

    top_requirements = {str(result.metadata.get("requirement_id")) for result in results[:3]}
    assert {"4.2.8", "4.3"} & top_requirements
    assert results[0].metadata.get("requirement_id") in {"4.2.8", "4.3"}


def test_mvp2_009_bm25_prefers_ftt_96_cross_module_requirement() -> None:
    rows = [
        {
            "text": "ФТТ. 9.6. Формирование связей между модулями. Возможность сквозного кодирования, в том числе тэгирования данных.",
            "metadata": {"document_type": "ФТТ", "relative_path": "docs/ftt.docx", "requirement_id": "9.6", "sections": ["9.6"]},
        },
        {
            "text": "ПМИ. СНТ 6. Сквозная связность данных между модулями: переход к связанной работе или объекту строительства из карточки замечания.",
            "metadata": {"document_type": "ПМИ", "relative_path": "docs/pmi.docx", "requirement_id": "9.6", "sections": ["9.6"]},
        },
        {
            "text": "ПР. Модуль строительного контроля формирует акты проверки, предписания и акты устранения.",
            "metadata": {"document_type": "ПР", "relative_path": "docs/pr_smr.docx"},
        },
    ]

    results = _bm25_retriever(rows).search(
        "Что ФТТ говорит про сквозное кодирование и связи между модулями?",
        top_k=3,
        mode="bm25",
    )

    assert results
    assert results[0].metadata.get("requirement_id") == "9.6"
    assert "сквозного кодирования" in results[0].text.lower() or "сквозное кодирование" in results[0].text.lower()
