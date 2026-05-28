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


def _bm25_with_expansion(rows: list[dict], expansion_config: dict) -> HybridRetriever:
    return HybridRetriever(
        vector_search=None,
        bm25_search=BM25SearchAdapter(rows),
        query_expander=QueryExpander(expansion_config),
    )


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


def test_bm25_prefers_cta_postgresql_chunk_over_logging_noise() -> None:
    rows = [
        {
            "text": "ЦТА. SIEM. Сервер Системы (логирование). Grafana Loki. Логи системы. Протокол HTTPS порт 443.",
            "metadata": {"document_type": "ЦТА", "relative_path": "docs/cta_logging.docx"},
        },
        {
            "text": "ЦТА. PostgreSQL - система управления базами данных, используется для хранения данных об объектах ПО АСУ-С.",
            "metadata": {"document_type": "ЦТА", "relative_path": "docs/cta_services.docx"},
        },
        {
            "text": "ЦТА. Patroni создает высокодоступный PostgreSQL кластер с поддержкой failover.",
            "metadata": {"document_type": "ЦТА", "relative_path": "docs/cta_postgresql.docx"},
        },
    ]

    results = BM25SearchAdapter(rows).search(
        "Что в ЦТА указано про PostgreSQL и его роль в архитектуре?",
        top_k=3,
    )

    assert results
    assert "postgresql" in results[0].text.lower()
    assert "grafana loki" not in results[0].text.lower()


def test_bm25_prefers_cta_minio_file_storage_over_log_storage() -> None:
    rows = [
        {
            "text": "ЦТА. Сервер Системы (логирование). Grafana Loki получает доступ к S3 Minio для сохранения логов.",
            "metadata": {"document_type": "ЦТА", "relative_path": "docs/cta_logging_s3.docx"},
        },
        {
            "text": "ЦТА. Minio S3 хранилище - высокопроизводительное объектное хранилище, используется для хранения файлов.",
            "metadata": {"document_type": "ЦТА", "relative_path": "docs/cta_minio.docx"},
        },
    ]

    results = BM25SearchAdapter(rows).search(
        "Что в ЦТА указано про MinIO S3 и хранение файлов?",
        top_k=2,
    )

    assert results
    assert "объектное хранилище" in results[0].text.lower()
    assert "хранения файлов" in results[0].text.lower()


def test_bm25_prefers_cta_kubernetes_service_chunk_over_non_cta_deploy_doc() -> None:
    rows = [
        {
            "text": "Руководство администратора. Развертывание сервисов через k8s.",
            "metadata": {"document_type": "Руководство", "relative_path": "docs/admin_guide.docx"},
        },
        {
            "text": "ЦТА. Kubernetes - платформа для автоматизации развертывания сервисов и управления контейнеризированными приложениями.",
            "metadata": {"document_type": "ЦТА", "relative_path": "docs/cta_kubernetes.docx"},
        },
        {
            "text": "ЦТА. Сервер Системы (логирование). Grafana Loki и SIEM. Логи системы.",
            "metadata": {"document_type": "ЦТА", "relative_path": "docs/cta_logging.docx"},
        },
    ]

    results = BM25SearchAdapter(rows).search(
        "Как в ЦТА описан Kubernetes-кластер и развертывание сервисов?",
        top_k=3,
    )

    assert results
    assert results[0].metadata.get("document_type") == "ЦТА"
    assert "kubernetes" in results[0].text.lower()


def test_bm25_prefers_pr_status_values_for_notice_status_query() -> None:
    rows = [
        {
            "text": "ПР. Управление замечаниями: операционный контроль. Создание, классификация, назначение, контроль сроков.",
            "metadata": {"document_type": "ПР", "relative_path": "docs/pr_smr.docx"},
        },
        {
            "text": "ПР. Параметр отчета: Статус. Источник данных: Карточка замечания, системный статус. Значения: «К устранению», «На проверке», «На доработке», «Просрочено», «Не устранено», «Устранено», «Аннулировано».",
            "metadata": {"document_type": "ПР", "relative_path": "docs/pr_smr.docx"},
        },
    ]
    retriever = _bm25_with_expansion(
        rows,
        {
            "pr_notice_statuses": {
                "triggers": ["статусы замечаний"],
                "expansions": ["статусная схема замечаний", "системный статус", "К устранению", "На проверке", "Аннулировано"],
            }
        },
    )

    results = retriever.search(
        "Какие статусы замечаний строительного контроля описаны в ПР?",
        top_k=2,
        mode="bm25",
    )

    assert results
    assert "значения:" in results[0].text.lower()
    assert "аннулировано" in results[0].text.lower()


def test_bm25_prefers_pr_annulment_process_for_annulment_query() -> None:
    rows = [
        {
            "text": "ПР. Закрытие замечания/ предписания. Подтверждение устранения. Статус «Устранено». Акт об устранении.",
            "metadata": {"document_type": "ПР", "relative_path": "docs/pr_smr.docx"},
        },
        {
            "text": "ПР. В карточке замечания нажимает «Аннулировать», если замечание признано необоснованным. Если «Аннулировать»: меняет статус на «Аннулировано», процесс по замечанию завершается.",
            "metadata": {"document_type": "ПР", "relative_path": "docs/pr_smr.docx"},
        },
    ]
    retriever = _bm25_with_expansion(
        rows,
        {
            "pr_notice_annulment": {
                "triggers": ["аннулирование"],
                "expansions": ["Аннулировать", "Аннулировано", "признано необоснованным", "процесс по замечанию завершается"],
            }
        },
    )

    results = retriever.search(
        "Что в ПР сказано про аннулирование замечаний строительного контроля?",
        top_k=2,
        mode="bm25",
    )

    assert results
    assert "аннулировать" in results[0].text.lower()
    assert "необоснованным" in results[0].text.lower()


def test_bm25_prefers_pr_roles_and_rights_chunks() -> None:
    rows = [
        {
            "text": "ПР. Закрытие замечания/ предписания. Подтверждение устранения. Роль исполнителя: пользователь.",
            "metadata": {"document_type": "ПР", "relative_path": "docs/pr_smr.docx"},
        },
        {
            "text": "ПР. Состав ролей, использующих функциональность данного модуля. Привилегированные: Куратор, Специалист технической поддержки. Непривилегированные: Инженер СК, Представитель ЛОС, Представитель подрядной организации.",
            "metadata": {"document_type": "ПР", "relative_path": "docs/pr_smr.docx"},
        },
        {
            "text": "ПР. Права доступа по ролям к объектам интерфейса пользователя, отчетам, регламентным заданиям, приведены в Приложение 1.",
            "metadata": {"document_type": "ПР", "relative_path": "docs/pr_smr.docx"},
        },
    ]
    retriever = _bm25_with_expansion(
        rows,
        {
            "pr_roles_rights": {
                "triggers": ["какие роли", "права доступа"],
                "expansions": ["состав ролей", "Привилегированные", "Непривилегированные", "Инженер СК", "Права доступа по ролям"],
            }
        },
    )

    role_results = retriever.search(
        "Какие роли предусмотрены в ПР для модуля строительного контроля?",
        top_k=3,
        mode="bm25",
    )
    rights_results = retriever.search(
        "Какие ограничения прав доступа для ролей строительного контроля описаны в ПР?",
        top_k=3,
        mode="bm25",
    )

    assert "непривилегированные" in role_results[0].text.lower()
    assert "права доступа по ролям" in rights_results[0].text.lower()
