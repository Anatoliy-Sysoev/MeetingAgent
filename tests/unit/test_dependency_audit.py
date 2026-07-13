from __future__ import annotations

import importlib.util
import json
from argparse import Namespace
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "47_dependency_audit.py"
SPEC = importlib.util.spec_from_file_location("dependency_audit", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def _write(path: Path, exceptions: list[dict]) -> None:
    path.write_text(
        json.dumps({"schema_version": 1, "exceptions": exceptions}),
        encoding="utf-8",
    )


def _valid_entry(**overrides) -> dict:
    entry = {
        "id": "GHSA-abcd-2345-6789",
        "reason": "Temporary exception while the upstream fix is validated.",
        "expires": "2026-08-01",
        "issue": "https://github.com/Anatoliy-Sysoev/MeetingAgent/issues/177",
    }
    entry.update(overrides)
    return entry


def test_empty_exception_policy_is_valid(tmp_path: Path) -> None:
    path = tmp_path / "exceptions.json"
    _write(path, [])
    assert audit.load_active_exceptions(path, today=date(2026, 7, 11)) == []


def test_valid_exception_becomes_ignore_flag(tmp_path: Path) -> None:
    path = tmp_path / "exceptions.json"
    _write(path, [_valid_entry()])
    ids = audit.load_active_exceptions(path, today=date(2026, 7, 11))
    command = audit.build_audit_command(Path("constraints.txt"), ids)
    assert ids == ["GHSA-ABCD-2345-6789"]
    assert command[-2:] == ["--ignore-vuln", "GHSA-ABCD-2345-6789"]
    assert "--strict" in command
    assert "--no-deps" in command
    assert "--disable-pip" in command


def test_audit_environment_forces_utf8_under_non_ascii_windows_path() -> None:
    environment = audit.build_audit_environment(
        {
            "VIRTUAL_ENV": r"C:\Users\Пользователь\Проект\.venv",
            "PYTHONUTF8": "0",
            "PYTHONIOENCODING": "cp1251",
            "KEEP_ME": "present",
        }
    )

    assert environment["VIRTUAL_ENV"].endswith(r"Пользователь\Проект\.venv")
    assert environment["PYTHONUTF8"] == "1"
    assert environment["PYTHONIOENCODING"] == "utf-8"
    assert environment["KEEP_ME"] == "present"


def test_audit_projection_normalizes_only_reviewed_cpu_wheels(tmp_path: Path) -> None:
    source = tmp_path / "live-lock.txt"
    source.write_text(
        "--extra-index-url https://download.pytorch.org/whl/cpu\n"
        "torch==2.13.0+cpu\n"
        "torchaudio==2.11.0+cpu ; python_version < \"3.15\"\n"
        "vosk==0.3.45\n",
        encoding="utf-8",
    )
    target = tmp_path / "audit.txt"

    assert audit.write_audit_projection(source, target) == 2
    assert target.read_text(encoding="utf-8") == (
        "torch==2.13.0\n"
        "torchaudio==2.11.0 ; python_version < \"3.15\"\n"
        "vosk==0.3.45\n"
    )


def test_audit_projection_rejects_unreviewed_local_version(tmp_path: Path) -> None:
    source = tmp_path / "lock.txt"
    source.write_text("example==1.0+private\n", encoding="utf-8")

    with pytest.raises(audit.AuditConfigurationError, match="local-version"):
        audit.write_audit_projection(source, tmp_path / "audit.txt")


def test_audit_projection_rejects_oversized_lock(tmp_path: Path) -> None:
    source = tmp_path / "lock.txt"
    source.write_bytes(b"x" * (audit.MAX_REQUIREMENTS_BYTES + 1))

    with pytest.raises(audit.AuditConfigurationError, match="too large"):
        audit.write_audit_projection(source, tmp_path / "audit.txt")


def test_main_passes_utf8_environment_to_audit_process(
    tmp_path: Path, monkeypatch
) -> None:
    requirements = tmp_path / "constraints.txt"
    requirements.write_text("example==1.0\n", encoding="utf-8")
    exceptions = tmp_path / "exceptions.json"
    _write(exceptions, [])
    seen: dict[str, object] = {}

    monkeypatch.setattr(
        audit,
        "parse_args",
        lambda: Namespace(
            requirements=requirements,
            exceptions=exceptions,
            check_config=False,
        ),
    )

    def fake_run(command, *, cwd, env, check):
        requirements_index = command.index("--requirement") + 1
        projection = Path(command[requirements_index])
        seen.update(
            command=command,
            cwd=cwd,
            env=env,
            check=check,
            projection=projection.read_text(encoding="utf-8"),
        )
        return SimpleNamespace(returncode=7)

    monkeypatch.setattr(audit.subprocess, "run", fake_run)
    monkeypatch.setenv("PYTHONUTF8", "0")
    monkeypatch.setenv("PYTHONIOENCODING", "cp1251")

    assert audit.main() == 7
    assert seen["cwd"] == audit.ROOT
    assert seen["check"] is False
    assert seen["env"]["PYTHONUTF8"] == "1"
    assert seen["env"]["PYTHONIOENCODING"] == "utf-8"
    assert seen["projection"] == "example==1.0\n"
    assert audit.os.environ["PYTHONUTF8"] == "0"
    assert audit.os.environ["PYTHONIOENCODING"] == "cp1251"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"id": "not-an-advisory"}, "invalid advisory"),
        ({"reason": "too short"}, "justification"),
        ({"expires": "2026-07-10"}, "expired"),
        ({"expires": "tomorrow"}, "invalid expiry"),
        ({"issue": "https://example.com/1"}, "repository issue"),
    ],
)
def test_invalid_exception_fails_closed(tmp_path: Path, overrides: dict, message: str) -> None:
    path = tmp_path / "exceptions.json"
    _write(path, [_valid_entry(**overrides)])
    with pytest.raises(audit.AuditConfigurationError, match=message):
        audit.load_active_exceptions(path, today=date(2026, 7, 11))


def test_duplicate_advisory_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "exceptions.json"
    _write(path, [_valid_entry(), _valid_entry()])
    with pytest.raises(audit.AuditConfigurationError, match="Duplicate"):
        audit.load_active_exceptions(path, today=date(2026, 7, 11))


def test_unknown_fields_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "exceptions.json"
    _write(path, [_valid_entry(owner="nobody")])
    with pytest.raises(audit.AuditConfigurationError, match="invalid fields"):
        audit.load_active_exceptions(path, today=date(2026, 7, 11))


def test_non_string_fields_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "exceptions.json"
    _write(path, [_valid_entry(reason=12345678901234567890)])
    with pytest.raises(audit.AuditConfigurationError, match="must be strings"):
        audit.load_active_exceptions(path, today=date(2026, 7, 11))


def test_oversized_policy_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "exceptions.json"
    path.write_bytes(b"{" + b"x" * (audit.MAX_EXCEPTIONS_BYTES + 1))
    with pytest.raises(audit.AuditConfigurationError, match="too large"):
        audit.load_active_exceptions(path, today=date(2026, 7, 11))
