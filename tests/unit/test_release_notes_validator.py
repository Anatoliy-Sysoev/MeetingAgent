from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "45_validate_release_notes.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("release_notes_validator_45", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_current_release_notes_validate() -> None:
    script = _load_script()

    assert script.main(["--version", "0.1.0"]) == 0


def test_version_lists_must_match(monkeypatch) -> None:
    script = _load_script()

    def fake_read_text(path: Path) -> str:
        if path.name == "CHANGELOG.md":
            return "# Changelog\n\n## v0.1.0\n\n### Added\n\n- x\n"
        if path.name == "CHANGELOG.ru.md":
            return "# История\n\n## v0.2.0\n\n### Добавлено\n\n- x\n"
        return ""

    monkeypatch.setattr(script, "read_text", fake_read_text)

    try:
        script.validate("0.1.0")
    except script.ReleaseNotesError as exc:
        assert "version lists differ" in str(exc)
    else:
        raise AssertionError("expected ReleaseNotesError")


def test_placeholders_are_rejected(monkeypatch) -> None:
    script = _load_script()

    def fake_read_text(path: Path) -> str:
        if path.name == "CHANGELOG.md":
            return "# Changelog\n\n## v0.1.0\n\n### Added\n\n- TBD\n"
        if path.name == "CHANGELOG.ru.md":
            return "# История\n\n## v0.1.0\n\n### Добавлено\n\n- x\n"
        return ""

    monkeypatch.setattr(script, "read_text", fake_read_text)

    try:
        script.validate("0.1.0")
    except script.ReleaseNotesError as exc:
        assert "placeholders" in str(exc)
    else:
        raise AssertionError("expected ReleaseNotesError")
