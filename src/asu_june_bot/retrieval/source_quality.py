from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any

from .models import SearchResult
from .query_intent import QueryIntent, QueryIntentResult


MIN_STRONG_TEXT_CHARS = 220
MIN_STRONG_WORDS = 28

CAPTION_MARKERS = {
    "рисунок",
    "рис.",
    "диаграмма",
    "uml",
    "sequence",
    "plantuml",
    "скриншот",
    "изображение",
}

STRUCTURAL_MARKERS = {
    "таблица",
    "заголовки:",
    "контекст:",
    "история изменений",
    "используемые сокращения",
    "связанные документы",
}

LOW_EVIDENCE_MARKERS = {
    "нет данных",
    "n/a",
    "не применимо",
    "требуется уточнение",
}


@dataclass(slots=True)
class SourceQualityAssessment:
    level: str
    weak: bool
    reasons: list[str]
    text_chars: int
    word_count: int
    primary_eligible: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "weak": self.weak,
            "reasons": self.reasons,
            "text_chars": self.text_chars,
            "word_count": self.word_count,
            "primary_eligible": self.primary_eligible,
        }


def _norm(text: str) -> str:
    return " ".join((text or "").lower().replace("ё", "е").split())


def _word_count(text: str) -> int:
    return len(re.findall(r"[a-zа-я0-9_]+", text, flags=re.IGNORECASE | re.UNICODE))


def _metadata_text(result: SearchResult) -> str:
    metadata = result.metadata or {}
    parts = [
        metadata.get("document_type"),
        metadata.get("relative_path"),
        metadata.get("title"),
        metadata.get("section"),
        metadata.get("sections"),
        metadata.get("requirement_id"),
    ]
    return _norm(" ".join(str(part or "") for part in parts))


def _rerank_labels(result: SearchResult) -> set[str]:
    return {str(label) for label in (result.diagnostics or {}).get("rerank_labels") or []}


def _is_nsi_regulation_inventory_source(result: SearchResult, text: str, metadata_text: str) -> bool:
    metadata = result.metadata or {}
    if str(metadata.get("document_type") or "") != "Методика/Регламент НСИ":
        return False
    if "реестр замечаний" in metadata_text:
        return False
    labels = _rerank_labels(result)
    if "boost:nsi_regulation_route" not in labels:
        return False
    return any(
        marker in metadata_text or marker in text
        for marker in (
            "регламент_ведения",
            "регламент ведения",
            "мвд_",
            "мвд ",
            "методика ведения",
            "методика ведения данных справочника",
        )
    )


def _is_nsi_registry_note(result: SearchResult, metadata_text: str) -> bool:
    metadata = result.metadata or {}
    if str(metadata.get("document_type") or "") != "Методика/Регламент НСИ":
        return False
    return "реестр замечаний" in metadata_text and "boost:nsi_regulation_route" in _rerank_labels(result)


def _is_nsi_reference_inventory_source(result: SearchResult, text: str) -> bool:
    metadata = result.metadata or {}
    if str(metadata.get("document_type") or "") not in {"Реестр НСИ", "Справочник НСИ", "СоИ Справочники"}:
        return False
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
    )


def _has_exact_requirement(result: SearchResult, intent: QueryIntentResult) -> bool:
    if not intent.mentioned_sections:
        return False
    metadata = result.metadata or {}
    requirement_id = str(metadata.get("requirement_id") or "")
    sections = {str(item) for item in (metadata.get("sections") or [])}
    text = result.text or ""
    for section in intent.mentioned_sections:
        if section == requirement_id or section in sections:
            return True
        if re.search(rf"(?<!\d){re.escape(section)}(?:\.|\b)", text):
            return True
    return False


def assess_source_quality(result: SearchResult, intent: QueryIntentResult | None = None) -> SourceQualityAssessment:
    text = _norm(result.text or "")
    metadata_text = _metadata_text(result)
    text_chars = len(text)
    words = _word_count(text)
    reasons: list[str] = []

    if text_chars < MIN_STRONG_TEXT_CHARS:
        reasons.append("short_text")
    if words < MIN_STRONG_WORDS:
        reasons.append("low_word_count")
    if any(marker in text or marker in metadata_text for marker in CAPTION_MARKERS):
        reasons.append("caption_or_diagram_like")
    if any(marker in text for marker in STRUCTURAL_MARKERS) and words < 55:
        reasons.append("short_structural_fragment")
    if any(marker in text for marker in LOW_EVIDENCE_MARKERS):
        reasons.append("low_evidence_marker")
    if "vector" in result.matched_by and "bm25" not in result.matched_by and text_chars < 500:
        reasons.append("short_vector_only")
    if _is_nsi_registry_note(result, metadata_text):
        reasons.append("nsi_registry_note")

    exact_requirement = bool(intent and _has_exact_requirement(result, intent))
    if exact_requirement:
        # Exact requirement fragments may be short but still critical.
        reasons = [reason for reason in reasons if reason not in {"short_text", "low_word_count", "short_vector_only"}]

    if _is_nsi_regulation_inventory_source(result, text, metadata_text):
        # For inventory/list questions about NSI regulation documents, a table of contents
        # or a structural title chunk is valid evidence of the document itself.
        reasons = [
            reason
            for reason in reasons
            if reason not in {"caption_or_diagram_like", "short_structural_fragment", "short_vector_only"}
        ]

    if _is_nsi_reference_inventory_source(result, text):
        # Short table rows with concrete NSI dictionaries/attributes are valid list evidence.
        reasons = [
            reason
            for reason in reasons
            if reason not in {"short_text", "low_word_count", "short_structural_fragment", "short_vector_only"}
        ]

    weak = bool(reasons)
    if not weak:
        return SourceQualityAssessment(
            level="strong",
            weak=False,
            reasons=[],
            text_chars=text_chars,
            word_count=words,
            primary_eligible=True,
        )

    hard_weak_reasons = {"caption_or_diagram_like", "short_structural_fragment", "low_evidence_marker", "nsi_registry_note"}
    primary_eligible = exact_requirement or not bool(set(reasons) & hard_weak_reasons)
    if intent and intent.intent == QueryIntent.DOCUMENT_OVERVIEW and set(reasons) & {"short_text", "low_word_count"}:
        primary_eligible = False

    return SourceQualityAssessment(
        level="weak",
        weak=True,
        reasons=reasons,
        text_chars=text_chars,
        word_count=words,
        primary_eligible=primary_eligible,
    )


def with_source_quality(result: SearchResult, intent: QueryIntentResult | None = None) -> SearchResult:
    assessment = assess_source_quality(result, intent)
    diagnostics = dict(result.diagnostics or {})
    diagnostics["source_quality"] = assessment.to_dict()
    if assessment.weak:
        labels = list(diagnostics.get("rerank_labels") or [])
        labels.append("quality:weak_source")
        diagnostics["rerank_labels"] = labels
    return replace(result, diagnostics=diagnostics)


def source_quality(result: SearchResult) -> dict[str, Any]:
    diagnostics = result.diagnostics or {}
    value = diagnostics.get("source_quality")
    return value if isinstance(value, dict) else {}


def is_weak_source(result: SearchResult) -> bool:
    return bool(source_quality(result).get("weak"))


def is_primary_eligible(result: SearchResult) -> bool:
    quality = source_quality(result)
    if not quality:
        return True
    return bool(quality.get("primary_eligible"))
