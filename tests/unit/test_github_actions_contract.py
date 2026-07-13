from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = ROOT / ".github" / "workflows"

REVIEWED_NODE24_ACTIONS = {
    "actions/checkout": "v7",
    "actions/deploy-pages": "v5",
    "actions/setup-python": "v6",
    "actions/upload-pages-artifact": "v5",
}

USES_RE = re.compile(
    r"^\s*uses:\s*['\"]?(?P<action>actions/[^@\s'\"]+)@(?P<ref>[^\s#'\"]+)",
    re.MULTILINE,
)


def _official_action_uses() -> list[tuple[str, str, str]]:
    uses: list[tuple[str, str, str]] = []
    workflow_paths = sorted(WORKFLOWS_DIR.glob("*.y*ml"))
    assert workflow_paths, "No GitHub Actions workflows were found"

    for workflow_path in workflow_paths:
        content = workflow_path.read_text(encoding="utf-8")
        for match in USES_RE.finditer(content):
            uses.append(
                (
                    workflow_path.relative_to(ROOT).as_posix(),
                    match.group("action"),
                    match.group("ref"),
                )
            )
    return uses


def test_all_official_actions_use_reviewed_node24_versions() -> None:
    uses = _official_action_uses()
    assert uses, "No official actions/* references were found"

    unreviewed = sorted(
        {action for _, action, _ in uses if action not in REVIEWED_NODE24_ACTIONS}
    )
    assert not unreviewed, (
        "Review the runtime and add every new official action to "
        f"REVIEWED_NODE24_ACTIONS: {unreviewed}"
    )

    stale = [
        f"{path}: {action}@{ref} (expected @{REVIEWED_NODE24_ACTIONS[action]})"
        for path, action, ref in uses
        if ref != REVIEWED_NODE24_ACTIONS[action]
    ]
    assert not stale, "Stale or unreviewed action versions:\n" + "\n".join(stale)


def test_every_reviewed_action_is_used_by_a_workflow() -> None:
    used_actions = {action for _, action, _ in _official_action_uses()}
    assert used_actions == set(REVIEWED_NODE24_ACTIONS)
