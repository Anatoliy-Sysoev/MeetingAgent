#!/usr/bin/env python3
"""Export reviewed chat runs into guard/eval regression cases (guard_v2_cases.jsonl).

Usage:
    python scripts/40_export_guard_v2_cases.py \
        --runs data/asu_june_bot/chat_runs.jsonl \
        --labels data/asu_june_bot/chat_run_labels.jsonl \
        --out data/asu_june_bot/guard_v2_cases.jsonl

Options:
    --runs PATH         Path to chat_runs.jsonl (default: data/asu_june_bot/chat_runs.jsonl)
    --labels PATH       Path to chat_run_labels.jsonl (default: data/asu_june_bot/chat_run_labels.jsonl)
    --out PATH          Output path (default: data/asu_june_bot/guard_v2_cases.jsonl)
    --include-correct   Also export "correct"-labeled runs (default: excluded)
    --limit N           Cap total exported cases
    --label LABEL       Export only this label (repeatable or comma-separated)
    --dry-run           Print summary without writing output file
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from asu_june_bot.evals.guard_cases import GuardCaseExporter  # noqa: E402


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export reviewed chat runs to guard_v2_cases.jsonl"
    )
    parser.add_argument(
        "--runs",
        type=Path,
        default=Path("data/asu_june_bot/chat_runs.jsonl"),
        help="Path to chat_runs.jsonl",
    )
    parser.add_argument(
        "--labels",
        type=Path,
        default=Path("data/asu_june_bot/chat_run_labels.jsonl"),
        help="Path to chat_run_labels.jsonl",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data/asu_june_bot/guard_v2_cases.jsonl"),
        help="Output path for guard_v2_cases.jsonl",
    )
    parser.add_argument(
        "--include-correct",
        action="store_true",
        default=False,
        help="Also export 'correct'-labeled runs (excluded by default)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of cases to export",
    )
    parser.add_argument(
        "--label",
        action="append",
        dest="labels_filter",
        default=None,
        help="Export only this label (repeatable; comma-separated values also accepted)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print summary without writing output file",
    )
    return parser.parse_args(argv)


def _resolve_filter_labels(labels_filter: list[str] | None) -> frozenset[str] | None:
    if not labels_filter:
        return None
    result: set[str] = set()
    for item in labels_filter:
        for part in item.split(","):
            stripped = part.strip()
            if stripped:
                result.add(stripped)
    return frozenset(result) if result else None


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    filter_labels = _resolve_filter_labels(args.labels_filter)

    exporter = GuardCaseExporter(
        runs_path=args.runs,
        labels_path=args.labels,
    )

    if args.dry_run:
        cases = exporter.export_cases(
            include_correct=args.include_correct,
            limit=args.limit,
            filter_labels=filter_labels,
        )
        runs_count = len(exporter._read_jsonl_tail(args.runs))
        labels_count = len(exporter._load_labels())
        summary = {
            "runs_read": runs_count,
            "labels_read": labels_count,
            "cases_would_write": len(cases),
            "output": str(args.out),
            "dry_run": True,
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    summary = exporter.write_cases(
        args.out,
        include_correct=args.include_correct,
        limit=args.limit,
        filter_labels=filter_labels,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
