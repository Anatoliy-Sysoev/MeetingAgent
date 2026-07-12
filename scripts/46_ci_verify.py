from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def build_diff_commands(env: Mapping[str, str]) -> list[list[str]]:
    """Build whitespace checks for GitHub ranges or the local working tree."""
    base = str(env.get("GITHUB_BASE_SHA") or "").strip()
    head = str(env.get("GITHUB_HEAD_SHA") or "").strip()
    if bool(base) != bool(head):
        raise ValueError("GITHUB_BASE_SHA and GITHUB_HEAD_SHA must be set together")
    if base and head:
        if set(base) == {"0"}:
            base = f"{head}^"
        return [["git", "diff", "--check", base, head]]
    return [
        ["git", "diff", "--check"],
        ["git", "diff", "--cached", "--check"],
    ]


def _run(command: list[str]) -> None:
    print(f"+ {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> int:
    try:
        diff_commands = build_diff_commands(os.environ)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    for command in diff_commands:
        _run(command)
    _run([sys.executable, "-m", "compileall", "-q", "scripts", "src", "tests"])
    _run([sys.executable, "-m", "pytest", "-q"])
    _run([sys.executable, "scripts/48_retrieval_coverage.py"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
