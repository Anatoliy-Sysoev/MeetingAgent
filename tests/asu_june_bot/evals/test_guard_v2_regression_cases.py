"""Regression harness for guard_v2_cases.jsonl.

Mode 1 — committed fixture (always runs):
    tests/fixtures/evals/guard_v2_cases.sample.jsonl

Mode 2 — local runtime file (skips if absent):
    data/asu_june_bot/guard_v2_cases.jsonl

No LLM calls, no network, no private runtime files committed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.evals.guard_case_loader import (  # noqa: E402
    VALID_CASE_LABELS,
    case_contains_forbidden_keys,
    load_guard_cases,
    validate_guard_case_payload,
)

SAMPLE_FIXTURE = ROOT / "tests" / "fixtures" / "evals" / "guard_v2_cases.sample.jsonl"
RUNTIME_CASES = ROOT / "data" / "asu_june_bot" / "guard_v2_cases.jsonl"


# ---------------------------------------------------------------------------
# Mode 1 — committed sample fixture (always runs)
# ---------------------------------------------------------------------------

class TestSampleFixtureRegression:
    """Full regression assertions against the committed sample fixture."""

    def setup_method(self) -> None:
        self.cases = load_guard_cases(SAMPLE_FIXTURE)

    def test_fixture_parses_all_rows(self) -> None:
        assert len(self.cases) > 0

    def test_fixture_schema_valid(self) -> None:
        # Already validated by load_guard_cases (strict=True by default).
        # This test exists as an explicit regression gate.
        for c in self.cases:
            assert c.case_id.startswith("run_")
            assert c.label in VALID_CASE_LABELS

    def test_fixture_no_prompt_internals(self) -> None:
        raw_text = SAMPLE_FIXTURE.read_text(encoding="utf-8")
        assert "prompt_sources" not in raw_text
        assert "manual_label" not in raw_text

    def test_fixture_no_source_paths(self) -> None:
        with SAMPLE_FIXTURE.open(encoding="utf-8") as fh:
            for line in fh:
                stripped = line.strip()
                if not stripped:
                    continue
                payload = json.loads(stripped)
                found = case_contains_forbidden_keys(payload)
                assert found == [], f"Forbidden keys in {payload.get('case_id')}: {found}"

    def test_fixture_deterministic_guard_expectations(self) -> None:
        """Cases with needs_manual_expected=False must have a concrete expected decision."""
        for c in self.cases:
            if not c.needs_manual_expected:
                assert c.expected_guard_decision is not None, (
                    f"Case {c.case_id} has needs_manual_expected=False "
                    f"but expected_guard_decision is None"
                )

    def test_fixture_manual_expected_cases_have_null_decision(self) -> None:
        """Cases flagged for manual review must not assert a concrete expectation."""
        for c in self.cases:
            if c.needs_manual_expected:
                assert c.expected_guard_decision is None, (
                    f"Case {c.case_id} has needs_manual_expected=True "
                    f"but expected_guard_decision={c.expected_guard_decision!r}"
                )

    def test_fixture_false_refuse_expectation(self) -> None:
        fr = [c for c in self.cases if c.label == "false_refuse"]
        assert fr, "Sample fixture must contain at least one false_refuse case"
        for c in fr:
            assert c.expected_guard_decision == "allow"
            assert c.case_type == "guard_false_refuse"

    def test_fixture_false_clarify_expectation(self) -> None:
        fc = [c for c in self.cases if c.label == "false_clarify"]
        assert fc, "Sample fixture must contain at least one false_clarify case"
        for c in fc:
            assert c.expected_guard_decision == "allow"
            assert c.case_type == "guard_false_clarify"

    def test_fixture_correct_regression(self) -> None:
        co = [c for c in self.cases if c.label == "correct"]
        assert co, "Sample fixture must contain at least one correct case"
        for c in co:
            assert c.case_type == "positive_regression"
            assert c.expected_guard_decision is not None

    def test_fixture_metadata_is_dict(self) -> None:
        for c in self.cases:
            assert isinstance(c.metadata, dict), f"Case {c.case_id}: metadata not a dict"


# ---------------------------------------------------------------------------
# Mode 2 — local runtime guard_v2_cases.jsonl (skips if absent)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not RUNTIME_CASES.exists(),
    reason="data/asu_june_bot/guard_v2_cases.jsonl not present (local only)",
)
class TestRuntimeCasesRegression:
    """Schema and security assertions against the local runtime export.

    This file is gitignored.  Tests in this class are skipped in CI and on
    fresh clones.  Run locally after generating via:
        python scripts/40_export_guard_v2_cases.py
    """

    def setup_method(self) -> None:
        self.cases = load_guard_cases(RUNTIME_CASES, strict=False)

    def test_runtime_cases_parse(self) -> None:
        assert isinstance(self.cases, list)

    def test_runtime_schema_valid(self) -> None:
        # Re-validate each case via the strict validator to catch any field
        # changes between export runs.
        with RUNTIME_CASES.open(encoding="utf-8") as fh:
            for lineno, raw in enumerate(fh, 1):
                stripped = raw.strip()
                if not stripped:
                    continue
                try:
                    obj = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict):
                    continue
                validate_guard_case_payload(obj)

    def test_runtime_no_prompt_internals(self) -> None:
        raw_text = RUNTIME_CASES.read_text(encoding="utf-8")
        assert "prompt_sources" not in raw_text

    def test_runtime_no_forbidden_keys(self) -> None:
        with RUNTIME_CASES.open(encoding="utf-8") as fh:
            for line in fh:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    payload = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                if not isinstance(payload, dict):
                    continue
                found = case_contains_forbidden_keys(payload)
                assert found == [], f"Forbidden keys in {payload.get('case_id')}: {found}"

    def test_runtime_labels_are_valid(self) -> None:
        for c in self.cases:
            assert c.label in VALID_CASE_LABELS, f"Unknown label {c.label!r} in {c.case_id}"

    def test_runtime_deterministic_expectations_consistent(self) -> None:
        for c in self.cases:
            if not c.needs_manual_expected:
                assert c.expected_guard_decision is not None, (
                    f"Case {c.case_id}: needs_manual_expected=False "
                    f"but expected_guard_decision is None"
                )
