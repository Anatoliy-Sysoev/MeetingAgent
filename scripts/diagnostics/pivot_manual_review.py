from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(path)
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as f:
        for line_no, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc
    return rows


def key(row: dict[str, Any], field: str) -> str:
    value = row.get(field)
    if value is None or value == "":
        return "unknown"
    return str(value)


def counter_dict(counter: Counter[str]) -> dict[str, int]:
    return dict(sorted(counter.items(), key=lambda item: (-item[1], item[0])))


def build_pivot(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_model = Counter(key(row, "model") for row in rows)
    by_category = Counter(key(row, "category") for row in rows)
    by_status = Counter(key(row, "status") for row in rows)
    by_verdict = Counter(key(row, "review_verdict") for row in rows)
    status_by_model: dict[str, Counter[str]] = defaultdict(Counter)
    verdict_by_model: dict[str, Counter[str]] = defaultdict(Counter)
    status_by_category: dict[str, Counter[str]] = defaultdict(Counter)
    verdict_by_category: dict[str, Counter[str]] = defaultdict(Counter)

    for row in rows:
        model = key(row, "model")
        category = key(row, "category")
        status = key(row, "status")
        verdict = key(row, "review_verdict")
        status_by_model[model][status] += 1
        verdict_by_model[model][verdict] += 1
        status_by_category[category][status] += 1
        verdict_by_category[category][verdict] += 1

    return {
        "rows": len(rows),
        "by_model": counter_dict(by_model),
        "by_category": counter_dict(by_category),
        "by_status": counter_dict(by_status),
        "by_review_verdict": counter_dict(by_verdict),
        "status_by_model": {k: counter_dict(v) for k, v in sorted(status_by_model.items())},
        "review_verdict_by_model": {k: counter_dict(v) for k, v in sorted(verdict_by_model.items())},
        "status_by_category": {k: counter_dict(v) for k, v in sorted(status_by_category.items())},
        "review_verdict_by_category": {k: counter_dict(v) for k, v in sorted(verdict_by_category.items())},
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["model", "category", "status", "review_verdict", "count"]
    grouped = Counter((key(row, "model"), key(row, "category"), key(row, "status"), key(row, "review_verdict")) for row in rows)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for (model, category, status, verdict), count in sorted(grouped.items()):
            writer.writerow(
                {
                    "model": model,
                    "category": category,
                    "status": status,
                    "review_verdict": verdict,
                    "count": count,
                }
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build status/verdict pivots from manual review JSONL")
    parser.add_argument("--review", required=True, type=Path)
    parser.add_argument("--out-json", type=Path)
    parser.add_argument("--out-csv", type=Path)
    args = parser.parse_args()

    rows = read_jsonl(args.review)
    pivot = build_pivot(rows)
    if args.out_json:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(json.dumps(pivot, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.out_csv:
        write_csv(args.out_csv, rows)
    print(json.dumps(pivot, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
