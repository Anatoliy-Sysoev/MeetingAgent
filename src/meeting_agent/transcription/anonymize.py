from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping


SUPPORTED_KINDS = {"person", "org", "path", "url", "email", "phone", "identifier"}


@dataclass
class Replacement:
    kind: str
    original: str
    placeholder: str
    count: int = 0

    @property
    def original_sha256(self) -> str:
        return hashlib.sha256(self.original.encode("utf-8")).hexdigest()

    def public_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "placeholder": self.placeholder,
            "count": self.count,
        }

    def private_dict(self) -> dict[str, Any]:
        data = self.public_dict()
        data["original"] = self.original
        data["original_sha256"] = self.original_sha256
        return data


@dataclass
class AnonymizationResult:
    text: str
    replacements: dict[str, Replacement]
    warnings: list[str] = field(default_factory=list)

    @property
    def replacements_count(self) -> int:
        return sum(replacement.count for replacement in self.replacements.values())


@dataclass(frozen=True)
class AnonymizationOptions:
    custom_terms: Mapping[str, Iterable[str]] = field(default_factory=dict)
    detect_person_names: bool = True
    detect_org_legal_names: bool = True
    detect_internal_identifiers: bool = True


_URL_RE = re.compile(r"(?i)\b(?:https?://|www\.)[^\s<>)\"']+")
_EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_PHONE_RE = re.compile(r"(?<!\w)(?:\+?7|8)?[\s(-]*\d{3}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}(?!\w)")
_WIN_PATH_RE = re.compile(r"(?i)(?<!\w)(?:[A-Z]:\\|\\\\)[^\s<>\"|?*]+")
_UNIX_PATH_RE = re.compile(r"(?<!\w)/(?:Users|home|mnt|var|tmp|opt|data|srv)/[^\s<>\"']+")
_LEGAL_ORG_RE = re.compile(
    r"\b(?:ООО|АО|ПАО|ЗАО|НКО|ИП|LLC|Inc\.?|Ltd\.?)\s+[\"«]?[A-ZА-ЯЁ0-9][A-Za-zА-Яа-яЁё0-9 ._-]{2,80}[\"»]?",
    re.IGNORECASE,
)
_PERSON_RE = re.compile(
    r"\b[А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ][а-яё]{2,}(?:\s+[А-ЯЁ][а-яё]{2,})?\b"
)
_IDENTIFIER_RE = re.compile(r"(?<!\[)\b[А-ЯA-Z]{2,}[A-ZА-Я0-9]*(?:[-_./][A-ZА-Я0-9]{2,})+\b")
_PLACEHOLDER_RE = re.compile(r"^\[(?:PERSON|ORG|PATH|URL|EMAIL|PHONE|ID)_\d{3}\]$")
_TECHNICAL_SPEAKER_RE = re.compile(r"^(?:SPEAKER_(?:UNKNOWN|\d{1,4})|UNKNOWN)$")
_SAFE_SOURCE_LABELS = {"MIX", "MIC", "SYS"}
_PRESERVE_STRING_KEYS = {
    "segment_id",
    "utterance_id",
    "chunk_id",
    "speaker_label",
    "engine",
    "language",
}
_PRESERVE_LIST_KEYS = {"utterance_ids", "segment_ids", "chunk_ids"}


def _kind_label(kind: str) -> str:
    return {
        "person": "PERSON",
        "org": "ORG",
        "path": "PATH",
        "url": "URL",
        "email": "EMAIL",
        "phone": "PHONE",
        "identifier": "ID",
    }[kind]


def _normalize_kind(kind: str) -> str:
    normalized = kind.strip().lower()
    if normalized not in SUPPORTED_KINDS:
        raise ValueError(f"Unsupported anonymization kind: {kind}")
    return normalized


def _clean_term(value: Any) -> str:
    return " ".join(str(value or "").split())


def _is_safe_speaker_label(value: str) -> bool:
    return bool(_TECHNICAL_SPEAKER_RE.fullmatch(value.strip()))


def _is_safe_source_label(value: str) -> bool:
    return value.strip().upper() in _SAFE_SOURCE_LABELS


def _iter_custom_terms(custom_terms: Mapping[str, Iterable[str]]) -> list[tuple[str, str]]:
    terms: list[tuple[str, str]] = []
    for raw_kind, values in custom_terms.items():
        kind = _normalize_kind(raw_kind)
        for value in values:
            term = _clean_term(value)
            if term:
                terms.append((kind, term))
    terms.sort(key=lambda item: len(item[1]), reverse=True)
    return terms


