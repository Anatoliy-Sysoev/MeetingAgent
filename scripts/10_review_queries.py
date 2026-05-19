from __future__ import annotations

import argparse
import json
from pathlib import Path

from rag_common import WORK_ROOT, jsonl_read


VERDICTS = [
    "ok",
    "missing_source",
    "garbage_source",
    "low_score",
    "hallucination",
    "out_of_scope",
]


def build_review_row(item: dict) -> dict:
    return {
        "ts": item.get("ts"),
        "source": item.get("source"),
        "question": item.get("question"),
        "status": item.get("status") or item.get("mode"),
        "top_sources": item.get("top_sources", []),
        "review_verdict": None,
        "review_comment": "",
        "allowed_verdicts": VERDICTS,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Подготовка review-среза для ручной разметки query_log.jsonl"
    )
    parser.add_argument(
        "--input",
        default=str(WORK_ROOT / "data" / "query_log.jsonl"),
        help="Путь до query_log.jsonl",
    )
    parser.add_argument(
        "--output",
        default=str(WORK_ROOT / "data" / "query_log_review.jsonl"),
        help="Путь до review-файла",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Количество последних запросов для review",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    rows = list(jsonl_read(input_path))
    if not rows:
        raise SystemExit(f"Пустой лог запросов: {input_path}")

    rows = rows[-args.limit :]

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8", newline="\n") as fp:
        for row in rows:
            fp.write(
                json.dumps(build_review_row(row), ensure_ascii=False) + "\n"
            )

    print(f"Review-срез сохранён: {output_path}")
    print(f"Количество записей: {len(rows)}")
    print("Вердикты:")
    for verdict in VERDICTS:
        print(f"- {verdict}")


if __name__ == "__main__":
    main()
