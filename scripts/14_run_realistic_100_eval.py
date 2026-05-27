from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rag_common import WORK_ROOT, jsonl_read


DEFAULT_DATASET = WORK_ROOT / "docs" / "quality" / "realistic_100_queries.jsonl"
DEFAULT_OUTPUT = WORK_ROOT / "data" / "realistic_100_eval_report.jsonl"
DEFAULT_TOP_K = 5
DEFAULT_MAX_TOKENS = 700
DEFAULT_TIMEOUT_SEC = 999999
DEFAULT_CHAT_SCRIPT = WORK_ROOT / "scripts" / "09_chat_quality.py"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_case(case: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    query = str(case["query"])
    model = str(case["model"])
    chat_script = Path(args.chat_script)
    if not chat_script.is_absolute():
        chat_script = WORK_ROOT / chat_script

    if chat_script.name == "asu_june_bot_chat.py":
        cmd = [
            sys.executable,
            str(chat_script),
            query,
            "--json",
            "--model",
            model,
            "--mode",
            str(args.mode),
            "--top-k",
            str(args.top_k),
            "--max-tokens",
            str(args.max_tokens),
            "--timeout-sec",
            str(args.timeout_sec),
            "--no-log",
        ]
    else:
        cmd = [
            sys.executable,
            str(chat_script),
            query,
            "--json",
            "--model",
            model,
            "--top-k",
            str(args.top_k),
            "--num-predict",
            str(args.max_tokens),
            "--timeout-sec",
            str(args.timeout_sec),
        ]

    started = time.perf_counter()
    started_at = utc_now()

    proc = subprocess.run(
        cmd,
        cwd=str(WORK_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=None,
    )

    finished = time.perf_counter()
    duration_sec = round(finished - started, 3)

    parsed: dict[str, Any] | None = None
    parse_error: str | None = None

    stdout = proc.stdout.strip()

    if stdout:
        try:
            parsed = json.loads(stdout)
        except Exception as exc:  # noqa: BLE001
            parse_error = str(exc)

    return {
        "ts": utc_now(),
        "started_at": started_at,
        "duration_sec": duration_sec,
        "id": case.get("id"),
        "scope": case.get("scope"),
        "category": case.get("category"),
        "model": model,
        "chat_script": str(chat_script),
        "query": query,
        "command": cmd,
        "returncode": proc.returncode,
        "stdout": stdout,
        "stderr": proc.stderr.strip(),
        "json_parse_error": parse_error,
        "parsed": parsed,
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scopes = Counter()
    models = Counter()
    statuses = Counter()
    parse_errors = 0
    failures = 0
    durations: list[float] = []

    for row in rows:
        scopes[str(row.get("scope"))] += 1
        models[str(row.get("model"))] += 1
        durations.append(float(row.get("duration_sec") or 0.0))

        if row.get("returncode") != 0:
            failures += 1

        if row.get("json_parse_error"):
            parse_errors += 1

        parsed = row.get("parsed")
        if isinstance(parsed, dict):
            statuses[str(parsed.get("status") or "unknown")] += 1

    return {
        "total": len(rows),
        "failures": failures,
        "parse_errors": parse_errors,
        "scopes": dict(scopes),
        "models": dict(models),
        "statuses": dict(statuses),
        "avg_duration_sec": round(sum(durations) / max(len(durations), 1), 3),
        "max_duration_sec": round(max(durations or [0.0]), 3),
        "min_duration_sec": round(min(durations or [0.0]), 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Прогон 100 realistic queries через project-only chat runner")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET), help="JSONL dataset")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="JSONL report")
    parser.add_argument("--chat-script", default=str(DEFAULT_CHAT_SCRIPT), help="Chat CLI script: 09_chat_quality.py для quality-run или 09_chat.py для baseline")
    parser.add_argument("--mode", choices=["hybrid", "vector", "bm25"], default="hybrid", help="Retrieval mode for asu_june_bot_chat.py")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--timeout-sec", type=int, default=DEFAULT_TIMEOUT_SEC)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    output_path = Path(args.output)
    chat_script = Path(args.chat_script)
    if not chat_script.is_absolute():
        chat_script = WORK_ROOT / chat_script

    if not chat_script.exists():
        raise SystemExit(f"Chat script not found: {chat_script}")

    rows = list(jsonl_read(dataset_path))
    if not rows:
        raise SystemExit(f"Пустой dataset: {dataset_path}")

    if args.limit:
        rows = rows[: args.limit]

    output_path.parent.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []

    with output_path.open("w", encoding="utf-8", newline="\n") as fp:
        for idx, row in enumerate(rows, start=1):
            print(
                f"[{idx}/{len(rows)}] START {row.get('id')} "
                f"model={row.get('model')} "
                f"chat_script={chat_script.name}",
                flush=True,
            )
            result = run_case(row, args)
            results.append(result)
            fp.write(json.dumps(result, ensure_ascii=False) + "\n")
            print(
                f"[{idx}/{len(rows)}] DONE {row.get('id')} "
                f"model={row.get('model')} "
                f"duration={result['duration_sec']}s "
                f"returncode={result['returncode']}",
                flush=True,
            )

    summary = summarize(results)

    print()
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    print(flush=True)
    print(f"Report сохранён: {output_path}", flush=True)


if __name__ == "__main__":
    main()
