from __future__ import annotations

import re
import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version


ROOT = Path(__file__).resolve().parents[2]


def _direct_requirements(path: Path) -> list[Requirement]:
    requirements: list[Requirement] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("-r "):
            continue
        requirements.append(Requirement(line))
    return requirements


def _pins() -> dict[str, Version]:
    pins: dict[str, Version] = {}
    for raw_line in (ROOT / "constraints-py312.txt").read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        assert re.fullmatch(r"[A-Za-z0-9_.-]+==[^;\s]+(?:\s*;\s*.+)?", line), line
        requirement = Requirement(line)
        exact = next(spec.version for spec in requirement.specifier if spec.operator == "==")
        pins[canonicalize_name(requirement.name)] = Version(exact)
    return pins


def test_every_direct_group_is_covered_by_compatible_pin() -> None:
    pins = _pins()
    assert "pip" in pins
    assert "setuptools" in pins
    for filename in (
        "requirements.txt",
        "requirements-transcription.txt",
        "requirements-dev.txt",
        "requirements-browser.txt",
        "requirements-docs.txt",
    ):
        for requirement in _direct_requirements(ROOT / filename):
            name = canonicalize_name(requirement.name)
            assert name in pins, f"{filename}: missing pin for {requirement.name}"
            assert pins[name] in requirement.specifier, (
                f"{filename}: {pins[name]} violates {requirement.specifier}"
            )


def test_pyproject_groups_match_requirement_inputs() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    runtime = {
        canonicalize_name(req.name) for req in _direct_requirements(ROOT / "requirements.txt")
    }
    transcription = {
        canonicalize_name(req.name)
        for req in _direct_requirements(ROOT / "requirements-transcription.txt")
    }
    diarization = {
        canonicalize_name(req.name)
        for req in _direct_requirements(ROOT / "requirements-diarization.txt")
    }
    live = {
        canonicalize_name(req.name) for req in _direct_requirements(ROOT / "requirements-live.txt")
    }
    dev = {
        canonicalize_name(req.name) for req in _direct_requirements(ROOT / "requirements-dev.txt")
    }
    browser = {
        canonicalize_name(req.name)
        for req in _direct_requirements(ROOT / "requirements-browser.txt")
    }
    assert runtime == {
        canonicalize_name(Requirement(value).name) for value in project["dependencies"]
    }
    assert transcription == {
        canonicalize_name(Requirement(value).name)
        for value in project["optional-dependencies"]["transcription"]
    }
    assert diarization == {
        canonicalize_name(Requirement(value).name)
        for value in project["optional-dependencies"]["diarization"]
    }
    assert live == {
        canonicalize_name(Requirement(value).name)
        for value in project["optional-dependencies"]["live"]
    }
    assert dev == {
        canonicalize_name(Requirement(value).name)
        for value in project["optional-dependencies"]["dev"]
    }
    assert browser == {
        canonicalize_name(Requirement(value).name)
        for value in project["optional-dependencies"]["browser"]
    }


def test_heavy_optional_dependencies_stay_outside_base_runtime() -> None:
    runtime = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    transcription = (ROOT / "requirements-transcription.txt").read_text(encoding="utf-8").lower()
    assert "faster-whisper" not in runtime
    assert "torch" not in runtime
    assert "sherpa-onnx" not in runtime
    assert "vosk" not in runtime
    assert "faster-whisper" in transcription


def test_lock_input_includes_dev_browser_and_optional_diarization_graphs() -> None:
    lock_input = (ROOT / "requirements-lock-py312.in").read_text(encoding="utf-8")
    assert "-r requirements-dev.txt" in lock_input
    assert "-r requirements-browser.txt" in lock_input
    assert "-r requirements-diarization.txt" in lock_input
    pins = _pins()
    assert "sherpa-onnx" in pins
    assert "soundfile" in pins
    assert "playwright" in pins


def test_lock_and_audit_are_wired_into_delivery_workflows() -> None:
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    release = (ROOT / ".github" / "workflows" / "release-validation.yml").read_text(
        encoding="utf-8"
    )
    audit = (ROOT / ".github" / "workflows" / "dependency-audit.yml").read_text(encoding="utf-8")
    docs = (ROOT / ".github" / "workflows" / "docs-pages.yml").read_text(encoding="utf-8")
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "-c constraints-py312.txt -r requirements-dev.txt" in ci
    assert "-c constraints-py312.txt -r requirements-browser.txt" in ci
    assert "python -m playwright install --with-deps chromium" in ci
    assert "python scripts/47_dependency_audit.py" in release
    assert "schedule:" in audit
    assert "python scripts/47_dependency_audit.py" in audit
    assert "|| true" not in audit
    assert "requirements-transcription.txt" in dockerfile
    assert "constraints-py312.txt" in dockerfile
    assert "-c constraints-py312.txt -r requirements-docs.txt" in docs
    assert "pip install --upgrade pip" not in ci
    assert "pip install --upgrade pip" not in release
    assert "pip install --upgrade pip" not in audit
    assert "pip install --upgrade pip" not in docs
    assert "pip install --upgrade pip" not in dockerfile


def test_documentation_entrypoint_installs_under_constraints() -> None:
    docs_index = (ROOT / "docs" / "index.md").read_text(encoding="utf-8")
    assert "-c constraints-py312.txt -r requirements-docs.txt" in docs_index
