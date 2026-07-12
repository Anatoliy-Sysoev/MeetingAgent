from __future__ import annotations

import importlib
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
for import_root in (SRC, SCRIPTS):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from legacy_entrypoint import LEGACY_ENTRYPOINTS  # noqa: E402
from meeting_agent.transcription import (  # noqa: E402
    DEFAULT_FASTER_WHISPER_MODEL,
    FasterWhisperConfig,
)


def _inventory() -> dict:
    raw = (ROOT / "configs" / "runtime_inventory.yaml").read_bytes()
    assert len(raw) <= 64 * 1024
    data = yaml.safe_load(raw.decode("utf-8"))
    assert isinstance(data, dict)
    assert data.get("version") == 1
    return data


INVENTORY = _inventory()


def _load_script(name: str, relative_path: str):
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _flatten(section: str) -> list[str]:
    groups = INVENTORY[section]
    assert set(groups) == {"current", "compatibility", "planned"}
    values = [item for status in groups.values() for item in status]
    assert len(values) == len(set(values))
    return values


def test_inventory_covers_every_script_exactly_once() -> None:
    actual = {
        path.relative_to(ROOT).as_posix()
        for path in SCRIPTS.rglob("*")
        if path.is_file() and path.suffix.lower() in {".py", ".ps1"}
    }
    actual.update(path.name for path in ROOT.glob("*.ps1") if path.is_file())

    assert set(_flatten("scripts")) == actual


def test_inventory_covers_every_python_package_exactly_once() -> None:
    actual = {
        init.parent.relative_to(SRC).as_posix().replace("/", ".")
        for init in SRC.rglob("__init__.py")
    }

    assert set(_flatten("packages")) == actual


def test_removed_paths_have_no_committed_files() -> None:
    removed = INVENTORY.get("removed_paths")
    assert isinstance(removed, list) and removed
    for relative_path in removed:
        path = ROOT / relative_path
        assert not path.exists() or not any(candidate.is_file() for candidate in path.rglob("*"))


def test_current_and_compatibility_packages_import() -> None:
    for package in _flatten("packages"):
        assert importlib.import_module(package) is not None


@pytest.mark.parametrize("relative_path", INVENTORY["supported_cli_help"])
def test_supported_cli_help_smoke(relative_path: str) -> None:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join((str(SRC), str(SCRIPTS)))
    result = subprocess.run(
        [sys.executable, str(ROOT / relative_path), "--help"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout.lower()


def test_compatibility_entrypoints_emit_migration_warning() -> None:
    compatibility = set(INVENTORY["scripts"]["compatibility"])
    registered = {f"scripts/{name}" for name in LEGACY_ENTRYPOINTS}
    expected_entrypoints = {path for path in compatibility if Path(path).name in LEGACY_ENTRYPOINTS}
    assert registered == expected_entrypoints
    for relative_path in expected_entrypoints:
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        assert "warn_legacy_entrypoint(__file__)" in source

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/06_transcribe_meeting.py"), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    assert result.returncode == 0
    assert "DEPRECATED:" in result.stderr
    assert "docs/en/runtime_ownership.md" in result.stderr

    powershell_paths = {path for path in compatibility if path.lower().endswith(".ps1")}
    assert powershell_paths
    for relative_path in powershell_paths:
        source = (ROOT / relative_path).read_text(encoding="utf-8-sig")
        assert "MEETINGAGENT_SUPPRESS_LEGACY_WARNING" in source
        assert "Write-Warning" in source


def test_legacy_warning_can_be_suppressed_for_existing_automation() -> None:
    env = dict(os.environ)
    env["MEETINGAGENT_SUPPRESS_LEGACY_WARNING"] = "1"
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/06_transcribe_meeting.py"), "--help"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )

    assert result.returncode == 0
    assert "DEPRECATED:" not in result.stderr


def test_retained_transcription_defaults_match_product_profile(monkeypatch) -> None:
    assert DEFAULT_FASTER_WHISPER_MODEL == "large-v3-turbo"
    assert FasterWhisperConfig().model == DEFAULT_FASTER_WHISPER_MODEL

    transcribe22 = _load_script(
        "runtime_inventory_transcribe22", "scripts/22_transcribe_meeting.py"
    )
    monkeypatch.setattr(transcribe22, "transcription_config", lambda: {})
    args22 = transcribe22.parse_args(
        ["--meeting-dir", "synthetic-meeting", "--engine", "faster-whisper"]
    )
    assert args22.model == DEFAULT_FASTER_WHISPER_MODEL

    pipeline08 = _load_script(
        "runtime_inventory_pipeline08", "scripts/08_process_meeting_pipeline.py"
    )
    args08 = pipeline08.parse_args(["--meeting-dir", "synthetic-meeting"])
    assert args08.asr_model == DEFAULT_FASTER_WHISPER_MODEL

    example = yaml.safe_load((ROOT / "config.example.yaml").read_text(encoding="utf-8"))
    assert example["transcription"]["model"] == DEFAULT_FASTER_WHISPER_MODEL
    assert "live_transcription" not in example
