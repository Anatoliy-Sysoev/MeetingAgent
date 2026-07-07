"""MeetingAgent local/Docker runtime preflight."""
from __future__ import annotations

import argparse
import sys

from asu_june_bot.packaging.preflight import (
    DEFAULT_CHAT_MODEL,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_OLLAMA_URL,
    format_results,
    has_required_failures,
    results_json,
    run_preflight,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check local MeetingAgent runtime prerequisites.")
    parser.add_argument("--mode", choices=["docker", "local"], default="docker")
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    parser.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL)
    parser.add_argument("--chat-model", default=DEFAULT_CHAT_MODEL)
    parser.add_argument("--skip-ollama", action="store_true")
    parser.add_argument("--optional-asr", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    results = run_preflight(
        mode=args.mode,
        ollama_url=args.ollama_url,
        embedding_model=args.embedding_model,
        chat_model=args.chat_model,
        skip_ollama=args.skip_ollama,
        optional_asr=args.optional_asr,
    )
    if args.json_output:
        print(results_json(results))
    else:
        print(format_results(results))
    return 1 if has_required_failures(results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
