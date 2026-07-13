from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def _updates() -> list[dict[str, object]]:
    config = yaml.safe_load(
        (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
    )
    assert config["version"] == 2
    return config["updates"]


def _ecosystem(name: str) -> dict[str, object]:
    matches = [
        update for update in _updates() if update.get("package-ecosystem") == name
    ]
    assert len(matches) == 1
    return matches[0]


def test_python_updates_are_not_combined_by_a_catch_all_group() -> None:
    pip = _ecosystem("pip")
    assert pip.get("groups") in (None, {})
    assert pip["schedule"] == {"interval": "weekly"}
    assert pip["open-pull-requests-limit"] == 5


def test_actions_group_remains_bounded_and_explicit() -> None:
    actions = _ecosystem("github-actions")
    assert actions["groups"] == {"github-actions": {"patterns": ["*"]}}
    assert actions["schedule"] == {"interval": "weekly"}
    assert actions["open-pull-requests-limit"] == 5
