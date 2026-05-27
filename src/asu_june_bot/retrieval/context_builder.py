from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import SearchResult
from .parent_expansion import ParentExpander
from .query_intent import QueryIntent, QueryIntentResult
from .source_quality import is_primary_eligible, is_weak_source, source_quality, with_source_quality


@dataclass(slots=True)
class BuiltContext:
    primary_sources: list[SearchResult] = field(default_factory=list)
    supporting_sources: list[SearchResult] = field(default_factory=list)
    excluded_sources: list[SearchResult] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary_sources": [source.to_dict() for source in self.primary_sources],
            "supporting_sources": [source.to_dict() for source in self.supporting_sources],
            "excluded_sources": [source.to_dict(preview_chars=240) for source in self.excluded_sources],
            "diagnostics": self.diagnostics,
        }


def doc_type(result: SearchResult) -> str:
    return str(result.metadata.get("document_type") or "")


def text_lower(result: SearchResult) -> str:
    return " ".join((result.text or "").lower().split())


def is_vector_only(result: SearchResult) -> bool:
    return "vector" in result.matched_by and "bm25" not in result.matched_by


def result_key(result: SearchResult) -> str:
    return str(result.metadata.get("chunk_id") or result.metadata.get("db_id") or result.source_id)


def has_label(result: SearchResult, label: str) -> bool:
    return label in set(result.diagnostics.get("rerank_labels") or [])


def has_noise_label(result: SearchResult) -> bool:
    labels = set(result.diagnostics.get("rerank_labels") or [])
    return any(label.startswith("penalty:software") or label.startswith("penalty:front_matter") for label in labels)


def result_sections(result: SearchResult) -> set[str]:
    sections: set[str] = set()
    raw_sections = result.metadata.get("sections") or []
    if isinstance(raw_sections, list):
        sections.update(str(section).strip().rstrip(".") for section in raw_sections if str(section).strip())
    raw_section = result.metadata.get("section")
    if raw_section:
        sections.add(str(raw_section).strip().rstrip("."))
    cells = result.metadata.get("cells") or {}
    if isinstance(cells, dict):
        for key in ("№", "N", "Номер", "Требование ФТТ"):
            value = cells.get(key)
            if value:
                sections.add(str(value).strip().rstrip("."))
    return {section for section in sections if section}


def has_exact_mentioned_section(result: SearchResult, intent: QueryIntentResult) -> bool:
    mentioned = {str(section).strip().rstrip(".") for section in intent.mentioned_sections if str(section).strip()}
    if not mentioned:
        return False
    return bool(result_sections(result) & mentioned)


def _quality_summary(results: list[SearchResult]) -> dict[str, Any]:
    weak = [result for result in results if is_weak_source(result)]
    reasons: dict[str, int] = {}
    for result in weak:
        for reason in source_quality(result).get("reasons") or []:
            reasons[str(reason)] = reasons.get(str(reason), 0) + 1
    return {
        "assessed_count": len(results),
        "weak_count": len(weak),
        "weak_reasons": reasons,
    }


def _remove_result_by_key(results: list[SearchResult], key: str) -> list[SearchResult]:
    return [result for result in results if result_key(result) != key]


