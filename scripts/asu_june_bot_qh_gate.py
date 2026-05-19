from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


WORK_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = WORK_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from asu_june_bot.qh import build_release_gate  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="QH release gate status")
    parser.add_argument("--local-validation-done", action="store_true", help="Mark local regression/smoke as done")
    parser.add_argument("--baseline-compared", action="store_true", help="Mark after-QH baseline comparison as done")
    parser.add_argument("--json", action="store_true", help="Print JSON")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = build_release_gate(
        local_validation_done=args.local_validation_done,
        baseline_compared=args.baseline_compared,
    )
    payload = result.to_dict()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    print(f"QH gate status: {payload['status']}")
    for item in payload["items"]:
        print(f"{item['code']}: {item['status']} — {item['title']}")


if __name__ == "__main__":
    main()
