"""Integration tests: pure guard API called with guard_v2_cases records.

The sample fixture uses university-domain queries (enrollment, cafeteria, etc.)
that do not match ASU project-specific keyword rules.  Calling
evaluate_guard_decision() on them will not produce results matching
expected_guard_decision from the fixture — that is expected and documented.

Deterministic assertion tests (expected_guard_decision matching) are skipped
with an explicit reason and left as the next task once real reviewed cases
from data/asu_june_bot/guard_v2_cases.jsonl are available.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.evals.guard_case_loader import load_guard_cases  # noqa: E402
from asu_june_bot.guard.decision import (  # noqa: E402
    VALID_DECISIONS,
    GuardDecisionResult,
    evaluate_guard_decision,
)

SAMPLE_FIXTURE = ROOT / "tests" / "fixtures" / "evals" / "guard_v2_cases.sample.jsonl"
RUNTIME_CASES = ROOT / "data" / "asu_june_bot" / "guard_v2_cases.jsonl"


# ---------------------------------------------------------------------------
# Pure API returns valid output for every query in the sample fixture
# ---------------------------------------------------------------------------

def test_pure_api_runs_on_all_fixture_queries() -> None:
    """evaluate_guard_decision must not raise for any fixture query."""
    cases = load_guard_cases(SAMPLE_FIXTURE)
    for case in cases:
        result = evaluate_guard_decision(case.query)
        assert isinstance(result, GuardDecisionResult)
        assert result.decision in VALID_DECISIONS, (
            f"Case {case.case_id}: unexpected decision {result.decision!r}"
        )


def test_pure_api_is_deterministic_over_fixture() -> None:
    """Same query must produce same decision across two calls."""
    cases = load_guard_cases(SAMPLE_FIXTURE)
    for case in cases:
        r1 = evaluate_guard_decision(case.query)
        r2 = evaluate_guard_decision(case.query)
        assert r1.decision == r2.decision, (
            f"Case {case.case_id}: non-deterministic decision"
        )


# ---------------------------------------------------------------------------
# Deterministic expected_guard_decision assertions — skipped (next task)
# ---------------------------------------------------------------------------

@pytest.mark.skip(
    reason=(
        "Sample fixture uses university-domain queries that do not match ASU "
        "project-specific keyword rules; expected_guard_decision in the fixture "
        "reflects reviewed runtime behavior, not rule-based evaluation of "
        "synthetic queries.  Activate once real project-domain cases from "
        "data/asu_june_bot/guard_v2_cases.jsonl are loaded."
    )
)
def test_fixture_deterministic_cases_match_pure_api() -> None:
    cases = load_guard_cases(SAMPLE_FIXTURE)
    deterministic = [
        c for c in cases
        if not c.needs_manual_expected
        and c.expected_guard_decision is not None
        and c.case_type.startswith("guard_")
    ]
    assert deterministic, "No deterministic cases to assert against"
    for case in deterministic:
        result = evaluate_guard_decision(case.query)
        assert result.decision == case.expected_guard_decision, (
            f"Case {case.case_id}: expected {case.expected_guard_decision!r}, "
            f"got {result.decision!r}"
        )


# ---------------------------------------------------------------------------
# Runtime file — skips if absent
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not RUNTIME_CASES.exists(),
    reason="data/asu_june_bot/guard_v2_cases.jsonl not present (local only)",
)
def test_pure_api_runs_on_runtime_cases() -> None:
    """Pure API must not raise for any query in the local runtime export."""
    cases = load_guard_cases(RUNTIME_CASES, strict=False)
    for case in cases:
        result = evaluate_guard_decision(case.query)
        assert result.decision in VALID_DECISIONS


@pytest.mark.skipif(
    not RUNTIME_CASES.exists(),
    reason="data/asu_june_bot/guard_v2_cases.jsonl not present (local only)",
)
def test_runtime_deterministic_cases_match_pure_api() -> None:
    """Assert expected_guard_decision for non-manual, non-null cases in runtime export.

    This is the active deterministic regression gate — it runs only when the
    local file exists and only against cases where needs_manual_expected=False
    and expected_guard_decision is not None and case_type starts with 'guard_'.
    """
    cases = load_guard_cases(RUNTIME_CASES, strict=False)
    deterministic = [
        c for c in cases
        if not c.needs_manual_expected
        and c.expected_guard_decision is not None
        and c.case_type.startswith("guard_")
    ]
    if not deterministic:
        pytest.skip("No deterministic guard cases in runtime export")
    failures = []
    for case in deterministic:
        result = evaluate_guard_decision(case.query)
        if result.decision != case.expected_guard_decision:
            failures.append(
                f"  {case.case_id}: expected={case.expected_guard_decision!r} "
                f"got={result.decision!r} reason={result.reason!r}"
            )
    assert not failures, "Guard decision mismatches:\n" + "\n".join(failures)
