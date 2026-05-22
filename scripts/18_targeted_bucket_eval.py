from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rag_bucket_quality import classify_failure_bucket


DEFAULT_OUTPUT_DIR = Path("data/targeted_bucket_eval")


def load_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL in {path} at line {line_no}: {exc}") from exc
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def json_loads_from_stdout(stdout: str) -> dict[str, Any] | None:
    text = stdout.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Some local scripts may print progress before JSON. Try to parse the last JSON object.
    start = text.rfind("\n{")
    if start >= 0:
        candidate = text[start + 1 :].strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            return None
    return None


def select_rows(review_rows: list[dict[str, Any]], bucket_code: str, limit: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for row in review_rows:
        bucket = classify_failure_bucket(row)
        if bucket == bucket_code:
            selected.append({**row, "failure_bucket": bucket})
    return selected[:limit]


def run_query(chat_script: str, model: str, query: str) -> dict[str, Any]:
    completed = subprocess.run(
        [
            sys.executable,
            chat_script,
            "--question",
            str(query),
            "--model",
            model,
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    parsed = json_loads_from_stdout(completed.stdout)
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "parsed": parsed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run targeted eval rerun by retrieval failure bucket")
    parser.add_argument("--review", required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--chat-script", default="scripts/09_chat_quality.py")
    parser.add_argument("--model", default="qwen2.5:7b-instruct")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--output", default=None, help="JSONL output path. Default: data/targeted_bucket_eval/<bucket>_<timestamp>.jsonl")
    parser.add_argument("--summary", default=None, help="Summary JSON output path. Default: <output>.summary.json")
    args = parser.parse_args()

    started_at = datetime.now(timezone.utc)
    timestamp = started_at.strftime("%Y%m%d_%H%M%S")
    output_path = Path(args.output) if args.output else DEFAULT_OUTPUT_DIR / f"{args.bucket}_{timestamp}.jsonl"
    summary_path = Path(args.summary) if args.summary else output_path.with_suffix(".summary.json")

    review_path = Path(args.review)
    review_rows = load_rows(review_path)
    selected = select_rows(review_rows, args.bucket, args.limit)

    header = {
        "bucket": args.bucket,
        "selected": len(selected),
        "model": args.model,
        "chat_script": args.chat_script,
        "review": str(review_path),
        "output": str(output_path),
        "summary": str(summary_path),
    }
    print(json.dumps(header, ensure_ascii=False, indent=2))

    result_rows: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    returncode_counts: Counter[str] = Counter()
    parse_errors = 0

    for idx, row in enumerate(selected, start=1):
        query = row.get("query") or row.get("question")
        print(f"[{idx}/{len(selected)}] {query}", flush=True)
        run = run_query(args.chat_script, args.model, str(query))
        parsed = run["parsed"]
        if parsed is None:
            parse_errors += 1
        status = str((parsed or {}).get("status") or "parse_error")
        status_counts[status] += 1
        returncode_counts[str(run["returncode"])] += 1

        result_rows.append(
            {
                "idx": idx,
                "bucket": args.bucket,
                "query": query,
                "review_verdict": row.get("review_verdict"),
                "review_comment": row.get("review_comment"),
                "original_status": row.get("status"),
                "returncode": run["returncode"],
                "parse_error": parsed is None,
                "status": status,
                "refusal_reason": (parsed or {}).get("refusal_reason"),
                "confidence": (parsed or {}).get("confidence"),
                "sources_count": len((parsed or {}).get("sources") or []),
                "top_sources": (parsed or {}).get("sources", [])[:5] if parsed else [],
                "diagnostics": (parsed or {}).get("diagnostics") if parsed else None,
                "stderr": run["stderr"].strip(),
                "stdout": run["stdout"].strip() if parsed is None else None,
            }
        )

    write_jsonl(output_path, result_rows)

    finished_at = datetime.now(timezone.utc)
    summary = {
        **header,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_sec": round((finished_at - started_at).total_seconds(), 3),
        "status_counts": dict(status_counts),
        "returncode_counts": dict(returncode_counts),
        "parse_errors": parse_errors,
        "failures": sum(1 for row in result_rows if int(row.get("returncode") or 0) != 0 or row.get("parse_error")),
        "notes": [
            "Targeted runner only reruns selected bucket questions; it does not approve regression rows automatically.",
            "Review rows must be checked manually before moving cases to the approved regression set.",
        ],
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    return 1 if summary["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
