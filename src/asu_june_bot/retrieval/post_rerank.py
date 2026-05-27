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


def _is_ad_role_mapping_chunk(text: str) -> bool:
    has_group_anchor = "app_ccpm" in text or "справочник групп ad" in text or "группы ad пользователя" in text
    has_role_anchor = "роль" in text or "роли строительного контроля" in text or "строительного контроля" in text
    has_groups_attr = "groups" in text or "атрибут groups" in text
    return has_group_anchor and (has_role_anchor or has_groups_attr)


def _is_nsi_regulation_chunk(text: str) -> bool:
    return any(marker in text for marker in ("регламент ведения", "методика ведения", "мвд", "ведение объекта нси"))


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

            if intent.intent == QueryIntent.INTEGRATION_OVERVIEW:
                if document_type in {"ЦТА", "Паспорт ИС", "СоИ AD", "СоИ Справочники", "ФТТ"}:
                    multiplier *= 1.35
                    labels.append("boost:integration_primary_doc_type")
                if document_type == "ПР" and _is_vector_only(result):
                    multiplier *= 0.72
                    labels.append("penalty:integration_pr_vector_only")

            query_lower = query.lower()
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
                elif document_type in {"Паспорт ИС", "ЦТА"}:
                    multiplier *= 0.72
                    labels.append("penalty:pr_construction_generic_doc")

            if any(marker in query_lower for marker in ("2520", "600 одновременно", "производительность", "экспорт данных", "pdf", "csv")):
                if document_type == "ФТТ":
                    multiplier *= 1.75
                    labels.append("boost:ftt_performance_or_export_route")

            if any(marker in query_lower for marker in ("rto", "rpo", "postgresql", "kubernetes", "minio", "grafana", "loki", "siem")):
                if document_type == "ЦТА":
                    multiplier *= 1.75
                    labels.append("boost:cta_infrastructure_route")

            has_nsi_regulation_route = any(marker in query_lower for marker in ("регламент ведения", "регламенты ведения", "мвд"))
            has_nsi_register_route = any(marker in query_lower for marker in ("реестр нси", "свок рд"))
            if has_nsi_regulation_route:
                if document_type == "Методика/Регламент НСИ":
                    multiplier *= 2.6
                    labels.append("boost:nsi_regulation_route")
                    if _is_nsi_regulation_chunk(text):
                        multiplier *= 1.35
                        labels.append("boost:nsi_regulation_chunk")
                elif document_type == "Реестр НСИ":
                    multiplier *= 1.75
                    labels.append("boost:nsi_regulation_register_support")
                elif document_type in {"Справочник НСИ", "СоИ Справочники"}:
                    multiplier *= 1.15
                    labels.append("boost:nsi_regulation_supporting")
                elif document_type in {"ФТТ", "ПР", "ЦТА"}:
                    multiplier *= 0.55
                    labels.append("penalty:nsi_regulation_project_docs")
            elif has_nsi_register_route:
                if document_type == "Реестр НСИ":
                    multiplier *= 2.4
                    labels.append("boost:nsi_register_route")
                elif document_type in {"Справочник НСИ", "Методика/Регламент НСИ"}:
                    multiplier *= 1.35
                    labels.append("boost:nsi_register_supporting")
                elif document_type in {"ФТТ", "ПР", "ЦТА"}:
                    multiplier *= 0.55
                    labels.append("penalty:nsi_register_project_docs")

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
