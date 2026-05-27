from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.retrieval.bm25 import BM25SearchAdapter  # noqa: E402


def test_bm25_prefers_ad_role_mapping_chunk_for_app_ccpm_query() -> None:
    rows = [
        {
            "text": "Справочник групп AD пользователя. Атрибут groups. app_ccpm_inspector. Роли строительного контроля.",
            "metadata": {"document_type": "СоИ AD", "relative_path": "docs/soi_ad.docx"},
        },
        {
            "text": "Интеграция с AD через LDAPS. Учетные записи и синхронизация пользователей.",
            "metadata": {"document_type": "СоИ AD", "relative_path": "docs/soi_ad.docx"},
        },
    ]

    results = BM25SearchAdapter(rows).search(
        "Какие группы AD app_ccpm используются для ролей строительного контроля?",
        top_k=2,
    )

    assert len(results) == 2
    assert "app_ccpm" in results[0].text.lower()
    assert "роли строительного контроля" in results[0].text.lower()


def test_bm25_includes_regulation_doc_for_nsi_regulations_query() -> None:
    rows = [
        {
            "text": "Реестр объектов НСИ. Содержит перечень объектов и справочников.",
            "metadata": {"document_type": "Реестр НСИ", "relative_path": "docs/nsi_register.xlsx"},
        },
        {
            "text": "Методика ведения объекта НСИ. Регламент ведения объекта НСИ и правила поддержки.",
            "metadata": {"document_type": "Методика/Регламент НСИ", "relative_path": "docs/nsi_mvd.docx"},
        },
        {
            "text": "ФТТ по проекту. Общие требования.",
            "metadata": {"document_type": "ФТТ", "relative_path": "docs/ftt.docx"},
        },
    ]

    results = BM25SearchAdapter(rows).search(
        "Какие регламенты ведения объектов НСИ есть в корпусе?",
        top_k=3,
    )

    top_doc_types = [str(result.metadata.get("document_type") or "") for result in results[:2]]
    assert "Методика/Регламент НСИ" in top_doc_types


def test_bm25_prefers_cta_recovery_chunk_over_logging_chunk() -> None:
    rows = [
        {
            "text": "ЦТА. Grafana Loki и SIEM. Логирование, мониторинг, порты интеграции, сетевые настройки.",
            "metadata": {"document_type": "ЦТА", "relative_path": "docs/cta_logging.docx"},
        },
        {
            "text": "ЦТА. Максимальное время восстановления после сбоя (RTO) - 4 часа. RPO - 4 часа. Резервное копирование и восстановление данных.",
            "metadata": {"document_type": "ЦТА", "relative_path": "docs/cta_recovery.docx"},
        },
        {
            "text": "ФТТ. Требования по производительности и экспорту.",
            "metadata": {"document_type": "ФТТ", "relative_path": "docs/ftt.docx"},
        },
    ]

    results = BM25SearchAdapter(rows).search(
        "Что указано в ЦТА про RTO и RPO?",
        top_k=3,
    )

    assert results
    assert "rto" in results[0].text.lower()
    assert "rpo" in results[0].text.lower()
    assert "резервное копирование" in results[0].text.lower()
