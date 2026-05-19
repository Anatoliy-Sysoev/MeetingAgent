from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rag_common import WORK_ROOT, jsonl_read, stable_id


DEFAULT_REVIEW_PATH = WORK_ROOT / "data" / "query_log_review.jsonl"
DEFAULT_OUTPUT_PATH = WORK_ROOT / "data" / "eval_candidates.jsonl"

BAD_VERDICTS = {
    "missing_source",
    "garbage_source",
    "low_score",
    "hallucination",
    "out_of_scope",
}


def normalize_top_sources(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    out: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "relative_path": item.get("relative_path"),
                "chunk_index": item.get("chunk_index"),
                "score": item.get("score"),
            }
        )
    return out


def expected_status_from_verdict(verdict: str) -> str:
    if verdict == "out_of_scope":
        return "refused"
    if verdict == "hallucination":
        return "no_hallucination_required"
    if verdict in {"missing_source", "garbage_source", "low_score"}:
        return "retrieval_fix_required"
    return "manual_review_required"


def build_candidate(row: dict[str, Any], index: int) -> dict[str, Any]:
    question = str(row.get("question") or "").strip()
    verdict = str(row.get("review_verdict") or "").strip()
    base = f"{question}|{verdict}|{row.get('ts') or ''}|{index}"
    candidate_id = f"CAND-{stable_id(base, 12).upper()}"
    return {
        "id": candidate_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": "query_log_review",
        "source_ts": row.get("ts"),
        "source_tool": row.get("source"),
        "query": question,
        "review_verdict": verdict,
        "review_comment": row.get("review_comment") or "",
        "expected_status": expected_status_from_verdict(verdict),
        "expected_sources": [],
        "observed_status": row.get("status"),
        "observed_top_sources": normalize_top_sources(row.get("top_sources")),
        "promotion_status": "candidate",
        "notes": "Manual approval required before moving to accepted eval cases.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Сборка кандидатов eval-кейсов из ручной review-разметки"
    )
    parser.add_argument("--input", default=str(DEFAULT_REVIEW_PATH), help="query_log_review.jsonl")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="eval_candidates.jsonl")
    parser.add_argument(
        "--include-ok",
        action="store_true",
        help="Также включать строки с review_verdict=ok как positive candidates",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    rows = list(jsonl_read(input_path))
    if not rows:
        raise SystemExit(f"Пустой или отсутствующий review-файл: {input_path}")

    candidates: list[dict[str, Any]] = []
    verdict_counter: Counter[str] = Counter()
    skipped_unreviewed = 0
    skipped_ok = 0

    for index, row in enumerate(rows, start=1):
        verdict = str(row.get("review_verdict") or "").strip()
        if not verdict:
            skipped_unreviewed += 1
            continue
        verdict_counter[verdict] += 1
        if verdict == "ok" and not args.include_ok:
            skipped_ok += 1
            continue
        if verdict != "ok" and verdict not in BAD_VERDICTS:
            # Unknown verdicts are preserved as manual-review candidates.
            pass
        candidates.append(build_candidate(row, index))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as fp:
        for candidate in candidates:
            fp.write(json.dumps(candidate, ensure_ascii=False) + "\n")

    print(f"Eval candidates сохранены: {output_path}")
    print(json.dumps(
        {
            "input_rows": len(rows),
            "candidates": len(candidates),
            "skipped_unreviewed": skipped_unreviewed,
            "skipped_ok": skipped_ok,
            "verdict_counter": dict(verdict_counter),
        },
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
