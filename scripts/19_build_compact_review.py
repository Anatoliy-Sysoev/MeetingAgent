from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from rag_bucket_quality import classify_failure_bucket


def jsonl_read(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def csv_read(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def compact_row(row: dict[str, Any]) -> dict[str, Any]:
    top_sources = row.get("top_sources") or row.get("sources") or []
    compact_sources = []
    for item in top_sources[:5]:
        if not isinstance(item, dict):
            continue
        compact_sources.append(
            {
                "relative_path": item.get("relative_path"),
                "score": item.get("score"),
                "retrieval": item.get("retrieval"),
                "lexical_score": item.get("lexical_score"),
            }
        )

    compact = {
        "id": row.get("id"),
        "scope": row.get("scope"),
        "category": row.get("category"),
        "model": row.get("model"),
        "query": row.get("query") or row.get("question"),
        "status": row.get("status"),
        "confidence": row.get("confidence"),
        "review_verdict": row.get("review_verdict"),
        "review_comment": row.get("review_comment"),
        "bucket": classify_failure_bucket(row),
        "top_sources": compact_sources,
    }
    return compact


def main() -> None:
    parser = argparse.ArgumentParser(description="Build compact labeled realistic review JSONL")
    parser.add_argument("--review", required=True)
    parser.add_argument("--csv", default=None)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    review_rows = jsonl_read(Path(args.review))
    csv_rows = csv_read(Path(args.csv)) if args.csv else []

    compact_rows = [compact_row(row) for row in review_rows]

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as f:
        for row in compact_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    verdict_counts = Counter(str(row.get("review_verdict") or "missing" ) for row in compact_rows)
    bucket_counts = Counter(str(row.get("bucket") or "unknown") for row in compact_rows)

    print(
        json.dumps(
            {
                "status": "ok",
                "input_rows": len(review_rows),
                "csv_rows": len(csv_rows),
                "output": str(output_path),
                "verdict_counts": dict(verdict_counts),
                "bucket_counts": dict(bucket_counts),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
