from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


ARTIFACT_FILES = {
    "summary": "summary.md",
    "protocol": "protocol.md",
    "decisions": "decisions.json",
    "tasks": "tasks.json",
    "risks": "risks.json",
    "open_questions": "open_questions.json",
}

STRUCTURED_KEYS = ("decisions", "tasks", "risks", "open_questions")


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    title: str
    transcript: list[dict[str, Any]]
    expectations: dict[str, Any]
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], *, line_number: int) -> "BenchmarkCase":
        case_id = str(data.get("case_id") or "").strip()
        title = str(data.get("title") or "").strip()
        transcript = data.get("transcript")
        expectations = data.get("expectations")
        if not case_id:
            raise ValueError(f"case line {line_number}: case_id is required")
        if not title:
            raise ValueError(f"case line {line_number}: title is required")
        if not isinstance(transcript, list) or not transcript:
            raise ValueError(f"case line {line_number}: transcript must be a non-empty list")
        if not isinstance(expectations, dict):
            raise ValueError(f"case line {line_number}: expectations must be an object")
        tags = [str(item) for item in data.get("tags", []) if str(item).strip()]
        return cls(case_id=case_id, title=title, transcript=list(transcript), expectations=dict(expectations), tags=tags)


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    title: str
    provider: str
    model: str | None
    checks: list[CheckResult]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def score(self) -> float:
        if not self.checks:
            return 0.0
        return round(sum(1 for check in self.checks if check.passed) / len(self.checks), 3)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "title": self.title,
            "provider": self.provider,
            "model": self.model,
            "passed": self.passed,
            "score": self.score,
            "checks": [check.to_dict() for check in self.checks],
        }


@dataclass(frozen=True)
class BenchmarkReport:
    provider: str
    model: str | None
    generated_at: str
    results: list[CaseResult]

    @property
    def score(self) -> float:
        if not self.results:
            return 0.0
        return round(sum(result.score for result in self.results) / len(self.results), 3)

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "generated_at": self.generated_at,
            "passed": self.passed,
            "score": self.score,
            "summary": {
                "cases": len(self.results),
                "passed": sum(1 for result in self.results if result.passed),
                "failed": sum(1 for result in self.results if not result.passed),
            },
            "results": [result.to_dict() for result in self.results],
        }


