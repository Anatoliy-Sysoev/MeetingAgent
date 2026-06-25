from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

VALID_CASE_LABELS: frozenset[str] = frozenset({
    "correct",
    "false_refuse",
    "false_clarify",
    "bad_source",
    "needs_case",
    "off_topic_ok",
    "needs_review",
})

VALID_CASE_TYPES: frozenset[str] = frozenset({
    "guard_false_refuse",
    "guard_false_clarify",
    "guard_off_topic_allowed",
    "retrieval_bad_source",
    "candidate",
    "needs_review",
    "positive_regression",
    "unknown",
})

_REQUIRED_FIELDS: tuple[str, ...] = (
    "case_id",
    "run_id",
    "query",
    "label",
    "case_type",
    "observed_guard_decision",
    "expected_guard_decision",
    "needs_manual_expected",
    "observed_status",
    "metadata",
)

# Keys whose presence in any exported case indicates a security leak.
_FORBIDDEN_KEYS: frozenset[str] = frozenset({
    "prompt_sources",
    "prompt",
    "full_prompt",
    "manual_label",
})

# Source sub-fields that must not appear in exported cases.
_FORBIDDEN_SOURCE_KEYS: frozenset[str] = frozenset({
    "path",
    "file_path",
    "abs_path",
    "local_path",
})


@dataclass(slots=True)
class GuardRegressionCase:
    case_id: str
    run_id: str
    query: str
    label: str
    case_type: str
    observed_guard_decision: str | None
    expected_guard_decision: str | None
    needs_manual_expected: bool
    observed_status: str | None
    metadata: dict[str, Any]
    manual_issue: str | None = None
    comment: str | None = None
    source_refs: list[str] = field(default_factory=list)
    source_titles: list[str] = field(default_factory=list)
    answer_preview: str | None = None
    created_at: str | None = None


class GuardCaseValidationError(ValueError):
    """Raised when a case payload fails schema validation."""


def validate_guard_case_payload(payload: dict[str, Any]) -> GuardRegressionCase:
    """Validate a parsed case dict and return a GuardRegressionCase.

    Raises GuardCaseValidationError on any schema violation.
    """
    missing = [f for f in _REQUIRED_FIELDS if f not in payload]
    if missing:
        raise GuardCaseValidationError(f"Missing required fields: {missing}")

    label = payload["label"]
    if label not in VALID_CASE_LABELS:
        raise GuardCaseValidationError(f"Unknown label: {label!r}")

    case_type = payload["case_type"]
    if case_type not in VALID_CASE_TYPES:
        raise GuardCaseValidationError(f"Unknown case_type: {case_type!r}")

    needs_manual = payload["needs_manual_expected"]
    if not isinstance(needs_manual, bool):
        raise GuardCaseValidationError(
            f"needs_manual_expected must be bool, got {type(needs_manual).__name__}"
        )

    metadata = payload["metadata"]
    if not isinstance(metadata, dict):
        raise GuardCaseValidationError(
            f"metadata must be a dict, got {type(metadata).__name__}"
        )

    return GuardRegressionCase(
        case_id=str(payload["case_id"]),
        run_id=str(payload["run_id"]),
        query=str(payload["query"]),
        label=label,
        case_type=case_type,
        observed_guard_decision=payload["observed_guard_decision"],
        expected_guard_decision=payload["expected_guard_decision"],
        needs_manual_expected=needs_manual,
        observed_status=payload.get("observed_status"),
        metadata=metadata,
        manual_issue=payload.get("manual_issue"),
        comment=payload.get("comment"),
        source_refs=list(payload.get("source_refs") or []),
        source_titles=list(payload.get("source_titles") or []),
        answer_preview=payload.get("answer_preview"),
        created_at=payload.get("created_at"),
    )


def case_contains_forbidden_keys(payload: dict[str, Any]) -> list[str]:
    """Return a list of forbidden key names found in the case payload.

    Checks top-level keys and source sub-dicts under 'sources' (legacy field).
    Returns an empty list if no forbidden keys are found.
    """
    found: list[str] = []
    for key in _FORBIDDEN_KEYS:
        if key in payload:
            found.append(key)
    # Check nested sources list if present (shouldn't be in exported cases, but guard anyway).
    sources = payload.get("sources")
    if isinstance(sources, list):
        for src in sources:
            if isinstance(src, dict):
                for key in _FORBIDDEN_SOURCE_KEYS:
                    if key in src and key not in found:
                        found.append(f"sources[].{key}")
    return found


def load_guard_cases(
    path: Path,
    *,
    strict: bool = True,
) -> list[GuardRegressionCase]:
    """Load and validate GuardRegressionCase records from a JSONL file.

    Args:
        path: path to the JSONL case file.
        strict: if True, raise on any malformed JSON line or validation error.
                if False, skip malformed/invalid lines silently.

    Returns list of validated GuardRegressionCase records.
    Raises FileNotFoundError if path does not exist (regardless of strict).
    """
    cases: list[GuardRegressionCase] = []
    with path.open(encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            stripped = raw.strip()
            if not stripped:
                continue
            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError as exc:
                if strict:
                    raise GuardCaseValidationError(
                        f"Malformed JSON at line {lineno}: {exc}"
                    ) from exc
                continue
            if not isinstance(obj, dict):
                if strict:
                    raise GuardCaseValidationError(
                        f"Line {lineno}: expected JSON object, got {type(obj).__name__}"
                    )
                continue
            try:
                cases.append(validate_guard_case_payload(obj))
            except GuardCaseValidationError:
                if strict:
                    raise
                continue
    return cases
