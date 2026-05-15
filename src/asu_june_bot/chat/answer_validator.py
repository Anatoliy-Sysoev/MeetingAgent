from __future__ import annotations

import re

from .models import ChatSource


SOURCE_REF_RE = re.compile(r"\[(S\d+(?:\s*,\s*S\d+)*)\]")
SINGLE_SOURCE_RE = re.compile(r"S\d+")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。！？])\s+|\n+")
NO_ANSWER_MARKERS = (
    "в переданных источниках данных недостаточно",
    "в предоставленных источниках информации для ответа",
    "в источниках нет информации",
    "нет данных для ответа",
    "недостаточно данных",
)
EXTERNAL_KNOWLEDGE_MARKERS = (
    "по общим данным",
    "обычно используется",
    "как правило",
    "насколько я знаю",
    "в целом такие системы",
    "вообще говоря",
)


def extract_source_refs(text: str) -> list[str]:
    refs: list[str] = []
    for match in SOURCE_REF_RE.finditer(text or ""):
        for ref in SINGLE_SOURCE_RE.findall(match.group(1)):
            if ref not in refs:
                refs.append(ref)
    return refs


def _word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-zА-Яа-я0-9_]+", text or ""))


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in SENTENCE_SPLIT_RE.split(text or "") if part.strip()]


class AnswerValidator:
    def __init__(self, min_answer_chars: int = 30, max_answer_chars: int = 8000, min_citation_density: float = 0.25) -> None:
        self.min_answer_chars = min_answer_chars
        self.max_answer_chars = max_answer_chars
        self.min_citation_density = min_citation_density

    def validate_answered(self, answer: str, sources: list[ChatSource]) -> tuple[bool, list[str]]:
        errors: list[str] = []
        text = (answer or "").strip()
        lowered = text.lower()
        if not text:
            errors.append("empty_answer")
            return False, errors
        if len(text) < self.min_answer_chars:
            errors.append("answer_too_short")
        if len(text) > self.max_answer_chars:
            errors.append("answer_too_long")
        if not sources:
            errors.append("missing_sources")

        if any(marker in lowered for marker in NO_ANSWER_MARKERS):
            # Honest no-answer is acceptable only for future NO_ANSWER status; current ChatService treats it as not answered.
            errors.append("no_answer_marker_present")

        external_markers = [marker for marker in EXTERNAL_KNOWLEDGE_MARKERS if marker in lowered]
        if external_markers:
            errors.append("external_knowledge_markers:" + ",".join(external_markers))

        used_refs = extract_source_refs(text)
        if not used_refs:
            errors.append("missing_source_references")
        if sources:
            allowed_refs = {source.source_ref for source in sources}
            unknown_refs = sorted(set(used_refs) - allowed_refs)
            if unknown_refs:
                errors.append("unknown_source_references:" + ",".join(unknown_refs))

        if used_refs:
            words = max(_word_count(text), 1)
            citation_density = (len(used_refs) / words) * 100
            if words >= 80 and citation_density < self.min_citation_density:
                errors.append(f"citation_density_too_low:{citation_density:.3f}")

            sentences = _sentences(text)
            if len(sentences) >= 3:
                cited_sentences = sum(1 for sentence in sentences if extract_source_refs(sentence))
                coverage = cited_sentences / len(sentences)
                if coverage < 0.35:
                    errors.append(f"citation_coverage_too_low:{coverage:.3f}")

        return not errors, errors