def load_benchmark_cases(path: Path) -> list[BenchmarkCase]:
    cases: list[BenchmarkCase] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_number, line in enumerate(fh, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                data = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc
            if not isinstance(data, dict):
                raise ValueError(f"case line {line_number}: row must be an object")
            cases.append(BenchmarkCase.from_dict(data, line_number=line_number))
    if not cases:
        raise ValueError(f"No benchmark cases loaded from {path}")
    return cases


def _read_text(path: Path) -> str:
    if not path.exists() or path.is_dir():
        return ""
    return path.read_text(encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists() or path.is_dir():
        return {"items": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Artifact must be a JSON object: {path}")
    if not isinstance(data.get("items"), list):
        raise ValueError(f"Artifact items must be a list: {path}")
    return data


def _case_artifacts_dir(candidate_dir: Path, case: BenchmarkCase) -> Path:
    nested = candidate_dir / case.case_id / "artifacts"
    if nested.exists():
        return nested
    direct = candidate_dir / case.case_id
    if direct.exists():
        return direct
    return candidate_dir


def _load_artifacts(candidate_dir: Path, case: BenchmarkCase) -> dict[str, Any]:
    artifacts_dir = _case_artifacts_dir(candidate_dir, case)
    return {
        "summary": _read_text(artifacts_dir / ARTIFACT_FILES["summary"]),
        "protocol": _read_text(artifacts_dir / ARTIFACT_FILES["protocol"]),
        "decisions": _read_json(artifacts_dir / ARTIFACT_FILES["decisions"]),
        "tasks": _read_json(artifacts_dir / ARTIFACT_FILES["tasks"]),
        "risks": _read_json(artifacts_dir / ARTIFACT_FILES["risks"]),
        "open_questions": _read_json(artifacts_dir / ARTIFACT_FILES["open_questions"]),
    }


def _contains_all(text: str, terms: Iterable[str]) -> tuple[bool, list[str]]:
    lower = text.lower()
    missing = [term for term in terms if term.lower() not in lower]
    return not missing, missing


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _items(artifacts: Mapping[str, Any], key: str) -> list[dict[str, Any]]:
    raw = artifacts.get(key, {}).get("items") if isinstance(artifacts.get(key), dict) else []
    return [dict(item) for item in raw if isinstance(item, dict)]


def _has_grounded_source(item: Mapping[str, Any]) -> bool:
    refs = item.get("source_refs")
    if not isinstance(refs, list) or not refs:
        return False
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        has_path = bool(str(ref.get("path") or "").strip())
        has_anchor = bool(ref.get("chunk_id") or ref.get("segment_id") or ref.get("segment_index") is not None)
        has_time = bool(ref.get("timecode_start") or ref.get("start") is not None)
        if has_path and has_anchor and has_time:
            return True
    return False


def _has_review_fields(item: Mapping[str, Any]) -> bool:
    confidence = item.get("confidence")
    return isinstance(item.get("needs_review"), bool) and isinstance(confidence, (int, float)) and 0 <= float(confidence) <= 1


def _check_expected_terms(
    *,
    case: BenchmarkCase,
    artifacts: Mapping[str, Any],
    artifact_key: str,
    expected_key: str,
    checks: list[CheckResult],
) -> None:
    expected = case.expectations.get(expected_key, [])
    if not isinstance(expected, list):
        checks.append(CheckResult(f"{expected_key}_schema", False, "expectation must be a list"))
        return
    text = _json_text(_items(artifacts, artifact_key))
    for index, expectation in enumerate(expected, start=1):
        if not isinstance(expectation, dict):
            checks.append(CheckResult(f"{expected_key}_{index}", False, "expectation must be an object"))
            continue
        terms = [str(term) for term in expectation.get("must_include", []) if str(term).strip()]
        ok, missing = _contains_all(text, terms)
        checks.append(
            CheckResult(
                f"{expected_key}_{index}_coverage",
                ok,
                "ok" if ok else "missing terms: " + ", ".join(missing),
            )
        )


def evaluate_case(case: BenchmarkCase, artifacts: Mapping[str, Any], *, provider: str, model: str | None) -> CaseResult:
    checks: list[CheckResult] = []
    summary_text = str(artifacts.get("summary") or "") + "\n" + str(artifacts.get("protocol") or "")
    summary_terms = [str(term) for term in case.expectations.get("summary_must_include", []) if str(term).strip()]
    ok, missing = _contains_all(summary_text, summary_terms)
    checks.append(CheckResult("summary_coverage", ok, "ok" if ok else "missing terms: " + ", ".join(missing)))

    minimum_counts = case.expectations.get("minimum_counts", {})
    if isinstance(minimum_counts, dict):
        for key in STRUCTURED_KEYS:
            expected_count = int(minimum_counts.get(key, 0) or 0)
            actual_count = len(_items(artifacts, key))
            checks.append(
                CheckResult(
                    f"{key}_minimum_count",
                    actual_count >= expected_count,
                    f"actual={actual_count}, expected>={expected_count}",
                )
            )

    _check_expected_terms(case=case, artifacts=artifacts, artifact_key="decisions", expected_key="expected_decisions", checks=checks)
    _check_expected_terms(case=case, artifacts=artifacts, artifact_key="tasks", expected_key="expected_tasks", checks=checks)
    _check_expected_terms(case=case, artifacts=artifacts, artifact_key="risks", expected_key="expected_risks", checks=checks)
    _check_expected_terms(case=case, artifacts=artifacts, artifact_key="open_questions", expected_key="expected_open_questions", checks=checks)

    structured_items = [item for key in STRUCTURED_KEYS for item in _items(artifacts, key)]
    if structured_items:
        grounded = sum(1 for item in structured_items if _has_grounded_source(item))
        review_ready = sum(1 for item in structured_items if _has_review_fields(item))
        checks.append(
            CheckResult(
                "structured_source_refs",
                grounded == len(structured_items),
                f"grounded={grounded}/{len(structured_items)}",
            )
        )
        checks.append(
            CheckResult(
                "structured_confidence_review_fields",
                review_ready == len(structured_items),
                f"with_fields={review_ready}/{len(structured_items)}",
            )
        )
    else:
        checks.append(CheckResult("structured_source_refs", False, "no structured items"))
        checks.append(CheckResult("structured_confidence_review_fields", False, "no structured items"))

    return CaseResult(case_id=case.case_id, title=case.title, provider=provider, model=model, checks=checks)


def evaluate_candidate_dir(
    *,
    cases: list[BenchmarkCase],
    candidate_dir: Path,
    provider: str,
    model: str | None = None,
) -> BenchmarkReport:
    results = [
        evaluate_case(case, _load_artifacts(candidate_dir, case), provider=provider, model=model)
        for case in cases
    ]
    return BenchmarkReport(
        provider=provider,
        model=model,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        results=results,
    )


def render_markdown(report: BenchmarkReport) -> str:
    lines = [
        "# Meeting Summary Benchmark Report",
        "",
        f"- provider: `{report.provider}`",
        f"- model: `{report.model or ''}`",
        f"- generated_at: `{report.generated_at}`",
        f"- cases: **{len(report.results)}**",
        f"- passed: **{sum(1 for result in report.results if result.passed)}**",
        f"- score: **{report.score:.3f}**",
        "",
        "## Cases",
        "",
    ]
    for result in report.results:
        status = "PASS" if result.passed else "FAIL"
        lines.append(f"### {result.case_id} — {status} ({result.score:.3f})")
        lines.append("")
        for check in result.checks:
            mark = "ok" if check.passed else "fail"
            lines.append(f"- {mark}: `{check.name}` — {check.detail}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_report(report: BenchmarkReport, out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "meeting_summary_benchmark_report.json"
    md_path = out_dir / "meeting_summary_benchmark_report.md"
    json_path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return {"json": json_path, "markdown": md_path}