class TranscriptAnonymizer:
    def __init__(self, options: AnonymizationOptions | None = None) -> None:
        self.options = options or AnonymizationOptions()
        self._by_original: dict[tuple[str, str], Replacement] = {}
        self._by_placeholder: dict[str, Replacement] = {}
        self.warnings: list[str] = []

    @property
    def replacements(self) -> dict[str, Replacement]:
        return dict(self._by_placeholder)

    def anonymize_text(self, text: str) -> str:
        result = str(text)

        for kind, term in _iter_custom_terms(self.options.custom_terms):
            result = self._replace_literal(result, kind, term)

        result = self._replace_regex(result, "url", _URL_RE)
        result = self._replace_regex(result, "email", _EMAIL_RE)
        result = self._replace_regex(result, "path", _WIN_PATH_RE)
        result = self._replace_regex(result, "path", _UNIX_PATH_RE)
        result = self._replace_regex(result, "phone", _PHONE_RE)
        if self.options.detect_org_legal_names:
            result = self._replace_regex(result, "org", _LEGAL_ORG_RE)
        if self.options.detect_person_names:
            result = self._replace_regex(result, "person", _PERSON_RE)
        if self.options.detect_internal_identifiers:
            result = self._replace_regex(result, "identifier", _IDENTIFIER_RE)
        return result

    def anonymize_value(self, value: Any, *, key: str | None = None) -> Any:
        if key in _PRESERVE_STRING_KEYS | _PRESERVE_LIST_KEYS:
            return value
        if key == "speaker":
            if isinstance(value, str) and _is_safe_speaker_label(value):
                return value
            return self.anonymize_value(value)
        if key == "source":
            if isinstance(value, str) and _is_safe_source_label(value):
                return value
            return self.anonymize_value(value)
        if key == "speakers" and isinstance(value, list):
            return [
                item if isinstance(item, str) and _is_safe_speaker_label(item) else self.anonymize_value(item)
                for item in value
            ]
        if isinstance(value, str):
            return self.anonymize_text(value)
        if isinstance(value, list):
            return [self.anonymize_value(item) for item in value]
        if isinstance(value, dict):
            return {str(child_key): self.anonymize_value(item, key=str(child_key)) for child_key, item in value.items()}
        return value

    def anonymize_rows(self, rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
        return [self.anonymize_value(dict(row)) for row in rows]

    def result_for_text(self, text: str) -> AnonymizationResult:
        anonymized = self.anonymize_text(text)
        return AnonymizationResult(text=anonymized, replacements=self.replacements, warnings=list(self.warnings))

    def _replacement_for(self, kind: str, original: str) -> Replacement:
        key = (kind, original)
        existing = self._by_original.get(key)
        if existing is not None:
            return existing
        index = 1 + sum(1 for replacement in self._by_original.values() if replacement.kind == kind)
        placeholder = f"[{_kind_label(kind)}_{index:03d}]"
        replacement = Replacement(kind=kind, original=original, placeholder=placeholder)
        self._by_original[key] = replacement
        self._by_placeholder[placeholder] = replacement
        return replacement

    def _replace_literal(self, text: str, kind: str, term: str) -> str:
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        return self._replace_regex(text, kind, pattern)

    def _replace_regex(self, text: str, kind: str, pattern: re.Pattern[str]) -> str:
        def repl(match: re.Match[str]) -> str:
            original = match.group(0).strip()
            if not original:
                return match.group(0)
            if _PLACEHOLDER_RE.fullmatch(original):
                return original
            replacement = self._replacement_for(kind, original)
            replacement.count += 1
            return replacement.placeholder

        return pattern.sub(repl, text)


def read_jsonl_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_number, line in enumerate(fh, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"JSONL row must be an object at {path}:{line_number}")
            rows.append(row)
    return rows


def write_jsonl_rows(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(dict(row), ensure_ascii=False) + "\n")
    tmp_path.replace(path)


def load_terms_file(path: Path) -> dict[str, list[str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Terms file must be a JSON object")
    terms: dict[str, list[str]] = {}
    for raw_kind, values in data.items():
        kind = _normalize_kind(str(raw_kind))
        if not isinstance(values, list):
            raise ValueError(f"Terms file key '{raw_kind}' must contain a list")
        terms[kind] = [_clean_term(value) for value in values if _clean_term(value)]
    return terms


def terms_from_meeting_card(card: Mapping[str, Any]) -> dict[str, list[str]]:
    terms: dict[str, list[str]] = {"person": [], "org": []}
    raw_mapping = card.get("speaker_mapping")
    if isinstance(raw_mapping, dict):
        for value in raw_mapping.values():
            if not isinstance(value, dict):
                continue
            name = _clean_term(value.get("name"))
            role = _clean_term(value.get("role"))
            if name:
                terms["person"].append(name)
            if role:
                terms.setdefault("identifier", []).append(role)
    title = _clean_term(card.get("title"))
    if title:
        terms.setdefault("identifier", []).append(title)
    return {kind: values for kind, values in terms.items() if values}


def merge_terms(*items: Mapping[str, Iterable[str]]) -> dict[str, list[str]]:
    merged: dict[str, list[str]] = {}
    for item in items:
        for raw_kind, values in item.items():
            kind = _normalize_kind(raw_kind)
            target = merged.setdefault(kind, [])
            for value in values:
                term = _clean_term(value)
                if term and term not in target:
                    target.append(term)
    return merged


def build_report(
    *,
    input_path: Path,
    output_files: Mapping[str, Path],
    anonymizer: TranscriptAnonymizer,
    rows_read: int | None = None,
    markdown_chars: int | None = None,
) -> dict[str, Any]:
    return {
        "input_name": input_path.name,
        "input_suffix": input_path.suffix.lower(),
        "outputs": {key: path.name for key, path in output_files.items()},
        "rows_read": rows_read,
        "markdown_chars": markdown_chars,
        "replacements_count": sum(item.count for item in anonymizer.replacements.values()),
        "replacements": [item.public_dict() for item in sorted(anonymizer.replacements.values(), key=lambda item: item.placeholder)],
        "warnings": [
            "Heuristic anonymization is not a privacy guarantee; manually review output before publication.",
            "Public report stores placeholders and counts only; original values and hashes are private-map only.",
            *anonymizer.warnings,
        ],
    }


def write_json_atomic(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(dict(data), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(path)
