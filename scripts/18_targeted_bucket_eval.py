from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from rag_bucket_quality import classify_failure_bucket


def load_rows(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Run targeted eval rerun by retrieval failure bucket")
    parser.add_argument("--review", required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--chat-script", default="scripts/09_chat_quality.py")
    parser.add_argument("--model", default="qwen2.5:7b-instruct")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    review_rows = load_rows(Path(args.review))

    selected = []
    for row in review_rows:
        bucket = classify_failure_bucket(row)
        if bucket == args.bucket:
            selected.append(row)

    selected = selected[: args.limit]

    print(json.dumps({
        "bucket": args.bucket,
        "selected": len(selected),
        "model": args.model,
        "chat_script": args.chat_script,
    }, ensure_ascii=False, indent=2))

    for idx, row in enumerate(selected, start=1):
        query = row.get("query") or row.get("question")
        print(f"[{idx}/{len(selected)}] {query}")
        subprocess.run(
            [
                sys.executable,
                args.chat_script,
                "--question",
                str(query),
                "--model",
                args.model,
                "--json",
            ],
            check=False,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
