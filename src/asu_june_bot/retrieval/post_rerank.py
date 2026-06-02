from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Any

from .models import SearchResult
from .query_intent import QueryIntent, QueryIntentResult


SECTION_RE = re.compile(r"(?<!\d)(\d+(?:\.\d+){1,5})(?:\.|\b)")


@dataclass(slots=True)
class RerankResult:
    results: list[SearchResult]
    excluded: list[SearchResult] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)


def _text(result: SearchResult) -> str:
    return " ".join((result.text or "").lower().split())


def _doc_type(result: SearchResult) -> str:
    return str(result.metadata.get("document_type") or "")


def _path(result: SearchResult) -> str:
    return str(result.metadata.get("relative_path") or "")


def _chunk_id(result: SearchResult) -> str:
    return str(result.metadata.get("chunk_id") or f"{_path(result)}#{result.metadata.get('chunk_index')}")


def _is_vector_only(result: SearchResult) -> bool:
    return "vector" in result.matched_by and "bm25" not in result.matched_by


def _is_bm25_vector(result: SearchResult) -> bool:
    return "vector" in result.matched_by and "bm25" in result.matched_by


def _is_glossary_or_front_matter(text: str) -> bool:
    return any(
        marker in text
        for marker in [
            "контекст: глоссарий",
            "используемые сокращения",
            "история изменений",
            "связанные документы",
            "таблица 1 заголовки: версия",
        ]
    )


def _is_software_or_support_table(text: str) -> bool:
    return any(
        marker in text
        for marker in [
            "контекст: программное обеспечение информационной системы",
            "заголовки: наименование по | тип по",
            "postgresql | open source",
            "kubernetes",
            "nginx",
            "операционная система серверов",
            "служба технической поддержки",
            "поддержка пользователей",
            "поддержка приложения",
            "устранение ошибок",
            "доработка приложения",
            "требования к квалификации и численности сотрудников",
            "сотрудников, обслуживающих систему",
            "роль | минимальные требования",
        ]
    )


def _has_passport_route(query_lower: str) -> bool:
    return any(
        marker in query_lower
        for marker in (
            "паспорт ис",
            "паспорте ис",
            "паспорта ис",
            "паспорт информационной системы",
        )
    )


def _is_passport_related_docs_query(query_lower: str) -> bool:
    return "связанн" in query_lower and "документ" in query_lower


def _is_passport_appendices_query(query_lower: str) -> bool:
    return any(marker in query_lower for marker in ("какие приложения", "приложения перечислены", "приложения в паспорте", "приложения паспорта"))


def _is_passport_system_purpose_query(query_lower: str) -> bool:
    return any(
        marker in query_lower
        for marker in (
            "сведения о системе",
            "назначение ис",
            "назначении ис",
            "назначение системы",
            "описание системы",
            "область применения",
        )
    )


def _is_passport_related_docs_chunk(text: str) -> bool:
    return (
        "таблица: table 2" in text
        and "название документа" in text
        and ("номер версии" in text or "имя файла" in text)
    ) or "связанные документы (этот документ должен читаться вместе с)" in text


def _is_passport_appendices_chunk(text: str) -> bool:
    return (
        "таблица: table 3" in text
        and ("приложение №" in text or "план послеаварийного восстановления" in text or "список источников" in text)
    ) or "приложения (являются неотъемлемой частью документа)" in text


def _is_passport_system_purpose_chunk(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "полное наименование описываемой системы",
            "краткое наименование описываемой системы",
            "основное назначение системы",
            "система предназначена для формирования единой информационной среды",
            "описание системы и область применения",
            "описание и область применения",
            "область применения: пао",
        )
    )


def _is_ad_role_mapping_chunk(text: str) -> bool:
    has_group_anchor = "app_ccpm" in text or "справочник групп ad" in text or "группы ad пользователя" in text
    has_role_anchor = "роль" in text or "роли строительного контроля" in text or "строительного контроля" in text
    has_groups_attr = "groups" in text or "атрибут groups" in text
    return has_group_anchor and (has_role_anchor or has_groups_attr)


