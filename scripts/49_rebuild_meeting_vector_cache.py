"""Validate and atomically compact the local meeting embedding cache."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from meeting_agent.meetings.vector_cache import rebuild_meeting_embedding_cache
from meeting_agent.meetings.vector_index import DEFAULT_MEETING_EMBEDDINGS_CACHE


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Remove malformed, invalid and duplicate meeting embedding cache rows.",
    )
    parser.add_argument(
        "--cache-path",
        type=Path,
        default=Path(DEFAULT_MEETING_EMBEDDINGS_CACHE),
        help="Meeting embedding JSONL cache path.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report recoverable rows without changing the cache.",
    )
    parser.add_argument(
        "--lock-timeout-seconds",
        type=float,
        default=300.0,
        help="Maximum wait for another local cache writer.",
    )
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> dict[str, object]:
    report = rebuild_meeting_embedding_cache(
        args.cache_path.expanduser().resolve(),
        dry_run=bool(args.dry_run),
        lock_timeout_seconds=float(args.lock_timeout_seconds),
    )
    return report.to_dict()


def main(argv: list[str] | None = None) -> int:
    payload = run(parse_args(argv))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
