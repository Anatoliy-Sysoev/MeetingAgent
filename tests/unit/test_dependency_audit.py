from __future__ import annotations

import importlib.util
import json
from datetime import date
from pathlib import Path

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