class ContextBuilder:
    def __init__(
        self,
        primary_limit: int = 5,
        supporting_limit: int = 5,
        enable_source_quality_filter: bool = True,
        enable_parent_expansion: bool = True,
        parent_expander: ParentExpander | None = None,
    ):
        self.primary_limit = primary_limit
        self.supporting_limit = supporting_limit
        self.enable_source_quality_filter = enable_source_quality_filter
        self.enable_parent_expansion = enable_parent_expansion
        self.parent_expander = parent_expander or ParentExpander()

    def build(self, query: str, intent: QueryIntentResult, results: list[SearchResult], excluded: list[SearchResult] | None = None) -> BuiltContext:
        assessed_results = [with_source_quality(result, intent) for result in results] if self.enable_source_quality_filter else list(results)
        assessed_excluded = [with_source_quality(result, intent) for result in (excluded or [])] if self.enable_source_quality_filter else list(excluded or [])

        primary: list[SearchResult] = []
        supporting: list[SearchResult] = []
        excluded_sources: list[SearchResult] = []
        used_keys: set[str] = set()
        source_quality_excluded_primary = 0

        for result in assessed_results:
            key = result_key(result)
            if key in used_keys:
                continue
            bucket = self._bucket(query, intent, result)
            if bucket == "primary" and self.enable_source_quality_filter and not is_primary_eligible(result):
                bucket = "supporting" if len(supporting) < self.supporting_limit else "excluded"
                source_quality_excluded_primary += 1

            if bucket == "primary" and len(primary) < self.primary_limit:
                primary.append(result)
                used_keys.add(key)
            elif bucket == "supporting" and len(supporting) < self.supporting_limit:
                supporting.append(result)
                used_keys.add(key)
            else:
                excluded_sources.append(result)
                used_keys.add(key)

        primary_fallback_weak = False
        primary_fallback_promoted = False

        # Fallback: promote the best already bucketed candidate to primary.
        # The first pass intentionally marks every candidate as used, so fallback must not search for unused keys.
        if not primary and assessed_results:
            promoted = self._find_primary_fallback(assessed_results, require_primary_eligible=True)
            if promoted is not None:
                key = result_key(promoted)
                primary.append(promoted)
                supporting = _remove_result_by_key(supporting, key)
                excluded_sources = _remove_result_by_key(excluded_sources, key)
                primary_fallback_promoted = True
                primary_fallback_weak = is_weak_source(promoted)

        # Last resort: if all candidates are weak/non-eligible, keep the best non-noise result as primary
        # but keep the warning in diagnostics. This prevents no_sources for answerable but sparse project facts.
        if not primary and assessed_results:
            promoted = self._find_primary_fallback(assessed_results, require_primary_eligible=False)
            if promoted is not None:
                key = result_key(promoted)
                primary.append(promoted)
                supporting = _remove_result_by_key(supporting, key)
                excluded_sources = _remove_result_by_key(excluded_sources, key)
                primary_fallback_promoted = True
                primary_fallback_weak = is_weak_source(promoted)

        if self.enable_parent_expansion:
            candidate_pool = assessed_results + assessed_excluded
            primary, primary_parent_diag = self.parent_expander.expand(primary, candidate_pool)
            supporting, supporting_parent_diag = self.parent_expander.expand(supporting, candidate_pool)
        else:
            primary_parent_diag = {"parent_expansion": "disabled"}
            supporting_parent_diag = {"parent_expansion": "disabled"}

        for result in assessed_excluded:
            key = result_key(result)
            if key not in used_keys:
                excluded_sources.append(result)
                used_keys.add(key)

        return BuiltContext(
            primary_sources=primary,
            supporting_sources=supporting,
            excluded_sources=excluded_sources,
            diagnostics={
                "builder": "ContextBuilder",
                "intent": intent.intent.value,
                "primary_count": len(primary),
                "supporting_count": len(supporting),
                "excluded_count": len(excluded_sources),
                "source_quality_filter": {
                    "enabled": self.enable_source_quality_filter,
                    "source_quality_excluded_primary": source_quality_excluded_primary,
                    "primary_fallback_promoted": primary_fallback_promoted,
                    "primary_fallback_weak": primary_fallback_weak,
                    "results": _quality_summary(assessed_results),
                    "excluded": _quality_summary(assessed_excluded),
                },
                "parent_expansion": {
                    "enabled": self.enable_parent_expansion,
                    "primary": primary_parent_diag,
                    "supporting": supporting_parent_diag,
                },
            },
        )

    def _find_primary_fallback(self, results: list[SearchResult], require_primary_eligible: bool) -> SearchResult | None:
        for result in results:
            if has_noise_label(result):
                continue
            if require_primary_eligible and self.enable_source_quality_filter and not is_primary_eligible(result):
                continue
            return result
        return None

    def _bucket(self, query: str, intent: QueryIntentResult, result: SearchResult) -> str:
        dt = doc_type(result)
        txt = text_lower(result)

        if has_noise_label(result):
            return "excluded"

        if intent.intent == QueryIntent.DOCUMENT_OVERVIEW:
            if dt == "Паспорт ИС" and any(marker in txt for marker in ["в границы описания включены", "настоящий паспорт ис подготовлен", "архитектурные и эксплуатационные сведения"]):
                return "primary"
            if dt == "Паспорт ИС" and not is_vector_only(result):
                return "supporting"
            return "excluded" if is_vector_only(result) else "supporting"

        if intent.intent == QueryIntent.INTEGRATION_OVERVIEW:
            if dt in {"ЦТА", "Паспорт ИС", "СоИ AD", "СоИ Справочники", "ФТТ"}:
                return "primary" if not is_vector_only(result) else "supporting"
            if dt == "ПР":
                return "supporting"
            return "excluded" if is_vector_only(result) else "supporting"

        if intent.intent == QueryIntent.CTA_RECOVERY_RTO_RPO:
            if dt == "ЦТА" and any(marker in txt for marker in ["rto", "rpo", "время восстановления", "резервное копирование", "аварийный режим", "восстановление данных"]):
                return "primary"
            if dt == "ЦТА":
                return "supporting"
            if dt in {"ФТТ", "Паспорт ИС"}:
                return "supporting"
            return "excluded" if is_vector_only(result) else "supporting"

        if intent.intent == QueryIntent.REQUIREMENT_LOOKUP:
            # Если пользователь указал конкретный пункт, primary должен содержать только точное попадание
            # в этот пункт. Смежные ФТТ/ПР/ПМИ/встречи нужны как supporting context, но не как primary.
            if intent.mentioned_sections:
                if dt == "ФТТ" and has_exact_mentioned_section(result, intent):
                    return "primary"
                if dt in {"ФТТ", "ПР", "ПМИ"}:
                    return "supporting"
                return "excluded" if is_vector_only(result) else "supporting"

            if dt == "ФТТ" and (has_label(result, "boost:exact_section_mention") or not is_vector_only(result)):
                return "primary"
            if dt in {"ПР", "ПМИ"}:
                return "supporting"
            return "excluded" if is_vector_only(result) else "supporting"

        if intent.intent == QueryIntent.GENERAL_PROJECT_QUESTION:
            return "primary" if not is_vector_only(result) else "supporting"

        return "excluded"
