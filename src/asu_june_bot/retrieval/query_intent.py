from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class QueryIntent(StrEnum):
    DOCUMENT_OVERVIEW = "document_overview"
    INTEGRATION_OVERVIEW = "integration_overview"
    REQUIREMENT_LOOKUP = "requirement_lookup"
    GENERAL_PROJECT_QUESTION = "general_project_question"
    OUT_OF_SCOPE_CANDIDATE = "out_of_scope_candidate"


REQUIREMENT_RE = re.compile(r"(?<!\d)(\d+(?:\.\d+){1,5})(?:\.|\b)")
FTT_RE = re.compile(r"\bфтт\b", re.IGNORECASE | re.UNICODE)

PROJECT_MARKERS = {
    "цп упкс",
    "упкс",
    "асу",
    "фтт",
    "цта",
    "пми",
    "пси",
    "псси",
    "пр ",
    "проектное решение",
    "паспорт ис",
    "паспорт информационной системы",
    "сои",
    "соглашение об интеграции",
    "mdr",
    "мдр",
    "кшд",
    "ad",
    "active directory",
    "blitz",
    "blitz idp",
    "siem",
    "новадок",
    "эцп",
    "смр",
    "мто",
    "нси",
    "справочник",
    "справочники",
    "строительный контроль",
    "исполнительная документация",
    "проектная документация",
    "интеграция",
    "интеграции",
    "требование",
    "требования",
    "архитектура",
    "модуль",
    "модули",
    "система цп",
    "система асу",
    "протокол встречи",
    "встреча",
}

DOCUMENT_MARKERS = {
    "паспорт ис",
    "паспорт информационной системы",
    "фтт",
    "цта",
    "пми",
    "проектное решение",
    "сои",
    "соглашение об интеграции",
    "руководство",
    "инструкция",
}

OVERVIEW_MARKERS = {
    "что входит",
    "из чего состоит",
    "состав",
    "структура",
    "структуру",
    "разделы",
    "какие разделы",
    "что включает",
    "включает",
    "опиши",
    "описание",
}

INTEGRATION_MARKERS = {
    "интеграция",
    "интеграции",
    "интеграционн",
    "системное взаимодействие",
    "системные взаимодействия",
    "внешние системы",
    "смежные системы",
    "обмен данными",
    "кшд",
    "сои",
    "ad",
    "active directory",
    "mdr",
    "мдр",
    "blitz",
    "siem",
    "smtp",
    "s3",
    "minio",
}

OUT_OF_SCOPE_MARKERS = {
    "погода",
    "курс доллара",
    "курс евро",
    "курс валют",
    "биткоин",
    "акции",
    "новости",
    "рецепт",
    "калории",
    "тренировка",
    "здоровье",
    "болит",
    "врач",
    "лекарство",
    "кино",
    "фильм",
    "игра",
    "игры",
    "игру",
    "игровой",
    "крестики",
    "нолики",
    "крестики нолики",
    "tic tac toe",
    "музыка",
    "песня",
    "путешествие",
    "отель",
    "билет",
    "купить",
    "цена",
    "скидка",
    "президент",
    "политика",
    "выборы",
    "анекдот",
    "шутка",
    "питон",
    "python",
    "javascript",
    "js",
    "html",
    "css",
    "код для",
    "напиши код",
    "сделай код",
    "скрипт для",
    "программа для",
    "в браузере",
    "браузерная игра",
    # offensive / security abuse markers. Defensive questions must be phrased as protection/audit tasks.
    "sql инъекц",
    "sql-инъекц",
    "sqli",
    "sql injection",
    "инъекцию",
    "инъекция",
    "инъекции",
    "дай инъекцию",
    "payload",
    "exploit",
    "эксплойт",
    "взлом",
    "взломать",
    "обойти защиту",
    "обход защиты",
    "jailbreak",
    "ignore previous instructions",
    "игнорируй предыдущие инструкции",
    "system prompt",
}

SAFE_GENERIC_PROJECT_WORDS = {
    "документ",
    "документы",
    "проект",
    "проекте",
    "требование",
    "требования",
    "архитектура",
    "интеграция",
    "интеграции",
    "модуль",
    "модули",
    "раздел",
    "разделы",
}


@dataclass(slots=True)
class QueryIntentResult:
    intent: QueryIntent
    confidence: float
    is_project_related: bool
    labels: list[str] = field(default_factory=list)
    matched_project_markers: list[str] = field(default_factory=list)
    matched_out_of_scope_markers: list[str] = field(default_factory=list)
    mentioned_sections: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent.value,
            "confidence": round(float(self.confidence), 4),
            "is_project_related": self.is_project_related,
            "labels": self.labels,
            "matched_project_markers": self.matched_project_markers,
            "matched_out_of_scope_markers": self.matched_out_of_scope_markers,
            "mentioned_sections": self.mentioned_sections,
        }


