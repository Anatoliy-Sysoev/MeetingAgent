from __future__ import annotations

import re

from .models import ChatSource


SOURCE_REF_RE = re.compile(r"\[(S\d+(?:\s*,\s*S\d+)*)\]")
SINGLE_SOURCE_RE = re.compile(r"S\d+")
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
STRUCTURAL_HEADINGS = {
    "краткий ответ",
    "обоснование",
    "источники",
    "ответ",
}


def extract_source_refs(text: str) -> list[str]:
    refs: list[str] = []
    for match in SOURCE_REF_RE.finditer(text or ""):
        for ref in SINGLE_SOURCE_RE.findall(match.group(1)):
            if ref not in refs:
                refs.append(ref)
    return refs


def _word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-zА-Яа-я0-9_]+", text or ""))


def _citation_units(text: str) -> list[str]:
    """Return claim-like units for citation coverage checks.

    The check intentionally avoids splitting by punctuation because valid model output
    often puts citations after a sentence as: "Факт. [S1]". Splitting on the dot would
    detach [S1] into a separate fragment and create a false validation failure.
    """
    units: list[str] = []
    for raw_line in (text or "").splitlines():
        line = raw_line.strip(" -\t")
        if not line:
            continue
        normalized = line.lower().rstrip(":")
        if normalized in STRUCTURAL_HEADINGS:
            continue
        if SOURCE_REF_RE.fullmatch(line):
            continue
        if _word_count(line) < 3 and not extract_source_refs(line):
            continue
        units.append(line)
    return units


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

            units = _citation_units(text)
            if len(units) >= 3:
                cited_units = sum(1 for unit in units if extract_source_refs(unit))
                coverage = cited_units / len(units)
                if coverage < 0.35:
                    errors.append(f"citation_coverage_too_low:{coverage:.3f}")

        return not errors, errors
