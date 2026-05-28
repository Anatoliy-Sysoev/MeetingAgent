from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from .metadata import enrich_metadata
from .models import SearchResult
from .source_policy import SourcePolicy


_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-я0-9_./-]+", re.UNICODE)
SECTION_QUERY_RE = re.compile(r"(?<!\d)(\d+(?:\.\d+){1,5})(?:\.|\b)")


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in _TOKEN_RE.findall(text or "") if len(token) > 1]


def extract_query_sections(query: str) -> list[str]:
    seen: set[str] = set()
    sections: list[str] = []
    for match in SECTION_QUERY_RE.finditer(query):
        section = match.group(1)
        if section not in seen:
            seen.add(section)
            sections.append(section)
    return sections


def has_exact_section_in_text(text: str, section: str) -> bool:
    escaped = re.escape(section)
    return re.search(rf"(?<!\d){escaped}(?:\.|\b)", text or "") is not None


@dataclass(slots=True)
class BM25Document:
    row_id: int
    text: str
    metadata: dict[str, Any]
    term_freq: Counter[str]
    length: int


class BM25SearchAdapter:
    @staticmethod
    def _is_ad_role_mapping_chunk(text_lower: str) -> bool:
        has_group_anchor = "app_ccpm" in text_lower or "справочник групп ad" in text_lower or "группы ad пользователя" in text_lower
        has_role_anchor = "роль" in text_lower or "роли строительного контроля" in text_lower or "строительного контроля" in text_lower
        has_groups_attr = "groups" in text_lower or "атрибут groups" in text_lower
        return has_group_anchor and (has_role_anchor or has_groups_attr)

    @staticmethod
    def _is_nsi_regulation_chunk(text_lower: str) -> bool:
        return any(marker in text_lower for marker in ("регламент ведения", "методика ведения", "мвд", "ведение объекта нси"))

    @staticmethod
    def _is_cta_recovery_chunk(text_lower: str) -> bool:
        return any(
            marker in text_lower
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

    @staticmethod
    def _is_logging_or_port_chunk(text_lower: str) -> bool:
        has_logging_noise = any(marker in text_lower for marker in ("grafana loki", "siem", "логирован", "мониторинг", "otel", "otlp"))
        has_port_noise = "порт " in text_lower or "tcp/" in text_lower or "udp/" in text_lower
        return has_logging_noise or has_port_noise

    @staticmethod
    def _is_cta_logging_noise_chunk(text_lower: str) -> bool:
        has_logging_noise = any(
            marker in text_lower
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
        has_file_storage_signal = any(marker in text_lower for marker in ("сохранение файлов", "хранение файлов", "объектное хранилище"))
        return has_logging_noise and not has_file_storage_signal

    @staticmethod
    def _is_cta_postgresql_chunk(text_lower: str) -> bool:
        if "postgresql" not in text_lower:
            return False
        return any(
            marker in text_lower
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

    @staticmethod
    def _is_cta_minio_storage_chunk(text_lower: str) -> bool:
        if "minio" not in text_lower and "s3" not in text_lower:
            return False
        return any(
            marker in text_lower
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

    @staticmethod
    def _is_cta_kubernetes_chunk(text_lower: str) -> bool:
        if "kubernetes" not in text_lower and "k8s" not in text_lower:
            return False
        return any(
            marker in text_lower
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

    @staticmethod
    def _pr_status_count(text_lower: str) -> int:
        status_markers = (
            "к устранению",
            "на проверке",
            "на доработке",
            "просрочено",
            "не устранено",
            "устранено",
            "аннулировано",
        )
        return sum(1 for marker in status_markers if marker in text_lower)

    @classmethod
    def _is_pr_status_values_chunk(cls, text_lower: str) -> bool:
        status_count = cls._pr_status_count(text_lower)
        has_values_list = "значения:" in text_lower and "статус" in text_lower and status_count >= 5
        has_status_scheme = "статусная схема замечаний" in text_lower and status_count >= 2
        return has_values_list or has_status_scheme

    @classmethod
    def _is_pr_status_transition_chunk(cls, text_lower: str) -> bool:
        if cls._pr_status_count(text_lower) < 2:
            return False
        return any(
            marker in text_lower
            for marker in (
                "меняет статус замечания",
                "изменяет статус замечания",
                "статус замечания",
                "карточке замечания нажимает",
            )
        )

    @staticmethod
    def _is_pr_annulment_chunk(text_lower: str) -> bool:
        if "аннулир" not in text_lower:
            return False
        return any(
            marker in text_lower
            for marker in (
                "признано необоснованным",
                "необоснованности замечания",
                "процесс по замечанию завершается",
                "может его аннулировать",
                "кнопку «аннулировать»",
                "кнопку \"аннулировать\"",
            )
        )

    @staticmethod
    def _is_pr_role_composition_chunk(text_lower: str) -> bool:
        return any(
            marker in text_lower
            for marker in (
                "состав ролей, использующих функциональность данного модуля",
                "привилегированные:",
                "непривилегированные:",
            )
        )

    @staticmethod
    def _is_pr_role_access_chunk(text_lower: str) -> bool:
        role_markers = (
            "куратор проекта нул",
            "инженер ск",
            "представитель лос",
            "специалист технической поддержки",
            "специалист информационной безопасности",
            "аудитор нул",
        )
        has_role = any(marker in text_lower for marker in role_markers)
        has_access_word = "право доступа" in text_lower or "права доступа" in text_lower or "ограничения" in text_lower
        has_matrix_values = "тип объекта: ск:" in text_lower and any(marker in text_lower for marker in ("просмотр", "изменение", "создание", "удаление", "нет"))
        return (
            "права доступа по ролям" in text_lower
            or "объектам интерфейса пользователя" in text_lower
            or "регламентным заданиям" in text_lower
            or (has_role and (has_access_word or has_matrix_values))
        )

    @staticmethod
    def _is_pr_generic_process_chunk(text_lower: str) -> bool:
        return any(
            marker in text_lower
            for marker in (
                "управление замечаниями: операционный контроль",
                "управление замечаниями: эскалация",
                "закрытие замечания/ предписания",
                "автоматическая генерация инспекционных документов",
                "акт об устранении: формируется автоматически",
                "роль исполнителя:",
            )
        )

    @staticmethod
    def _is_pr_construction_control_document(metadata: dict[str, Any]) -> bool:
        path_lower = str(metadata.get("relative_path") or metadata.get("source_path") or "").lower()
        return "строительн" in path_lower and "контрол" in path_lower

    def __init__(self, rows: list[dict[str, Any]], source_policy: SourcePolicy | None = None, k1: float = 1.5, b: float = 0.75):
        self.source_policy = source_policy or SourcePolicy()
        self.k1 = k1
        self.b = b
        self.documents: list[BM25Document] = []
        self.doc_freq: Counter[str] = Counter()

        for row_id, row in enumerate(rows):
            text = str(row.get("text") or row.get("document") or "")
            raw_meta = dict(row.get("metadata") or row)
            metadata = enrich_metadata(raw_meta, text)
            tokens = tokenize(text)
            term_freq = Counter(tokens)
            self.documents.append(BM25Document(row_id=row_id, text=text, metadata=metadata, term_freq=term_freq, length=len(tokens)))
            self.doc_freq.update(set(tokens))

        self.doc_count = len(self.documents)
        self.avg_doc_len = sum(doc.length for doc in self.documents) / max(self.doc_count, 1)

    def _idf(self, term: str) -> float:
        df = self.doc_freq.get(term, 0)
        if df <= 0:
            return 0.0
        return math.log(1 + (self.doc_count - df + 0.5) / (df + 0.5))

    def _score_doc(self, query_terms: list[str], doc: BM25Document) -> float:
        if not query_terms or doc.length <= 0:
            return 0.0
        score = 0.0
        for term in query_terms:
            tf = doc.term_freq.get(term, 0)
            if tf <= 0:
                continue
            denom = tf + self.k1 * (1 - self.b + self.b * doc.length / max(self.avg_doc_len, 1e-9))
            score += self._idf(term) * (tf * (self.k1 + 1)) / max(denom, 1e-9)
        return score

    def _exact_section_boost(self, query_sections: list[str], doc: BM25Document) -> tuple[float, list[str]]:
        if not query_sections:
            return 1.0, []
        doc_sections = set(str(section) for section in (doc.metadata.get("sections") or []))
        requirement_id = str(doc.metadata.get("requirement_id") or "")
        matched: list[str] = []
        for section in query_sections:
            if section in doc_sections or section == requirement_id or has_exact_section_in_text(doc.text, section):
                matched.append(section)
        if not matched:
            return 1.0, []
        if any(section == requirement_id for section in matched):
            return 2.1, matched
        if any(section in doc_sections for section in matched):
            return 1.75, matched
        return 1.45, matched

    @staticmethod
    def _is_passport_overview_query(lowered: str) -> bool:
        return "паспорт" in lowered and "ис" in lowered and any(marker in lowered for marker in ["что входит", "состав", "структур", "раздел", "включает", "из чего"])

    @staticmethod
    def _is_passport_software_table(text_lower: str) -> bool:
        return (
            "контекст: программное обеспечение информационной системы" in text_lower
            or "заголовки: наименование по | тип по" in text_lower
            or "строка" in text_lower[:350] and "postgresql" in text_lower
            or "строка" in text_lower[:350] and "kubernetes" in text_lower
            or "строка" in text_lower[:350] and "nginx" in text_lower
        )

    @staticmethod
    def _is_passport_scope_chunk(text_lower: str) -> bool:
        return (
            "настоящий паспорт ис подготовлен" in text_lower
            or "в границы описания включены" in text_lower
            or "общие сведения" in text_lower[:700]
            or "назначение и область применения" in text_lower[:900]
            or "архитектурные и эксплуатационные сведения" in text_lower
            or "сведения по базовым сервисам платформы" in text_lower
        )

    def _intent_boost(self, query: str, doc: BM25Document) -> tuple[float, list[str]]:
        lowered = query.lower()
        original_lowered = query.split("\n", 1)[0].lower()
        document_type = str(doc.metadata.get("document_type") or "")
        text_lower = doc.text.lower()
        boosts: list[tuple[str, float]] = []
        has_soi_ad_route = any(marker in lowered for marker in ("сои ad", "active directory", "ldaps", "app_ccpm", "группы ad"))

        if "паспорт" in lowered and "ис" in lowered:
            boosts.append(("intent:passport", 2.0 if document_type == "Паспорт ИС" else 0.72))
            if self._is_passport_overview_query(lowered):
                if self._is_passport_scope_chunk(text_lower):
                    boosts.append(("intent:passport_overview_scope", 2.6))
                if self._is_passport_software_table(text_lower):
                    boosts.append(("penalty:passport_software_table_for_overview", 0.18))
                if "история изменений" in text_lower[:1000] or "связанные документы" in text_lower[:1200]:
                    boosts.append(("penalty:passport_front_matter_for_overview", 0.35))

        if "фтт" in lowered:
            if document_type == "ФТТ":
                boosts.append(("intent:ftt", 1.85))
            elif document_type == "ПМИ":
                boosts.append(("intent:ftt_penalty_pmi", 0.68))
            elif document_type == "ПР":
                boosts.append(("intent:ftt_penalty_pr", 0.82))

        if "интеграц" in lowered or "взаимодейств" in lowered:
            if document_type in {"ЦТА", "СоИ AD", "СоИ Справочники", "Паспорт ИС", "ФТТ"}:
                boosts.append(("intent:integrations", 1.25))
            elif document_type == "Wiki":
                boosts.append(("intent:integrations_wiki_penalty", 0.72))

        if has_soi_ad_route:
            if document_type == "СоИ AD":
                boosts.append(("intent:soi_ad", 3.2))
                if self._is_ad_role_mapping_chunk(text_lower):
                    boosts.append(("intent:soi_ad_role_mapping", 1.85))
            elif self._is_ad_role_mapping_chunk(text_lower):
                boosts.append(("intent:soi_ad_role_mapping_supporting", 2.1))
            elif document_type in {"Паспорт ИС", "ЦТА", "ПР"}:
                boosts.append(("intent:soi_ad_penalty_generic_docs", 0.68))

        if any(marker in lowered for marker in ("bearer", "bearer token", "mdr", "мдр", "сои нси", "сои справочники")):
            if document_type == "СоИ Справочники":
                boosts.append(("intent:soi_nsi_mdr", 2.35))
            elif document_type in {"ЦТА", "Паспорт ИС", "ФТТ"}:
                boosts.append(("intent:soi_nsi_mdr_penalty_generic_docs", 0.72))

        has_pr_status_route = any(marker in original_lowered for marker in ("статусы замечаний", "статусная схема", "какие статусы"))
        has_pr_annulment_route = "аннулир" in original_lowered
        has_pr_roles_route = any(marker in original_lowered for marker in ("роли предусмотрены", "какие роли", "матрица ролей", "роли и полномочия"))
        has_pr_rights_route = any(marker in original_lowered for marker in ("права доступа", "ограничения прав", "ограничение прав", "матрица ролей"))
        has_pr_construction_control_module_route = any(marker in original_lowered for marker in ("строительного контроля", "строительный контроль", "модуль строительного контроля"))
        if not has_soi_ad_route and any(marker in lowered for marker in ("пр ", "проектное решение", "статусы замечаний", "инспекционной проверки", "строительного контроля", "автоматически формируемые документы")):
            if document_type == "ПР":
                boosts.append(("intent:pr_construction_control", 2.0))
                if has_pr_construction_control_module_route and not self._is_pr_construction_control_document(doc.metadata):
                    boosts.append(("penalty:pr_other_module_for_construction_control", 0.28))
                if has_pr_status_route:
                    if self._is_pr_status_values_chunk(text_lower):
                        boosts.append(("intent:pr_notice_status_values", 5.2))
                    elif self._is_pr_status_transition_chunk(text_lower):
                        boosts.append(("intent:pr_notice_status_transition", 2.2))
                    elif self._is_pr_generic_process_chunk(text_lower):
                        boosts.append(("penalty:pr_notice_status_generic_process", 0.42))
                if has_pr_annulment_route:
                    if self._is_pr_annulment_chunk(text_lower):
                        boosts.append(("intent:pr_notice_annulment_process", 5.4))
                    elif self._is_pr_status_values_chunk(text_lower):
                        boosts.append(("intent:pr_notice_annulment_status_support", 1.7))
                    elif self._is_pr_generic_process_chunk(text_lower):
                        boosts.append(("penalty:pr_notice_annulment_generic_process", 0.36))
                if has_pr_roles_route:
                    if self._is_pr_role_composition_chunk(text_lower):
                        boosts.append(("intent:pr_roles_composition", 5.0))
                    elif self._is_pr_role_access_chunk(text_lower):
                        boosts.append(("intent:pr_roles_access_support", 2.2))
                    elif self._is_pr_generic_process_chunk(text_lower):
                        boosts.append(("penalty:pr_roles_generic_process", 0.34))
                if has_pr_rights_route:
                    if self._is_pr_role_access_chunk(text_lower):
                        boosts.append(("intent:pr_rights_access_matrix", 5.4))
                    elif self._is_pr_role_composition_chunk(text_lower):
                        boosts.append(("intent:pr_rights_role_composition_support", 2.4))
                    elif self._is_pr_generic_process_chunk(text_lower):
                        boosts.append(("penalty:pr_rights_generic_process", 0.32))
            elif document_type in {"Паспорт ИС", "ЦТА"}:
                boosts.append(("intent:pr_construction_control_penalty_generic_docs", 0.72))

        if any(marker in lowered for marker in ("2520", "600 одновременно", "производительность", "экспорт данных", "pdf", "csv")):
            if document_type == "ФТТ":
                boosts.append(("intent:ftt_performance_or_export", 1.85))

        has_cta_recovery_route = any(
            marker in lowered
            for marker in ("rto", "rpo", "время восстановления", "точка восстановления", "резервное копирование", "backup", "restore")
        )
        has_explicit_cta_route = "цта" in lowered or "целевая техническая архитектура" in lowered
        has_cta_postgresql_route = any(marker in lowered for marker in ("postgresql", "субд postgresql", "хранение данных"))
        has_cta_minio_route = any(marker in lowered for marker in ("minio", "s3", "объектное хранилище", "хранение файлов"))
        has_cta_kubernetes_route = any(marker in lowered for marker in ("kubernetes", "k8s", "развертывание сервисов", "развертывания сервисов"))
        has_cta_logging_route = any(marker in lowered for marker in ("grafana", "loki", "siem", "логирован", "мониторинг"))
        has_cta_infrastructure_route = has_cta_postgresql_route or has_cta_minio_route or has_cta_kubernetes_route or has_cta_logging_route
        if has_cta_recovery_route:
            if document_type == "ЦТА":
                boosts.append(("intent:cta_recovery_rto_rpo", 2.4))
                if self._is_cta_recovery_chunk(text_lower):
                    boosts.append(("intent:cta_recovery_chunk", 2.2))
                elif self._is_logging_or_port_chunk(text_lower):
                    boosts.append(("intent:cta_recovery_penalty_logging_or_port", 0.28))
            elif document_type in {"ФТТ", "Паспорт ИС", "СоИ AD", "СоИ Справочники", "ПР"}:
                boosts.append(("intent:cta_recovery_penalty_non_cta", 0.62))
        elif has_cta_infrastructure_route:
            if document_type == "ЦТА":
                boosts.append(("intent:cta_infrastructure", 1.85))
                if has_cta_postgresql_route and self._is_cta_postgresql_chunk(text_lower):
                    boosts.append(("intent:cta_postgresql_chunk", 3.0))
                if has_cta_minio_route and self._is_cta_minio_storage_chunk(text_lower):
                    boosts.append(("intent:cta_minio_storage_chunk", 2.8))
                if has_cta_kubernetes_route and self._is_cta_kubernetes_chunk(text_lower):
                    boosts.append(("intent:cta_kubernetes_chunk", 3.0))
                if not has_cta_logging_route and self._is_cta_logging_noise_chunk(text_lower):
                    boosts.append(("penalty:cta_infrastructure_logging_noise", 0.16))
            elif has_explicit_cta_route:
                boosts.append(("intent:cta_infrastructure_penalty_non_cta", 0.25))

        has_nsi_regulation_route = any(marker in lowered for marker in ("регламент ведения", "регламенты ведения", "мвд"))
        has_nsi_register_route = any(marker in lowered for marker in ("реестр нси", "свок рд"))
        if has_nsi_regulation_route:
            if document_type == "Методика/Регламент НСИ":
                boosts.append(("intent:nsi_regulation_primary", 2.75))
                if self._is_nsi_regulation_chunk(text_lower):
                    boosts.append(("intent:nsi_regulation_chunk", 1.45))
            elif document_type == "Реестр НСИ":
                boosts.append(("intent:nsi_regulation_register_support", 1.8))
            elif document_type in {"Справочник НСИ", "СоИ Справочники"}:
                boosts.append(("intent:nsi_regulation_supporting", 1.2))
            elif document_type in {"ФТТ", "ПР", "ЦТА"}:
                boosts.append(("intent:nsi_regulation_penalty_project_docs", 0.55))
        elif has_nsi_register_route:
            if document_type == "Реестр НСИ":
                boosts.append(("intent:nsi_register", 2.5))
            elif document_type in {"Справочник НСИ", "Методика/Регламент НСИ"}:
                boosts.append(("intent:nsi_register_supporting", 1.45))
            elif document_type in {"ФТТ", "ПР", "ЦТА"}:
                boosts.append(("intent:nsi_register_penalty_project_docs", 0.55))

        if "глоссарий" not in lowered and (
            "контекст: глоссарий" in text_lower
            or "таблица 5 контекст: глоссарий" in text_lower
            or "таблица 7 контекст: глоссарий" in text_lower
            or "используемые сокращения" in text_lower[:700]
        ):
            boosts.append(("penalty:glossary", 0.25))

        if "история изменений" in text_lower[:800] and "история" not in lowered:
            boosts.append(("penalty:change_history", 0.55))

        multiplier = 1.0
        labels: list[str] = []
        for label, boost in boosts:
            multiplier *= boost
            labels.append(label)
        return multiplier, labels

    def search(self, query: str, top_k: int, include_source_types: list[str] | None = None) -> list[SearchResult]:
        query_terms = tokenize(query)
        query_sections = extract_query_sections(query)
        if not query_terms or top_k <= 0:
            return []

        scored: list[tuple[float, BM25Document, dict[str, Any]]] = []
        for doc in self.documents:
            if not self.source_policy.is_allowed(doc.metadata, query, include_source_types):
                continue
            score = self._score_doc(query_terms, doc)
            if score <= 0:
                continue
            section_boost, matched_sections = self._exact_section_boost(query_sections, doc)
            intent_boost, intent_labels = self._intent_boost(query, doc)
            policy_weight = self.source_policy.weight(doc.metadata)
            final_score = score * policy_weight * section_boost * intent_boost
            if final_score <= 0:
                continue
            scored.append(
                (
                    final_score,
                    doc,
                    {
                        "raw_bm25_score": score,
                        "policy_weight": policy_weight,
                        "section_boost": section_boost,
                        "matched_sections": matched_sections,
                        "intent_boost": intent_boost,
                        "intent_labels": intent_labels,
                    },
                )
            )

        scored.sort(key=lambda item: item[0], reverse=True)
        results: list[SearchResult] = []
        for idx, (score, doc, diagnostics) in enumerate(scored[:top_k], start=1):
            results.append(
                SearchResult(
                    source_id=f"BM25-{idx:03d}",
                    text=doc.text,
                    score=float(score),
                    vector_score=None,
                    bm25_score=float(score),
                    metadata=doc.metadata,
                    matched_by=["bm25"],
                    diagnostics=diagnostics,
                )
            )
        return results