def _contains_any(lowered: str, markers: set[str]) -> list[str]:
    matched = []
    padded = f" {lowered} "
    for marker in sorted(markers, key=len, reverse=True):
        marker_l = marker.lower()
        if marker_l.endswith(" "):
            if marker_l in padded:
                matched.append(marker.strip())
            continue
        if marker_l in lowered:
            matched.append(marker)
    return matched


def _extract_sections(query: str) -> list[str]:
    seen: set[str] = set()
    sections: list[str] = []
    for match in REQUIREMENT_RE.finditer(query):
        section = match.group(1)
        if section not in seen:
            seen.add(section)
            sections.append(section)
    return sections


def classify_query_intent(query: str) -> QueryIntentResult:
    lowered = " ".join((query or "").lower().split())
    project_matches = _contains_any(lowered, PROJECT_MARKERS)
    document_matches = _contains_any(lowered, DOCUMENT_MARKERS)
    overview_matches = _contains_any(lowered, OVERVIEW_MARKERS)
    integration_matches = _contains_any(lowered, INTEGRATION_MARKERS)
    out_matches = _contains_any(lowered, OUT_OF_SCOPE_MARKERS)
    mentioned_sections = _extract_sections(query)

    labels: list[str] = []
    if project_matches:
        labels.append("has_project_marker")
    if document_matches:
        labels.append("has_document_marker")
    if overview_matches:
        labels.append("has_overview_marker")
    if integration_matches:
        labels.append("has_integration_marker")
    if mentioned_sections:
        labels.append("has_section_marker")
    if out_matches:
        labels.append("has_out_of_scope_marker")

    has_project_signal = bool(project_matches or document_matches or mentioned_sections)
    has_strong_out_scope = bool(out_matches) and not has_project_signal

    if has_strong_out_scope:
        return QueryIntentResult(
            intent=QueryIntent.OUT_OF_SCOPE_CANDIDATE,
            confidence=0.96,
            is_project_related=False,
            labels=labels + ["strong_out_of_scope_without_project_signal"],
            matched_project_markers=project_matches,
            matched_out_of_scope_markers=out_matches,
            mentioned_sections=mentioned_sections,
        )

    if integration_matches:
        return QueryIntentResult(
            intent=QueryIntent.INTEGRATION_OVERVIEW,
            confidence=0.88 if has_project_signal else 0.62,
            is_project_related=True,
            labels=labels,
            matched_project_markers=project_matches,
            matched_out_of_scope_markers=out_matches,
            mentioned_sections=mentioned_sections,
        )

    if FTT_RE.search(query or "") or mentioned_sections:
        return QueryIntentResult(
            intent=QueryIntent.REQUIREMENT_LOOKUP,
            confidence=0.9 if FTT_RE.search(query or "") else 0.72,
            is_project_related=True,
            labels=labels,
            matched_project_markers=project_matches,
            matched_out_of_scope_markers=out_matches,
            mentioned_sections=mentioned_sections,
        )

    if document_matches and overview_matches:
        return QueryIntentResult(
            intent=QueryIntent.DOCUMENT_OVERVIEW,
            confidence=0.9,
            is_project_related=True,
            labels=labels,
            matched_project_markers=project_matches,
            matched_out_of_scope_markers=out_matches,
            mentioned_sections=mentioned_sections,
        )

    if project_matches:
        return QueryIntentResult(
            intent=QueryIntent.GENERAL_PROJECT_QUESTION,
            confidence=0.72,
            is_project_related=True,
            labels=labels,
            matched_project_markers=project_matches,
            matched_out_of_scope_markers=out_matches,
            mentioned_sections=mentioned_sections,
        )

    # Ambiguous general question without project vocabulary. Do not treat it as project-related.
    generic_matches = _contains_any(lowered, SAFE_GENERIC_PROJECT_WORDS)
    if generic_matches:
        labels.append("generic_project_words_without_scope")

    return QueryIntentResult(
        intent=QueryIntent.OUT_OF_SCOPE_CANDIDATE,
        confidence=0.58,
        is_project_related=False,
        labels=labels + ["no_project_signal"],
        matched_project_markers=project_matches,
        matched_out_of_scope_markers=out_matches,
        mentioned_sections=mentioned_sections,
    )
