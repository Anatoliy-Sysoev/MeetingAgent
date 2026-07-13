from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REQUIREMENTS = ROOT / "constraints-py312.txt"
DEFAULT_EXCEPTIONS = ROOT / "security" / "dependency-audit-exceptions.json"
MAX_EXCEPTIONS_BYTES = 64 * 1024
MAX_EXCEPTIONS = 50
MAX_REQUIREMENTS_BYTES = 2 * 1024 * 1024
_ADVISORY_RE = re.compile(
    r"^(?:CVE-\d{4}-\d{4,}|GHSA-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{4}|PYSEC-\d{4}-\d+)$",
    re.IGNORECASE,
)
_ISSUE_RE = re.compile(r"^https://github\.com/Anatoliy-Sysoev/MeetingAgent/issues/\d+$")
_CPU_LOCAL_PIN_RE = re.compile(
    r"^(?P<name>torch|torchaudio)==(?P<version>[^;+\s]+)\+cpu(?P<marker>\s*;\s*.+)?$",
    re.IGNORECASE,
)
_ANY_LOCAL_PIN_RE = re.compile(r"^[A-Za-z0-9_.-]+==[^;\s]+\+[^;\s]+(?:\s*;\s*.+)?$")


class AuditConfigurationError(ValueError):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    try:
        if path.stat().st_size > MAX_EXCEPTIONS_BYTES:
            raise AuditConfigurationError("Dependency audit exceptions file is too large")
        raw = path.read_bytes()
        if len(raw) > MAX_EXCEPTIONS_BYTES:
            raise AuditConfigurationError("Dependency audit exceptions file is too large")
        data = json.loads(raw.decode("utf-8"))
    except AuditConfigurationError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AuditConfigurationError("Dependency audit exceptions file is unreadable") from exc
    if not isinstance(data, dict):
        raise AuditConfigurationError("Dependency audit exceptions root must be an object")
    return data


def load_active_exceptions(
    path: Path,
    *,
    today: date | None = None,
) -> list[str]:
    data = _load_json(path)
    if data.get("schema_version") != 1:
        raise AuditConfigurationError("Unsupported dependency exception schema")
    entries = data.get("exceptions")
    if not isinstance(entries, list) or len(entries) > MAX_EXCEPTIONS:
        raise AuditConfigurationError("Dependency exceptions must be a bounded list")
    current = today or date.today()
    advisory_ids: list[str] = []
    seen: set[str] = set()
    required = {"id", "reason", "expires", "issue"}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or set(entry) != required:
            raise AuditConfigurationError(f"Dependency exception #{index + 1} has invalid fields")
        if any(not isinstance(entry[field], str) for field in required):
            raise AuditConfigurationError(
                f"Dependency exception #{index + 1} fields must be strings"
            )
        advisory_id = entry["id"].strip().upper()
        reason = entry["reason"].strip()
        issue = entry["issue"].strip()
        if not _ADVISORY_RE.fullmatch(advisory_id):
            raise AuditConfigurationError(
                f"Dependency exception #{index + 1} has an invalid advisory id"
            )
        if advisory_id in seen:
            raise AuditConfigurationError(f"Duplicate dependency exception: {advisory_id}")
        if not 20 <= len(reason) <= 500:
            raise AuditConfigurationError(
                f"Dependency exception {advisory_id} needs a bounded justification"
            )
        if not _ISSUE_RE.fullmatch(issue):
            raise AuditConfigurationError(
                f"Dependency exception {advisory_id} must reference a repository issue"
            )
        try:
            expiry = date.fromisoformat(entry["expires"])
        except ValueError as exc:
            raise AuditConfigurationError(
                f"Dependency exception {advisory_id} has an invalid expiry date"
            ) from exc
        if expiry < current:
            raise AuditConfigurationError(
                f"Dependency exception {advisory_id} expired on {expiry.isoformat()}"
            )
        seen.add(advisory_id)
        advisory_ids.append(advisory_id)
    return advisory_ids


def build_audit_command(requirements: Path, advisory_ids: list[str]) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "pip_audit",
        "--strict",
        "--no-deps",
        "--disable-pip",
        "--progress-spinner",
        "off",
        "--requirement",
        str(requirements),
    ]
    for advisory_id in advisory_ids:
        command.extend(["--ignore-vuln", advisory_id])
    return command


def build_audit_environment(
    base_environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    environment = dict(os.environ if base_environment is None else base_environment)
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    return environment


def write_audit_projection(source: Path, target: Path) -> int:
    """Project trusted CPU wheel pins onto their auditable upstream versions."""
    try:
        if source.stat().st_size > MAX_REQUIREMENTS_BYTES:
            raise AuditConfigurationError("Dependency lock file is too large")
        text = source.read_text(encoding="utf-8")
    except AuditConfigurationError:
        raise
    except (OSError, UnicodeError) as exc:
        raise AuditConfigurationError("Dependency lock file is unreadable") from exc
    if len(text.encode("utf-8")) > MAX_REQUIREMENTS_BYTES:
        raise AuditConfigurationError("Dependency lock file is too large")

    normalized = 0
    output: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("--index-url") or line.startswith("--extra-index-url"):
            continue
        match = _CPU_LOCAL_PIN_RE.fullmatch(line)
        if match:
            marker = match.group("marker") or ""
            output.append(
                f"{match.group('name').lower()}=={match.group('version')}{marker}"
            )
            normalized += 1
            continue
        if _ANY_LOCAL_PIN_RE.fullmatch(line):
            raise AuditConfigurationError(
                "Unsupported local-version dependency pin in audit lock"
            )
        output.append(raw_line)
    try:
        target.write_text("\n".join(output) + "\n", encoding="utf-8", newline="\n")
    except OSError as exc:
        raise AuditConfigurationError("Dependency audit projection is unwritable") from exc
    return normalized


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit the reviewed Python 3.12 dependency lock.")
    parser.add_argument("--requirements", type=Path, default=DEFAULT_REQUIREMENTS)
    parser.add_argument("--exceptions", type=Path, default=DEFAULT_EXCEPTIONS)
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Validate the exception policy without network access.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        advisory_ids = load_active_exceptions(args.exceptions)
    except AuditConfigurationError as exc:
        raise SystemExit(str(exc)) from exc
    if not args.requirements.is_file():
        raise SystemExit("Dependency lock file is missing")
    try:
        with tempfile.TemporaryDirectory(prefix="meetingagent-dependency-audit-") as temp_dir:
            projected = Path(temp_dir) / "requirements.txt"
            normalized = write_audit_projection(args.requirements, projected)
            if args.check_config:
                print(
                    "Dependency audit policy valid; "
                    f"active exceptions: {len(advisory_ids)}; "
                    f"normalized CPU pins: {normalized}"
                )
                return 0
            command = build_audit_command(projected, advisory_ids)
            environment = build_audit_environment()
            print(
                "Auditing pinned dependencies; "
                f"reviewed exceptions: {len(advisory_ids)}; "
                f"normalized CPU pins: {normalized}"
            )
            try:
                return subprocess.run(
                    command,
                    cwd=ROOT,
                    env=environment,
                    check=False,
                ).returncode
            except OSError as exc:
                raise SystemExit("pip-audit is not installed in this environment") from exc
    except AuditConfigurationError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    raise SystemExit(main())
