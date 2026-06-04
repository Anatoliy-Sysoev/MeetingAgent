from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
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


DEFAULT_DATASET = "docs/quality/ntk_realistic_500_v3_queries_2026-06-03.jsonl"
DEFAULT_REPORT = "docs/quality/ntk_realistic_500_v3_guard_only_report_2026-06-04.jsonl"
DEFAULT_SUMMARY = "docs/quality/ntk_realistic_500_v3_guard_only_summary_2026-06-04.md"


def resolve_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = WORK_ROOT / path
    return path


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if "query" not in row:
                raise ValueError(f"Missing query at {path}:{line_no}")
            rows.append(row)
    return rows


def action_to_status(action: GuardAction) -> str:
    if action == GuardAction.ALLOW:
        return "ok"
    if action == GuardAction.CLARIFY:
        return "clarify"
    return "refused"


def expected_status(scope: str) -> str:
    if scope == "project":
        return "ok"
    if scope in {"out_of_scope", "harmful_security"}:
        return "refused"
    return "clarify"


def verdict(expected: str, actual: str) -> str:
    if expected == actual:
        return "ok"
    if expected == "ok" and actual == "clarify":
        return "false_clarify_project"
    if expected == "ok" and actual == "refused":
        return "false_refuse_project"
    if expected == "refused" and actual == "ok":
        return "false_allow"
    if expected == "refused" and actual == "clarify":
        return "false_clarify_boundary"
    return "mismatch"


def evaluate_dataset(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    guard = ProjectGuard()
    results: list[dict[str, Any]] = []
    for idx, row in enumerate(rows, start=1):
        query = str(row["query"])
        decision = guard.evaluate_v2(query)
        actual = action_to_status(decision.action)
        expected = expected_status(str(row.get("scope") or ""))
        guard_payload = decision.to_dict()
        aggregate = guard_payload.get("aggregate") or {}
        results.append(
            {
                "row_index": idx,
                "id": row.get("id") or row.get("eval_id") or f"row_{idx}",
                "scope": row.get("scope"),
                "category": row.get("category"),
                "query": query,
                "expected_status": expected,
                "actual_status": actual,
                "verdict": verdict(expected, actual),
                "guard_action": guard_payload.get("action"),
                "guard_reason": guard_payload.get("reason"),
                "aggregate_scope": aggregate.get("scope"),
                "aggregate_confidence": aggregate.get("confidence"),
                "aggregate_labels": aggregate.get("labels"),
                "segments": aggregate.get("segments"),
            }
        )
    return results


def counter_by(results: list[dict[str, Any]], key: str) -> Counter:
    return Counter(str(row.get(key)) for row in results)


def nested_counts(results: list[dict[str, Any]], first_key: str, second_key: str) -> dict[str, dict[str, int]]:
    nested: dict[str, Counter] = defaultdict(Counter)
    for row in results:
        nested[str(row.get(first_key))][str(row.get(second_key))] += 1
    return {key: dict(counter.most_common()) for key, counter in sorted(nested.items())}


def build_summary(results: list[dict[str, Any]], dataset_path: Path, report_path: Path) -> str:
    total = len(results)
    verdict_counts = counter_by(results, "verdict")
    actual_counts = counter_by(results, "actual_status")
    reason_counts = counter_by(results, "guard_reason")
    action_by_scope = nested_counts(results, "scope", "actual_status")
    verdict_by_scope = nested_counts(results, "scope", "verdict")
    verdict_by_category = nested_counts(results, "category", "verdict")

    lines = [
        "# NTK realistic 500 v3 guard-only baseline",
        "",
        "Дата: 2026-06-04",
        "",
        "Назначение: дешёвый baseline только через ProjectGuard.evaluate_v2(), без retrieval, embeddings и LLM.",
        "",
        f"Dataset: `{dataset_path.relative_to(WORK_ROOT)}`",
        f"Report: `{report_path.relative_to(WORK_ROOT)}`",
        "",
        "## Summary",
        "",
        f"- total: {total}",
    ]
    for key in ("ok", "false_clarify_project", "false_refuse_project", "false_clarify_boundary", "false_allow", "mismatch"):
        if verdict_counts.get(key):
            lines.append(f"- {key}: {verdict_counts[key]}")

    lines.extend(["", "## Actual Status Counts", ""])
    for key, count in actual_counts.most_common():
        lines.append(f"- {key}: {count}")

    lines.extend(["", "## Action By Scope", ""])
    for scope, counts in action_by_scope.items():
        lines.append(f"- {scope}: {counts}")

    lines.extend(["", "## Verdict By Scope", ""])
    for scope, counts in verdict_by_scope.items():
        lines.append(f"- {scope}: {counts}")

    lines.extend(["", "## Top Guard Reasons", ""])
    for reason, count in reason_counts.most_common(20):
        lines.append(f"- {reason}: {count}")

    lines.extend(["", "## Verdict By Category", ""])
    for category, counts in verdict_by_category.items():
        lines.append(f"- {category}: {counts}")

    lines.extend(["", "## Failed Examples", ""])
    failed = [row for row in results if row["verdict"] != "ok"]
    for row in failed[:40]:
        lines.append(
            f"- `{row['id']}` {row['verdict']} | scope={row.get('scope')} | "
            f"category={row.get('category')} | actual={row['actual_status']} | reason={row.get('guard_reason')}"
        )
        lines.append(f"  Query: {row['query']}")

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ProjectGuard on a realistic JSONL dataset without retrieval/LLM")
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--report", default=DEFAULT_REPORT)
    parser.add_argument("--summary", default=DEFAULT_SUMMARY)
    args = parser.parse_args()

    dataset_path = resolve_path(args.dataset)
    report_path = resolve_path(args.report)
    summary_path = resolve_path(args.summary)

    rows = read_jsonl(dataset_path)
    results = evaluate_dataset(rows)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8", newline="\n") as w:
        for row in results:
            w.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")

    summary_text = build_summary(results, dataset_path, report_path)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(summary_text, encoding="utf-8")

    verdict_counts = counter_by(results, "verdict")
    actual_counts = counter_by(results, "actual_status")
    print(json.dumps({"total": len(results), "verdict": verdict_counts, "actual_status": actual_counts}, ensure_ascii=False, indent=2))
    print(f"report_path: {report_path}")
    print(f"summary_path: {summary_path}")


if __name__ == "__main__":
    main()
