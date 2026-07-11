from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "46_ci_verify.py"
SPEC = importlib.util.spec_from_file_location("meetingagent_ci_verify", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
build_diff_commands = MODULE.build_diff_commands


def test_local_runner_checks_worktree_and_index() -> None:
    assert build_diff_commands({}) == [
        ["git", "diff", "--check"],
        ["git", "diff", "--cached", "--check"],
    ]


def test_ci_runner_checks_explicit_base_and_head() -> None:
    assert build_diff_commands(
        {"GITHUB_BASE_SHA": "base-sha", "GITHUB_HEAD_SHA": "head-sha"}
    ) == [["git", "diff", "--check", "base-sha", "head-sha"]]


def test_initial_push_uses_head_parent_when_before_is_zero() -> None:
    assert build_diff_commands(
        {"GITHUB_BASE_SHA": "0" * 40, "GITHUB_HEAD_SHA": "head-sha"}
    ) == [["git", "diff", "--check", "head-sha^", "head-sha"]]


def test_ci_range_must_be_complete() -> None:
    with pytest.raises(ValueError, match="must be set together"):
        build_diff_commands({"GITHUB_BASE_SHA": "base-only"})


def test_workflow_runs_full_canonical_verifier_with_minimal_permissions() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "permissions:\n  contents: read" in workflow
    assert "fetch-depth: 0" in workflow
    assert "cache: pip" in workflow
    assert "timeout-minutes: 20" in workflow
    assert "python scripts/46_ci_verify.py" in workflow
    assert "pytest tests/asu_june_bot" not in workflow
    assert "cancel-in-progress: true" in workflow