def _is_nsi_regulation_chunk(text: str) -> bool:
    return any(marker in text for marker in ("регламент ведения", "методика ведения", "мвд", "ведение объекта нси"))


def _has_nsi_regulation_route(query_lower: str) -> bool:
    return any(
        marker in query_lower
        for marker in (
            "регламент ведения",
            "регламенты ведения",
            "регламентные документы",
            "методика/регламент",
            "методики ведения",
            "методика ведения",
            "правила ведения",
            "мвд",
        )
    )


def _has_nsi_reference_route(query_lower: str) -> bool:
    return any(
        marker in query_lower
        for marker in (
            "какие справочники нси",
            "справочники нси",
            "справочник нси",
            "реестр нси",
            "реестр объектов нси",
            "атрибутные составы",
            "атрибутный состав",
            "модель данных нси",
            "маппинг справочников",
            "маппинг атрибутов",
            "свок рд",
        )
    )


def _is_nsi_reference_chunk(text: str) -> bool:
    dictionary_names = (
        "единицы измерения",
        "должности",
        "отделы",
        "контрагенты",
        "организации",
        "объекты строительства",
        "виды прикрепляемых документов",
        "договоры",
        "инвестиционные проекты",
    )
    return (
        ("справочники:" in text and any(name in text for name in dictionary_names))
        or "атрибутный состав" in text
        or "атрибутивный состав" in text
        or "модель данных нси" in text
        or "реестр объектов нси" in text
        or "реестр используемых объектов нси" in text
        or "корпоративный реестр нси" in text
        or ("table 8" in text and "справочники" in text)
    )


def _is_cta_recovery_chunk(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "время восстановления",
            "максимальное время восстановления",
            "rto",
            "rpo",
            "точка восстановления",
            "окно потери данных",
            "резервное копирование",
            "backup",
            "restore",
            "восстановление данных",
            "аварийный режим",
        )
    )


def _is_logging_or_port_chunk(text: str) -> bool:
    has_logging_noise = any(marker in text for marker in ("grafana loki", "siem", "логирован", "мониторинг", "otel", "otlp"))
    has_port_noise = "порт " in text or "tcp/" in text or "udp/" in text
    return has_logging_noise or has_port_noise


def _is_cta_logging_noise_chunk(text: str) -> bool:
    has_logging_noise = any(
        marker in text
        for marker in (
            "grafana loki",
            "siem",
            "сервер системы (логирование)",
            "сервер логирования",
            "логи системы",
            "кластером логирования",
            "журналирования",
        )
    )
    has_file_storage_signal = any(marker in text for marker in ("сохранение файлов", "хранение файлов", "объектное хранилище"))
    return has_logging_noise and not has_file_storage_signal


def _is_cta_postgresql_chunk(text: str) -> bool:
    if "postgresql" not in text:
        return False
    return any(
        marker in text
        for marker in (
            "система управления базами данных",
            "субд postgresql",
            "кластер серверов postgresql",
            "postgresql кластер",
            "patroni",
            "consul",
            "хранения данных",
            "доступ к базе данных",
        )
    )


def _is_cta_minio_storage_chunk(text: str) -> bool:
    if "minio" not in text and "s3" not in text:
        return False
    return any(
        marker in text
        for marker in (
            "объектное хранилище",
            "хранения файлов",
            "хранение файлов",
            "сохранение файлов",
            "s3 хранилищ",
            "s3-протокол",
            "бакет",
        )
    )


def _is_cta_kubernetes_chunk(text: str) -> bool:
    if "kubernetes" not in text and "k8s" not in text:
        return False
    return any(
        marker in text
        for marker in (
            "развертыван",
            "оркестрац",
            "запуск сервисов",
            "запуск слоя управления",
            "контейнер",
            "k8s-master",
            "k8s-worker",
        )
    )


