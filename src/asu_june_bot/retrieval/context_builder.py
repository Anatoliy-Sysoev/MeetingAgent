from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import SearchResult
from .query_intent import QueryIntent, QueryIntentResult


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


class ContextBuilder:
    def __init__(self, primary_limit: int = 5, supporting_limit: int = 5):
        self.primary_limit = primary_limit
        self.supporting_limit = supporting_limit

    def build(self, query: str, intent: QueryIntentResult, results: list[SearchResult], excluded: list[SearchResult] | None = None) -> BuiltContext:
        primary: list[SearchResult] = []
        supporting: list[SearchResult] = []
        excluded_sources: list[SearchResult] = list(excluded or [])

        for result in results:
            bucket = self._bucket(query, intent, result)
            if bucket == "primary" and len(primary) < self.primary_limit:
                primary.append(result)
            elif bucket == "supporting" and len(supporting) < self.supporting_limit:
                supporting.append(result)
            else:
                excluded_sources.append(result)

        if not primary and results:
            for result in results:
                if not has_noise_label(result):
                    primary.append(result)
                    break

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
            },
        )

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
