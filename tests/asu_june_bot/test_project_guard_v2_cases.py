from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.guardrails.models import GuardAction  # noqa: E402
from asu_june_bot.guardrails.project_guard import ProjectGuard  # noqa: E402

CASES_PATH = Path(__file__).with_name("guard_v2_cases.jsonl")


def load_cases() -> list[dict]:
    rows: list[dict] = []
    with CASES_PATH.open("r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if stripped:
                rows.append(json.loads(stripped))
    return rows


def action_to_status(action: GuardAction) -> str:
    if action == GuardAction.ALLOW:
        return "ok"
    if action == GuardAction.CLARIFY:
        return "clarify"
    return "refused"


@pytest.mark.parametrize("case", load_cases(), ids=lambda case: case["id"])
def test_project_guard_v2_regression_cases(case: dict) -> None:
    result = ProjectGuard().evaluate_v2(case["query"])
    actual_status = action_to_status(result.action)
    actual_scope = result.aggregate.scope.value

    assert actual_status == case["expected_status"]
    if case.get("expected_scope") is not None:
        assert actual_scope == case["expected_scope"]
    if case.get("expected_reason") is not None:
        assert result.reason == case["expected_reason"]

    if actual_status in {"refused", "clarify"}:
        assert not result.allowed