def _pr_status_count(text: str) -> int:
    status_markers = (
        "к устранению",
        "на проверке",
        "на доработке",
        "просрочено",
        "не устранено",
        "устранено",
        "аннулировано",
    )
    return sum(1 for marker in status_markers if marker in text)


def _is_pr_status_values_chunk(text: str) -> bool:
    status_count = _pr_status_count(text)
    has_values_list = "значения:" in text and "статус" in text and status_count >= 5
    has_status_scheme = "статусная схема замечаний" in text and status_count >= 2
    return has_values_list or has_status_scheme


def _is_pr_status_transition_chunk(text: str) -> bool:
    if _pr_status_count(text) < 2:
        return False
    return any(
        marker in text
        for marker in (
            "меняет статус замечания",
            "изменяет статус замечания",
            "статус замечания",
            "карточке замечания нажимает",
        )
    )


def _is_pr_annulment_chunk(text: str) -> bool:
    if "аннулир" not in text:
        return False
    return any(
        marker in text
        for marker in (
            "признано необоснованным",
            "необоснованности замечания",
            "процесс по замечанию завершается",
            "может его аннулировать",
            "кнопку «аннулировать»",
            "кнопку \"аннулировать\"",
        )
    )


def _is_pr_role_composition_chunk(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "состав ролей, использующих функциональность данного модуля",
            "привилегированные:",
            "непривилегированные:",
        )
    )


def _is_pr_role_access_chunk(text: str) -> bool:
    role_markers = (
        "куратор проекта нул",
        "инженер ск",
        "представитель лос",
        "специалист технической поддержки",
        "специалист информационной безопасности",
        "аудитор нул",
    )
    has_role = any(marker in text for marker in role_markers)
    has_access_word = "право доступа" in text or "права доступа" in text or "ограничения" in text
    has_matrix_values = "тип объекта: ск:" in text and any(marker in text for marker in ("просмотр", "изменение", "создание", "удаление", "нет"))
    return (
        "права доступа по ролям" in text
        or "объектам интерфейса пользователя" in text
        or "регламентным заданиям" in text
        or (has_role and (has_access_word or has_matrix_values))
    )


def _is_pr_generic_process_chunk(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "управление замечаниями: операционный контроль",
            "управление замечаниями: эскалация",
            "закрытие замечания/ предписания",
            "автоматическая генерация инспекционных документов",
            "акт об устранении: формируется автоматически",
            "роль исполнителя:",
        )
    )


def _is_pr_construction_control_document(result: SearchResult) -> bool:
    path = _path(result).lower()
    return "строительн" in path and "контрол" in path


def _has_exact_section(result: SearchResult, sections: list[str]) -> bool:
    if not sections:
        return False
    result_sections = {str(item) for item in (result.metadata.get("sections") or [])}
    requirement_id = str(result.metadata.get("requirement_id") or "")
    text = result.text or ""
    for section in sections:
        if section in result_sections or section == requirement_id:
            return True
        if re.search(rf"(?<!\d){re.escape(section)}(?:\.|\b)", text):
            return True
    return False


def _dedup_key(result: SearchResult) -> str:
    path = _path(result).lower()
    chunk_index = result.metadata.get("chunk_index")
    # Keep different chunks, but collapse exact duplicated chunk ids only.
    return str(result.metadata.get("chunk_id") or f"{path}#{chunk_index}")


