from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .ranking_profile import RankingProfile


@dataclass(frozen=True, slots=True)
class RankingSignals:
    profile: RankingProfile

    @staticmethod
    def normalize(text: str) -> str:
        return " ".join((text or "").lower().split())

    def has(self, group: str, text: str) -> bool:
        return self.profile.has_any(group, text)

    def document_in(self, group: str, document_type: str) -> bool:
        return self.profile.document_in(group, document_type)

    def has_pr_route(self, query: str) -> bool:
        lowered = self.normalize(query)
        has_short_prefix = any(
            f"{marker} " in lowered for marker in self.profile.markers["pr_short_prefix"]
        )
        return has_short_prefix or self.has("pr_route", lowered)

    def is_glossary_or_front_matter(self, text: str) -> bool:
        return self.has("glossary_front_matter", text)

    def is_software_or_support_table(self, text: str) -> bool:
        return self.has("software_support_table", text)

    def is_passport_related_query(self, query: str) -> bool:
        lowered = self.normalize(query)
        return "связанн" in lowered and "документ" in lowered

    def is_passport_overview_query(self, query: str) -> bool:
        lowered = self.normalize(query)
        return (
            "паспорт" in lowered
            and "ис" in lowered
            and self.has("passport_overview_query", lowered)
        )

    def is_passport_related_chunk(self, text: str) -> bool:
        lowered = self.normalize(text)
        has_table = "таблица: table 2" in lowered
        has_title = "название документа" in lowered
        has_version = "номер версии" in lowered or "имя файла" in lowered
        return (has_table and has_title and has_version) or (
            "связанные документы (этот документ должен читаться вместе с)" in lowered
        )

    def is_passport_appendices_chunk(self, text: str) -> bool:
        lowered = self.normalize(text)
        has_table = "таблица: table 3" in lowered
        has_item = self.has("passport_appendices_chunk", lowered)
        return (has_table and has_item) or (
            "приложения (являются неотъемлемой частью документа)" in lowered
        )

    def is_passport_purpose_chunk(self, text: str) -> bool:
        return self.has("passport_purpose_chunk", text)

    def is_passport_scope_chunk(self, text: str) -> bool:
        lowered = self.normalize(text)
        return (
            "настоящий паспорт ис подготовлен" in lowered
            or "в границы описания включены" in lowered
            or "общие сведения" in lowered[:700]
            or "назначение и область применения" in lowered[:900]
            or "архитектурные и эксплуатационные сведения" in lowered
            or "сведения по базовым сервисам платформы" in lowered
        )

    def is_passport_software_table(self, text: str) -> bool:
        lowered = self.normalize(text)
        return (
            "контекст: программное обеспечение информационной системы" in lowered
            or "заголовки: наименование по | тип по" in lowered
            or ("строка" in lowered[:350] and "postgresql" in lowered)
            or ("строка" in lowered[:350] and "kubernetes" in lowered)
            or ("строка" in lowered[:350] and "nginx" in lowered)
        )

    def is_ad_role_mapping_chunk(self, text: str) -> bool:
        lowered = self.normalize(text)
        has_group_anchor = self.has("soi_ad_group_anchor", lowered)
        has_role_anchor = self.has("soi_ad_role_anchor", lowered)
        has_groups_attr = self.has("soi_ad_groups_attribute", lowered)
        return has_group_anchor and (has_role_anchor or has_groups_attr)

    def is_nsi_regulation_chunk(self, text: str) -> bool:
        return self.has("nsi_regulation_chunk", text)

    def is_nsi_reference_chunk(self, text: str) -> bool:
        lowered = self.normalize(text)
        has_named_dictionary = "справочники:" in lowered and self.has(
            "nsi_dictionary_names", lowered
        )
        return (
            has_named_dictionary
            or self.has("nsi_reference_chunk", lowered)
            or ("table 8" in lowered and "справочники" in lowered)
        )

    def is_cta_recovery_chunk(self, text: str) -> bool:
        return self.has("cta_recovery_chunk", text)

    def is_logging_or_port_chunk(self, text: str) -> bool:
        lowered = self.normalize(text)
        return self.has("logging_noise", lowered) or any(
            marker in lowered for marker in ("порт ", "tcp/", "udp/")
        )

    def is_cta_logging_noise_chunk(self, text: str) -> bool:
        lowered = self.normalize(text)
        return self.has("logging_noise", lowered) and not self.has("file_storage_signal", lowered)

    def is_cta_postgresql_chunk(self, text: str) -> bool:
        lowered = self.normalize(text)
        return "postgresql" in lowered and self.has("cta_postgresql_chunk", lowered)

    def is_cta_minio_storage_chunk(self, text: str) -> bool:
        lowered = self.normalize(text)
        return ("minio" in lowered or "s3" in lowered) and self.has("cta_minio_chunk", lowered)

    def is_cta_kubernetes_chunk(self, text: str) -> bool:
        lowered = self.normalize(text)
        return ("kubernetes" in lowered or "k8s" in lowered) and self.has(
            "cta_kubernetes_chunk", lowered
        )

    def pr_status_count(self, text: str) -> int:
        return self.profile.count("pr_status_values", text)

    def is_pr_status_values_chunk(self, text: str) -> bool:
        lowered = self.normalize(text)
        count = self.pr_status_count(lowered)
        return ("значения:" in lowered and "статус" in lowered and count >= 5) or (
            "статусная схема замечаний" in lowered and count >= 2
        )

    def is_pr_status_transition_chunk(self, text: str) -> bool:
        return self.pr_status_count(text) >= 2 and self.has("pr_status_transition", text)

    def is_pr_annulment_chunk(self, text: str) -> bool:
        lowered = self.normalize(text)
        return "аннулир" in lowered and self.has("pr_annulment_chunk", lowered)

    def is_pr_role_composition_chunk(self, text: str) -> bool:
        return self.has("pr_role_composition_chunk", text)

    def is_pr_role_access_chunk(self, text: str) -> bool:
        lowered = self.normalize(text)
        has_role = self.has("pr_role_names", lowered)
        has_access = any(
            marker in lowered for marker in ("право доступа", "права доступа", "ограничения")
        )
        has_matrix = "тип объекта: ск:" in lowered and self.has("pr_matrix_values", lowered)
        return self.has("pr_role_access_chunk", lowered) or (
            has_role and (has_access or has_matrix)
        )

    def is_pr_generic_process_chunk(self, text: str) -> bool:
        return self.has("pr_generic_process_chunk", text)

    @staticmethod
    def is_pr_construction_control_document(metadata: dict[str, Any]) -> bool:
        path = str(metadata.get("relative_path") or metadata.get("source_path") or "").lower()
        return "строительн" in path and "контрол" in path

    @staticmethod
    def has_exact_section(metadata: dict[str, Any], text: str, sections: list[str]) -> bool:
        if not sections:
            return False
        result_sections = {str(item) for item in (metadata.get("sections") or [])}
        requirement_id = str(metadata.get("requirement_id") or "")
        for section in sections:
            if section in result_sections or section == requirement_id:
                return True
            if re.search(rf"(?<!\d){re.escape(section)}(?:\.|\b)", text or ""):
                return True
        return False
