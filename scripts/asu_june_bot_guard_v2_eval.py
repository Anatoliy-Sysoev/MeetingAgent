from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


WORK_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = WORK_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from asu_june_bot.guardrails.models import GuardAction  # noqa: E402
from asu_june_bot.guardrails.project_guard import ProjectGuard  # noqa: E402


DEFAULT_CASES = "tests/asu_june_bot/guard_v2_cases.jsonl"
DEFAULT_REPORT = "data/asu_june_bot/guard_v2_eval_report.json"


@dataclass(slots=True)
class EvalCase:
    case_id: str
    query: str
    expected_status: str
    expected_scope: str | None = None
    expected_reason: str | None = None


@dataclass(slots=True)
class EvalResult:
    case: EvalCase
    actual_status: str
    actual_scope: str | None
    actual_reason: str | None
    passed: bool
    actual: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.case.case_id,
            "query": self.case.query,
            "expected_status": self.case.expected_status,
            "expected_scope": self.case.expected_scope,
            "expected_reason": self.case.expected_reason,
            "actual_status": self.actual_status,
            "actual_scope": self.actual_scope,
            "actual_reason": self.actual_reason,
            "passed": self.passed,
            "actual": self.actual,
        }


def resolve_path(path_value: str) -> Path:
    path = Path(path_value)
    if not path.is_absolute():
        path = WORK_ROOT / path
    return path


def read_cases(path: Path) -> list[EvalCase]:
    cases: list[EvalCase] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            row = json.loads(stripped)
            cases.append(
                EvalCase(
                    case_id=str(row.get("id") or f"case_{line_no}"),
                    query=str(row["query"]),
                    expected_status=str(row["expected_status"]),
                    expected_scope=row.get("expected_scope"),
                    expected_reason=row.get("expected_reason"),
                )
            )
    return cases


def action_to_status(action: GuardAction) -> str:
    if action == GuardAction.ALLOW:
        return "ok"
    if action == GuardAction.CLARIFY:
        return "clarify"
    return "refused"


def evaluate_case(guard: ProjectGuard, case: EvalCase) -> EvalResult:
    decision = guard.evaluate_v2(case.query)
    actual_status = action_to_status(decision.action)
    actual_scope = decision.aggregate.scope.value
    actual_reason = decision.reason

    passed = actual_status == case.expected_status
    if case.expected_scope is not None:
        passed = passed and actual_scope == case.expected_scope
    if case.expected_reason is not None:
        passed = passed and actual_reason == case.expected_reason

    return EvalResult(
        case=case,
        actual_status=actual_status,
        actual_scope=actual_scope,
        actual_reason=actual_reason,
        passed=passed,
        actual=decision.to_dict(),
    )


def build_summary(results: list[EvalResult]) -> dict[str, Any]:
    failed = [item for item in results if not item.passed]
    false_allow = [item for item in failed if item.actual_status == "ok" and item.case.expected_status != "ok"]
    false_refuse = [item for item in failed if item.actual_status == "refused" and item.case.expected_status == "ok"]
    false_clarify = [item for item in failed if item.actual_status == "clarify" and item.case.expected_status != "clarify"]
    return {
        "total": len(results),
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "false_allow": len(false_allow),
        "false_refuse": len(false_refuse),
        "false_clarify": len(false_clarify),
        "failed_ids": [item.case.case_id for item in failed],
        "false_allow_ids": [item.case.case_id for item in false_allow],
        "false_refuse_ids": [item.case.case_id for item in false_refuse],
        "false_clarify_ids": [item.case.case_id for item in false_clarify],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate ProjectGuard v2 on JSONL regression cases without retrieval")
    parser.add_argument("--cases", default=DEFAULT_CASES, help="Path to JSONL cases")
    parser.add_argument("--output", default=DEFAULT_REPORT, help="Path to JSON report")
    parser.add_argument("--fail-on-error", action="store_true", help="Exit 1 when any case fails")
    parser.add_argument("--print-failed", action="store_true", help="Print failed cases to stdout")
    args = parser.parse_args()

    cases_path = resolve_path(args.cases)
    report_path = resolve_path(args.output)
    cases = read_cases(cases_path)
    guard = ProjectGuard()
    results = [evaluate_case(guard, case) for case in cases]
    summary = build_summary(results)
    report = {
        "summary": summary,
        "cases_path": str(cases_path),
        "results": [item.to_dict() for item in results],
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"report_path: {report_path}")

    if args.print_failed and summary["failed"]:
        print("\nFailed cases:")
        for item in results:
            if not item.passed:
                print(
                    f"- {item.case.case_id}: expected=({item.case.expected_status}, {item.case.expected_scope}, {item.case.expected_reason}) "
                    f"actual=({item.actual_status}, {item.actual_scope}, {item.actual_reason})"
                )
                print(f"  query: {item.case.query}")

    if args.fail_on_error and summary["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
