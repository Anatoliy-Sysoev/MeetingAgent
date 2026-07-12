from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TEST_TARGETS = (
    "tests/asu_june_bot/retrieval",
    "tests/asu_june_bot/search",
)


@dataclass(frozen=True, slots=True)
class CoverageGroup:
    minimum: float
    modules: dict[str, float]


GROUPS = {
    "ranking_core": CoverageGroup(
        minimum=90.0,
        modules={
            "src/asu_june_bot/retrieval/bm25.py": 85.0,
            "src/asu_june_bot/retrieval/hybrid.py": 85.0,
            "src/asu_june_bot/retrieval/post_rerank.py": 95.0,
            "src/asu_june_bot/retrieval/ranking_policies.py": 90.0,
            "src/asu_june_bot/retrieval/ranking_profile.py": 95.0,
            "src/asu_june_bot/retrieval/ranking_signals.py": 95.0,
        },
    ),
    "source_routing": CoverageGroup(
        minimum=75.0,
        modules={
            "src/asu_june_bot/retrieval/context_builder.py": 60.0,
            "src/asu_june_bot/retrieval/query_intent.py": 95.0,
            "src/asu_june_bot/retrieval/source_policy.py": 85.0,
            "src/asu_june_bot/retrieval/source_quality.py": 90.0,
        },
    ),
}


def _run(command: list[str], *, env: dict[str, str]) -> None:
    print("+", " ".join(command))
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def _normalized_files(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    files = report.get("files")
    if not isinstance(files, dict):
        raise ValueError("coverage report does not contain files")
    return {str(path).replace("\\", "/"): value for path, value in files.items()}


def _group_percent(files: dict[str, dict[str, Any]], group: CoverageGroup) -> float:
    covered = 0
    total = 0
    for path in group.modules:
        summary = files[path]["summary"]
        covered += int(summary["covered_lines"]) + int(summary["covered_branches"])
        total += int(summary["num_statements"]) + int(summary["num_branches"])
    return 100.0 * covered / max(total, 1)


def validate_report(report: dict[str, Any]) -> list[str]:
    files = _normalized_files(report)
    failures: list[str] = []
    for group_name, group in GROUPS.items():
        missing = sorted(set(group.modules) - set(files))
        if missing:
            failures.append(f"{group_name}: missing modules: {', '.join(missing)}")
            continue
        for path, minimum in group.modules.items():
            actual = float(files[path]["summary"]["percent_covered"])
            print(f"coverage {path}: {actual:.2f}% (minimum {minimum:.2f}%)")
            if actual + 1e-9 < minimum:
                failures.append(f"{path}: {actual:.2f}% < {minimum:.2f}%")
        group_actual = _group_percent(files, group)
        print(f"coverage group {group_name}: {group_actual:.2f}% (minimum {group.minimum:.2f}%)")
        if group_actual + 1e-9 < group.minimum:
            failures.append(f"group {group_name}: {group_actual:.2f}% < {group.minimum:.2f}%")
    return failures


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="meetingagent_retrieval_coverage_") as temp_dir:
        temp = Path(temp_dir)
        coverage_file = temp / ".coverage"
        report_path = temp / "coverage.json"
        env = dict(os.environ)
        env["COVERAGE_FILE"] = str(coverage_file)
        env["PYTHONPATH"] = os.pathsep.join(
            [str(ROOT / "src"), str(ROOT / "scripts"), env.get("PYTHONPATH", "")]
        ).rstrip(os.pathsep)
        _run(
            [
                sys.executable,
                "-m",
                "coverage",
                "run",
                "--branch",
                "--source=src/asu_june_bot/retrieval",
                "-m",
                "pytest",
                *TEST_TARGETS,
                "-q",
            ],
            env=env,
        )
        _run(
            [sys.executable, "-m", "coverage", "json", "-o", str(report_path)],
            env=env,
        )
        report = json.loads(report_path.read_text(encoding="utf-8"))
        failures = validate_report(report)
        if failures:
            for failure in failures:
                print(f"coverage failure: {failure}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
