from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rag_common import WORK_ROOT, jsonl_read


DEFAULT_INPUT = WORK_ROOT / "data" / "realistic_100_eval_report.jsonl"
DEFAULT_OUTPUT = WORK_ROOT / "data" / "realistic_100_eval_review.jsonl"
DEFAULT_SUMMARY = WORK_ROOT / "data" / "realistic_100_eval_review_summary.json"

VERDICTS = [
    "ok",
    "missing_source",
    "garbage_source",
    "low_score",
    "hallucination",
    "out_of_scope",
    "bad_refusal",
    "needs_clarification",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def compact_source(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_ref": source.get("source_ref"),
        "source_id": source.get("source_id"),
        "title": source.get("title"),
        "path": source.get("path"),
        "section": source.get("section"),
        "requirement_id": source.get("requirement_id"),
        "source_type": source.get("source_type"),
        "score": source.get("score"),
        "bucket": source.get("bucket"),
        "text_preview": source.get("text_preview"),
    }


def build_review_row(row: dict[str, Any]) -> dict[str, Any]:
    parsed = as_dict(row.get("parsed"))
    sources = [compact_source(src) for src in as_list(parsed.get("sources")) if isinstance(src, dict)]
    answer = str(parsed.get("answer") or "").strip()
    return {
        "review_created_at": utc_now(),
        "source": "realistic_100_eval",
        "eval_id": row.get("id"),
        "scope": row.get("scope"),
        "category": row.get("category"),
        "model": row.get("model"),
        "query": row.get("query"),
        "duration_sec": row.get("duration_sec"),
        "returncode": row.get("returncode"),
        "json_parse_error": row.get("json_parse_error"),
        "status": parsed.get("status") or "parse_error",
        "answer_preview": answer[:1200],
        "sources_count": len(sources),
        "top_sources": sources[:8],
        "review_verdict": None,
        "review_comment": "",
        "allowed_verdicts": VERDICTS,
    }


def summarize(rows: list[dict[str, Any]], review_rows: list[dict[str, Any]]) -> dict[str, Any]:
    scopes = Counter(str(row.get("scope")) for row in rows)
    models = Counter(str(row.get("model")) for row in rows)
    statuses = Counter(str(row.get("status")) for row in review_rows)
    returncodes = Counter(str(row.get("returncode")) for row in rows)
    return {
        "created_at": utc_now(),
        "input_rows": len(rows),
        "review_rows": len(review_rows),
        "scopes": dict(scopes),
        "models": dict(models),
        "statuses": dict(statuses),
        "returncodes": dict(returncodes),
        "parse_errors": sum(1 for row in rows if row.get("json_parse_error")),
        "failures": sum(1 for row in rows if row.get("returncode") != 0),
        "output": str(DEFAULT_OUTPUT),
        "next_step": "Manual review: fill review_verdict and review_comment before candidate generation.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare manual-review JSONL from realistic 100 eval report")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="realistic_100_eval_report.jsonl")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="review JSONL output")
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY), help="summary JSON output")
    parser.add_argument("--require-complete", action="store_true", help="Fail if input has fewer than 100 rows")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    summary_path = Path(args.summary)

    rows = list(jsonl_read(input_path))
    if args.require_complete and len(rows) < 100:
        raise SystemExit(f"Report is incomplete: {len(rows)}/100 rows")
    if not rows:
        raise SystemExit(f"Empty report: {input_path}")

    review_rows = [build_review_row(row) for row in rows]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as fp:
        for row in review_rows:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = summarize(rows, review_rows)
    summary["output"] = str(output_path)
    summary["summary"] = str(summary_path)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Review saved: {output_path}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
