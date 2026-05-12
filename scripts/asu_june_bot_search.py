from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


WORK_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = WORK_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from asu_june_bot.core.config import load_config  # noqa: E402
from asu_june_bot.retrieval.chunks import load_chunks  # noqa: E402
from asu_june_bot.retrieval.hybrid import build_hybrid_retriever  # noqa: E402


def print_human(payload: dict) -> None:
    print(f"Запрос: {payload['query']}")
    print(f"Режим: {payload['mode']}")
    print(f"Результатов: {len(payload['results'])}")
    print()
    for item in payload["results"]:
        print(
            f"[{item['source_id']}] score={item['score']} "
            f"vector={item['vector_score']} bm25={item['bm25_score']} matched_by={','.join(item['matched_by'])}"
        )
        print(f"Документ: {item.get('document')}")
        print(f"Тип: {item.get('document_type')} | Source type: {item.get('source_type')} | Модуль: {item.get('module')}")
        print(f"Раздел: {item.get('section')} | Chunk: {item.get('chunk_index')}")
        print(f"Фрагмент: {item.get('text_preview')}")
        print("-" * 100)


def main() -> None:
    parser = argparse.ArgumentParser(description="Asu June Bot search CLI: hybrid retrieval over MeetingAgent RAG corpus")
    parser.add_argument("query", nargs="+", help="Поисковый запрос")
    parser.add_argument("--top-k", type=int, default=10, help="Количество результатов")
    parser.add_argument("--mode", choices=["hybrid", "vector", "bm25"], default="hybrid", help="Режим поиска")
    parser.add_argument(
        "--include-source-type",
        action="append",
        dest="include_source_types",
        help="Явно разрешить source_type. Можно указать несколько раз",
    )
    parser.add_argument("--json", action="store_true", help="Вывод JSON")
    args = parser.parse_args()

    query = " ".join(args.query).strip()
    if not query:
        raise SystemExit("Пустой запрос")

    cfg = load_config()
    rows = load_chunks(cfg)
    retriever = build_hybrid_retriever(cfg, rows, mode=args.mode)
    results = retriever.search(
        query=query,
        top_k=args.top_k,
        include_source_types=args.include_source_types,
        mode=args.mode,
    )

    payload = {
        "query": query,
        "mode": args.mode,
        "top_k": args.top_k,
        "results": [result.to_dict() for result in results],
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_human(payload)


if __name__ == "__main__":
    main()