class PostReranker:
    def rerank(self, query: str, intent: QueryIntentResult, results: list[SearchResult], top_k: int | None = None) -> RerankResult:
        adjusted: list[SearchResult] = []
        excluded: list[SearchResult] = []
        seen: set[str] = set()

        for result in results:
            key = _dedup_key(result)
            if key in seen:
                excluded.append(self._with_rerank(result, 0.0, ["excluded:duplicate_chunk"]))
                continue
            seen.add(key)

            labels: list[str] = []
            multiplier = 1.0
            text = _text(result)
            document_type = _doc_type(result)

            if _is_bm25_vector(result):
                multiplier *= 1.12
                labels.append("boost:matched_by_bm25_and_vector")

            if _is_vector_only(result):
                if intent.intent in {QueryIntent.DOCUMENT_OVERVIEW, QueryIntent.REQUIREMENT_LOOKUP}:
                    multiplier *= 0.42
                    labels.append("penalty:vector_only_for_exact_or_overview")
                else:
                    multiplier *= 0.82
                    labels.append("penalty:vector_only")

            if intent.intent == QueryIntent.DOCUMENT_OVERVIEW:
                if document_type == "Паспорт ИС" and "паспорт" in query.lower():
                    multiplier *= 1.55
                    labels.append("boost:document_overview_passport")
                if _is_software_or_support_table(text):
                    multiplier *= 0.08
                    labels.append("penalty:software_or_support_table_for_overview")
                if _is_glossary_or_front_matter(text):
                    multiplier *= 0.28
                    labels.append("penalty:front_matter_or_glossary_for_overview")
                if any(marker in text for marker in ["в границы описания включены", "настоящий паспорт ис подготовлен", "архитектурные и эксплуатационные сведения"]):
                    multiplier *= 1.8
                    labels.append("boost:overview_scope_chunk")

            query_lower = query.lower()
            has_passport_route = _has_passport_route(query_lower)
            if has_passport_route:
                if document_type == "Паспорт ИС":
                    multiplier *= 1.35
                    labels.append("boost:passport_route")
                    if _is_passport_related_docs_query(query_lower):
                        if _is_passport_related_docs_chunk(text):
                            multiplier *= 4.8
                            labels.append("boost:passport_related_documents")
                        elif _is_software_or_support_table(text):
                            multiplier *= 0.22
                            labels.append("penalty:passport_support_noise_for_related_docs")
                    if _is_passport_appendices_query(query_lower):
                        if _is_passport_appendices_chunk(text):
                            multiplier *= 5.4
                            labels.append("boost:passport_appendices")
                        elif _is_software_or_support_table(text):
                            multiplier *= 0.08
                            labels.append("penalty:passport_support_noise_for_appendices")
                    if _is_passport_system_purpose_query(query_lower):
                        if _is_passport_system_purpose_chunk(text) or any(marker in text for marker in ["в границы описания включены", "настоящий паспорт ис подготовлен"]):
                            multiplier *= 4.0
                            labels.append("boost:passport_system_purpose")
                            if "система предназначена для формирования единой информационной среды" in text:
                                multiplier *= 5.0
                                labels.append("boost:passport_exact_system_purpose")
                        elif _is_software_or_support_table(text):
                            multiplier *= 0.22
                            labels.append("penalty:passport_support_noise_for_purpose")
                elif document_type in {"ФТТ", "ПР", "ЦТА", "СоИ AD", "СоИ Справочники"}:
                    multiplier *= 0.42
                    labels.append("penalty:passport_other_doc_type")

            if intent.intent == QueryIntent.INTEGRATION_OVERVIEW:
                if document_type in {"ЦТА", "Паспорт ИС", "СоИ AD", "СоИ Справочники", "ФТТ"}:
                    multiplier *= 1.35
                    labels.append("boost:integration_primary_doc_type")
                if document_type == "ПР" and _is_vector_only(result):
                    multiplier *= 0.72
                    labels.append("penalty:integration_pr_vector_only")

            has_soi_ad_route = any(marker in query_lower for marker in ("сои ad", "active directory", "ldaps", "app_ccpm", "группы ad"))
            if has_soi_ad_route:
                if document_type == "СоИ AD":
                    multiplier *= 3.0
                    labels.append("boost:soi_ad_route")
                    if _is_ad_role_mapping_chunk(text):
                        multiplier *= 1.9
                        labels.append("boost:soi_ad_role_mapping_chunk")
                elif _is_ad_role_mapping_chunk(text):
                    multiplier *= 2.2
                    labels.append("boost:soi_ad_role_mapping_supporting_chunk")
                elif document_type in {"Паспорт ИС", "ЦТА", "ПР"}:
                    multiplier *= 0.68
                    labels.append("penalty:soi_ad_generic_doc")

            if any(marker in query_lower for marker in ("bearer", "bearer token", "mdr", "мдр", "сои нси", "сои справочники")):
                if document_type == "СоИ Справочники":
                    multiplier *= 2.1
                    labels.append("boost:soi_nsi_mdr_route")
                elif document_type in {"ЦТА", "Паспорт ИС", "ФТТ"}:
                    multiplier *= 0.72
                    labels.append("penalty:soi_nsi_mdr_generic_doc")

            if not has_soi_ad_route and any(marker in query_lower for marker in ("пр ", "проектное решение", "статусы замечаний", "инспекционной проверки", "строительного контроля", "автоматически формируемые документы")):
                if document_type == "ПР":
                    multiplier *= 1.9
                    labels.append("boost:pr_construction_control_route")
                    has_pr_status_route = any(marker in query_lower for marker in ("статусы замечаний", "статусная схема", "какие статусы"))
                    has_pr_annulment_route = "аннулир" in query_lower
                    has_pr_roles_route = any(marker in query_lower for marker in ("роли предусмотрены", "какие роли", "матрица ролей", "роли и полномочия"))
                    has_pr_rights_route = any(marker in query_lower for marker in ("права доступа", "ограничения прав", "ограничение прав", "матрица ролей"))
                    has_pr_construction_control_module_route = any(marker in query_lower for marker in ("строительного контроля", "строительный контроль", "модуль строительного контроля"))
                    if has_pr_construction_control_module_route and not _is_pr_construction_control_document(result):
                        multiplier *= 0.28
                        labels.append("penalty:pr_other_module_for_construction_control")
                    if has_pr_status_route:
                        if _is_pr_status_values_chunk(text):
                            multiplier *= 4.8
                            labels.append("boost:pr_notice_status_values")
                        elif _is_pr_status_transition_chunk(text):
                            multiplier *= 2.0
                            labels.append("boost:pr_notice_status_transition")
                        elif _is_pr_generic_process_chunk(text):
                            multiplier *= 0.42
                            labels.append("penalty:pr_notice_status_generic_process")
                    if has_pr_annulment_route:
                        if _is_pr_annulment_chunk(text):
                            multiplier *= 5.0
                            labels.append("boost:pr_notice_annulment_process")
                        elif _is_pr_status_values_chunk(text):
                            multiplier *= 1.6
                            labels.append("boost:pr_notice_annulment_status_support")
                        elif _is_pr_generic_process_chunk(text):
                            multiplier *= 0.36
                            labels.append("penalty:pr_notice_annulment_generic_process")
                    if has_pr_roles_route:
                        if _is_pr_role_composition_chunk(text):
                            multiplier *= 4.6
                            labels.append("boost:pr_roles_composition")
                        elif _is_pr_role_access_chunk(text):
                            multiplier *= 2.1
                            labels.append("boost:pr_roles_access_support")
                        elif _is_pr_generic_process_chunk(text):
                            multiplier *= 0.34
                            labels.append("penalty:pr_roles_generic_process")
                    if has_pr_rights_route:
                        if _is_pr_role_access_chunk(text):
                            multiplier *= 5.0
                            labels.append("boost:pr_rights_access_matrix")
                        elif _is_pr_role_composition_chunk(text):
                            multiplier *= 2.2
                            labels.append("boost:pr_rights_role_composition_support")
                        elif _is_pr_generic_process_chunk(text):
                            multiplier *= 0.32
                            labels.append("penalty:pr_rights_generic_process")
                elif document_type in {"Паспорт ИС", "ЦТА"}:
                    multiplier *= 0.72
                    labels.append("penalty:pr_construction_generic_doc")

            if any(marker in query_lower for marker in ("2520", "600 одновременно", "производительность", "экспорт данных", "pdf", "csv")):
                if document_type == "ФТТ":
                    multiplier *= 1.75
                    labels.append("boost:ftt_performance_or_export_route")

            has_cta_recovery_route = any(
                marker in query_lower
                for marker in ("rto", "rpo", "время восстановления", "точка восстановления", "резервное копирование", "backup", "restore")
            )
            has_explicit_cta_route = "цта" in query_lower or "целевая техническая архитектура" in query_lower
            has_cta_postgresql_route = any(marker in query_lower for marker in ("postgresql", "субд postgresql", "хранение данных"))
            has_cta_minio_route = any(marker in query_lower for marker in ("minio", "s3", "объектное хранилище", "хранение файлов"))
            has_cta_kubernetes_route = any(marker in query_lower for marker in ("kubernetes", "k8s", "развертывание сервисов", "развертывания сервисов"))
            has_cta_logging_route = any(marker in query_lower for marker in ("grafana", "loki", "siem", "логирован", "мониторинг"))
            has_cta_infrastructure_route = has_cta_postgresql_route or has_cta_minio_route or has_cta_kubernetes_route or has_cta_logging_route
            if has_cta_recovery_route:
                if document_type == "ЦТА":
                    multiplier *= 2.2
                    labels.append("boost:cta_recovery_rto_rpo_route")
                    if _is_cta_recovery_chunk(text):
                        multiplier *= 1.95
                        labels.append("boost:cta_recovery_chunk")
                    elif _is_logging_or_port_chunk(text):
                        multiplier *= 0.26
                        labels.append("penalty:cta_recovery_logging_or_port_chunk")
                elif document_type in {"ФТТ", "Паспорт ИС", "СоИ AD", "СоИ Справочники", "ПР"}:
                    multiplier *= 0.62
                    labels.append("penalty:cta_recovery_non_cta_doc")
            elif has_cta_infrastructure_route:
                if document_type == "ЦТА":
                    multiplier *= 1.75
                    labels.append("boost:cta_infrastructure_route")
                    if has_cta_postgresql_route and _is_cta_postgresql_chunk(text):
                        multiplier *= 2.8
                        labels.append("boost:cta_postgresql_chunk")
                    if has_cta_minio_route and _is_cta_minio_storage_chunk(text):
                        multiplier *= 2.6
                        labels.append("boost:cta_minio_storage_chunk")
                    if has_cta_kubernetes_route and _is_cta_kubernetes_chunk(text):
                        multiplier *= 2.8
                        labels.append("boost:cta_kubernetes_chunk")
                    if not has_cta_logging_route and _is_cta_logging_noise_chunk(text):
                        multiplier *= 0.16
                        labels.append("penalty:cta_infrastructure_logging_noise")
                elif has_explicit_cta_route:
                    multiplier *= 0.25
                    labels.append("penalty:cta_infrastructure_non_cta_doc")

            has_nsi_regulation_route = _has_nsi_regulation_route(query_lower)
            has_nsi_reference_route = _has_nsi_reference_route(query_lower)
            if has_nsi_regulation_route:
                if document_type == "Методика/Регламент НСИ":
                    multiplier *= 3.0
                    labels.append("boost:nsi_regulation_route")
                    if _is_nsi_regulation_chunk(text):
                        multiplier *= 1.65
                        labels.append("boost:nsi_regulation_chunk")
                elif document_type == "Реестр НСИ":
                    multiplier *= 1.35
                    labels.append("boost:nsi_regulation_register_support")
                elif document_type in {"Справочник НСИ", "СоИ Справочники"}:
                    multiplier *= 1.05
                    labels.append("boost:nsi_regulation_supporting")
                elif document_type in {"ФТТ", "ПР", "ЦТА"}:
                    multiplier *= 0.38
                    labels.append("penalty:nsi_regulation_project_docs")
            elif has_nsi_reference_route:
                if document_type == "Реестр НСИ":
                    multiplier *= 3.0
                    labels.append("boost:nsi_reference_register")
                    if _is_nsi_reference_chunk(text):
                        multiplier *= 1.9
                        labels.append("boost:nsi_reference_chunk")
                elif document_type == "СоИ Справочники":
                    multiplier *= 2.5
                    labels.append("boost:nsi_reference_soi_spravochniki")
                    if _is_nsi_reference_chunk(text):
                        multiplier *= 2.2
                        labels.append("boost:nsi_reference_chunk")
                elif document_type == "Справочник НСИ":
                    multiplier *= 2.2
                    labels.append("boost:nsi_reference_dictionary")
                    if _is_nsi_reference_chunk(text):
                        multiplier *= 1.7
                        labels.append("boost:nsi_reference_chunk")
                elif document_type == "Методика/Регламент НСИ":
                    multiplier *= 1.15
                    labels.append("boost:nsi_reference_regulation_supporting")
                elif document_type in {"ФТТ", "ПР", "ЦТА"}:
                    multiplier *= 0.32
                    labels.append("penalty:nsi_reference_project_docs")

            if intent.intent == QueryIntent.REQUIREMENT_LOOKUP:
                if document_type == "ФТТ":
                    multiplier *= 1.6
                    labels.append("boost:requirement_lookup_ftt")
                if _has_exact_section(result, intent.mentioned_sections):
                    multiplier *= 1.9
                    labels.append("boost:exact_section_mention")
                elif intent.mentioned_sections:
                    multiplier *= 0.72
                    labels.append("penalty:no_exact_section_mention")
                if document_type == "ПР" and _has_exact_section(result, intent.mentioned_sections):
                    multiplier *= 1.15
                    labels.append("boost:pr_mentions_requirement")

            if _is_glossary_or_front_matter(text) and intent.intent != QueryIntent.DOCUMENT_OVERVIEW:
                multiplier *= 0.5
                labels.append("penalty:glossary_or_front_matter")

            adjusted_score = float(result.score) * multiplier
            adjusted.append(self._with_rerank(result, adjusted_score, labels, multiplier))

        adjusted.sort(key=lambda item: item.score, reverse=True)
        if top_k is not None and top_k > 0:
            overflow = adjusted[top_k:]
            adjusted = adjusted[:top_k]
            excluded.extend(
                self._with_rerank(item, item.score, ["excluded:overflow_after_rerank"])
                for item in overflow
            )

        return RerankResult(
            results=self._renumber(adjusted),
            excluded=excluded,
            diagnostics={
                "reranker": "PostReranker",
                "input_count": len(results),
                "output_count": len(adjusted),
                "excluded_count": len(excluded),
                "intent": intent.intent.value,
            },
        )

    @staticmethod
    def _with_rerank(result: SearchResult, adjusted_score: float, labels: list[str], multiplier: float | None = None) -> SearchResult:
        diagnostics = dict(result.diagnostics)
        existing_labels = list(diagnostics.get("rerank_labels") or [])
        diagnostics["rerank_labels"] = existing_labels + labels
        if multiplier is not None:
            diagnostics["rerank_multiplier"] = round(float(multiplier), 6)
        diagnostics["score_before_post_rerank"] = round(float(result.score), 6)
        return replace(result, score=float(adjusted_score), diagnostics=diagnostics)

    @staticmethod
    def _renumber(results: list[SearchResult]) -> list[SearchResult]:
        return [replace(result, source_id=f"SRC-{idx:03d}") for idx, result in enumerate(results, start=1)]
