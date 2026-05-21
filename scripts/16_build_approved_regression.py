from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rag_common import WORK_ROOT, jsonl_read, stable_id


DEFAULT_INPUT = WORK_ROOT / "data" / "realistic_100_eval_review.jsonl"
DEFAULT_OUTPUT = WORK_ROOT / "eval" / "cases" / "approved_regression_realistic_100.jsonl"


def normalize_sources(value: Any, limit: int = 5) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    sources: list[dict[str, Any]] = []
    for item in value[:limit]:
        if not isinstance(item, dict):
            continue
        sources.append(
            {
                "relative_path": item.get("relative_path"),
                "chunk_index": item.get("chunk_index"),
                "score": item.get("score"),
                "retrieval": item.get("retrieval"),
                "lexical_score": item.get("lexical_score"),
                "matched_terms": item.get("matched_terms"),
                "matched_numbers": item.get("matched_numbers"),
                "phrase_matches": item.get("phrase_matches"),
            }
        )
    return sources


def build_case(row: dict[str, Any], index: int) -> dict[str, Any]:
    query = str(row.get("question") or row.get("query") or "").strip()
    source_id = str(row.get("id") or row.get("case_id") or row.get("request_id") or index)
    case_id = f"APR-{stable_id(query + '|' + source_id, 12).upper()}"
    return {
        "id": case_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": "realistic_100_manual_review",
        "source_id": source_id,
        "query": query,
        "scope": row.get("scope"),
        "category": row.get("category"),
        "expected_status": row.get("status") or "answered",
        "expected_model": row.get("model"),
        "review_verdict": row.get("review_verdict"),
        "review_comment": row.get("review_comment") or "",
        "approved": True,
        "approved_reason": "manual_review_verdict_ok",
        "expected_sources": normalize_sources(row.get("top_sources") or row.get("sources")),
        "notes": "Approved positive regression case. Do not edit automatically; update only after manual review.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build approved regression set from manually reviewed realistic eval JSONL")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Reviewed JSONL with review_verdict/review_comment")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output approved regression JSONL")
    parser.add_argument("--only-scope", default=None, help="Optional scope filter, e.g. project")
    parser.add_argument("--include-no-answer", action="store_true", help="Include ok no_answer cases as approved negative cases")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    rows = list(jsonl_read(input_path))
    if not rows:
        raise SystemExit(f"No rows found: {input_path}")

    cases: list[dict[str, Any]] = []
    skipped = Counter()
    for index, row in enumerate(rows, start=1):
        verdict = str(row.get("review_verdict") or "").strip()
        status = str(row.get("status") or "").strip()
        scope = str(row.get("scope") or "").strip()
        if verdict != "ok":
            skipped["not_ok"] += 1
            continue
        if args.only_scope and scope != args.only_scope:
            skipped["scope"] += 1
            continue
        if status == "no_answer" and not args.include_no_answer:
            skipped["no_answer"] += 1
            continue
        query = str(row.get("question") or row.get("query") or "").strip()
        if not query:
            skipped["empty_query"] += 1
            continue
        cases.append(build_case(row, index))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as fp:
        for case in cases:
            fp.write(json.dumps(case, ensure_ascii=False) + "\n")

    print(
        json.dumps(
            {
                "status": "ok",
                "input": str(input_path),
                "output": str(output_path),
                "input_rows": len(rows),
                "approved_cases": len(cases),
                "skipped": dict(skipped),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
