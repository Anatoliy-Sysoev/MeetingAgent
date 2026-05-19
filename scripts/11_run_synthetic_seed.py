from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rag_common import WORK_ROOT, jsonl_read


DEFAULT_SEED_PATH = WORK_ROOT / "docs" / "quality" / "synthetic_seed_queries.jsonl"
DEFAULT_REPORT_PATH = WORK_ROOT / "data" / "synthetic_seed_report.jsonl"


def run_query(question: str, top_k: int, compact: bool, timeout_sec: int) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(WORK_ROOT / "scripts" / "04_query.py"),
        question,
        "--top-k",
        str(top_k),
    ]
    if compact:
        cmd.append("--compact")

    started = datetime.now(timezone.utc).isoformat()
    proc = subprocess.run(
        cmd,
        cwd=str(WORK_ROOT),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout_sec,
    )
    finished = datetime.now(timezone.utc).isoformat()

    return {
        "started_at": started,
        "finished_at": finished,
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Прогон synthetic seed вопросов через scripts/04_query.py"
    )
    parser.add_argument("--seed", default=str(DEFAULT_SEED_PATH), help="JSONL seed-файл")
    parser.add_argument("--output", default=str(DEFAULT_REPORT_PATH), help="JSONL отчёт")
    parser.add_argument("--limit", type=int, default=20, help="Сколько seed-запросов прогнать")
    parser.add_argument("--top-k", type=int, default=8, help="top-k для 04_query.py")
    parser.add_argument("--timeout-sec", type=int, default=180, help="timeout на один запрос")
    parser.add_argument(
        "--full-llm",
        action="store_true",
        help="Запускать полный LLM-ответ. По умолчанию используется --compact для дешёвой проверки retrieval.",
    )
    args = parser.parse_args()

    seed_path = Path(args.seed)
    output_path = Path(args.output)

    rows = list(jsonl_read(seed_path))
    if not rows:
        raise SystemExit(f"Seed-файл пустой или не найден: {seed_path}")

    selected = rows[: args.limit]
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ok = 0
    failed = 0

    with output_path.open("w", encoding="utf-8", newline="\n") as fp:
        for row in selected:
            query = str(row.get("query", "")).strip()
            if not query:
                continue
            result = run_query(
                question=query,
                top_k=args.top_k,
                compact=not args.full_llm,
                timeout_sec=args.timeout_sec,
            )
            status = "ok" if result["returncode"] == 0 else "failed"
            if status == "ok":
                ok += 1
            else:
                failed += 1
            report_row = {
                "seed_id": row.get("id"),
                "category": row.get("category"),
                "query": query,
                "expected_status": row.get("expected_status"),
                "review_priority": row.get("review_priority"),
                "runner_status": status,
                "result": result,
            }
            fp.write(json.dumps(report_row, ensure_ascii=False) + "\n")
            print(f"{row.get('id')}: {status} — {query}", flush=True)

    print("---")
    print(f"Отчёт: {output_path}")
    print(f"Всего: {len(selected)}")
    print(f"ok: {ok}")
    print(f"failed: {failed}")


if __name__ == "__main__":
    main()
