from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


WORK_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = WORK_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from asu_june_bot.core.config import load_config, resolve_work_path  # noqa: E402
from asu_june_bot.retrieval.chunks import read_jsonl  # noqa: E402
from asu_june_bot.retrieval.hybrid import build_hybrid_retriever  # noqa: E402


DEFAULT_CHUNKS_PATH = "data/asu_june_bot/chunks_v2.jsonl"
DEFAULT_INDEX_DIR = "data/asu_june_bot/numpy_index_v2"


def make_v2_cfg(cfg: dict[str, Any], chunks_path: str, index_dir: str) -> dict[str, Any]:
    patched = dict(cfg)
    paths = dict(patched.get("paths") or {})
    paths["chunks"] = chunks_path
    paths["numpy_index"] = index_dir
    patched["paths"] = paths
    return patched


def get_path(item: dict[str, Any]) -> str | None:
    metadata = item.get("metadata") or {}
    return item.get("relative_path") or item.get("document") or metadata.get("relative_path")


def print_human(payload: dict[str, Any]) -> None:
    print(f"Запрос: {payload['query']}")
    print(f"Корпус: {payload['corpus']}")
    print(f"Режим: {payload['mode']}")
    print(f"Результатов: {len(payload['results'])}")
    print()
    for item in payload["results"]:
        metadata = item.get("metadata") or {}
        requirement_id = item.get("requirement_id") or metadata.get("requirement_id")
        print(
            f"[{item['source_id']}] score={item['score']} "
            f"vector={item['vector_score']} bm25={item['bm25_score']} matched_by={','.join(item['matched_by'])}"
        )
        print(f"Документ: {item.get('document')}")
        print(f"Тип: {item.get('document_type')} | Source type: {item.get('source_type')} | Модуль: {item.get('module')}")
        print(f"Раздел: {item.get('section')} | Requirement: {requirement_id} | Chunk: {item.get('chunk_index')}")
        print(f"Путь: {get_path(item)}")
        print(f"Фрагмент: {item.get('text_preview')}")
        print("-" * 100)


def main() -> None:
    parser = argparse.ArgumentParser(description="Asu June Bot v2 search CLI over chunks_v2 and numpy_index_v2")
    parser.add_argument("query", nargs="+", help="Поисковый запрос")
    parser.add_argument("--top-k", type=int, default=10, help="Количество результатов")
    parser.add_argument("--mode", choices=["hybrid", "vector", "bm25"], default="hybrid", help="Режим поиска")
    parser.add_argument("--chunks-path", default=DEFAULT_CHUNKS_PATH)
    parser.add_argument("--index-dir", default=DEFAULT_INDEX_DIR)
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
    cfg = make_v2_cfg(cfg, args.chunks_path, args.index_dir)
    chunks_path = resolve_work_path(cfg, args.chunks_path)
    index_dir = resolve_work_path(cfg, args.index_dir)

    rows = read_jsonl(chunks_path)
    if args.mode in {"hybrid", "vector"} and not (index_dir / "manifest.json").exists():
        raise SystemExit(
            f"numpy_index_v2 не найден: {index_dir}. "
            "Сначала запусти scripts/asu_june_bot_build_index_v2.py или используй --mode bm25."
        )

    retriever = build_hybrid_retriever(cfg, rows, mode=args.mode)
    results = retriever.search(
        query=query,
        top_k=args.top_k,
        include_source_types=args.include_source_types,
        mode=args.mode,
    )

    payload = {
        "query": query,
        "corpus": "asu_june_bot_v2",
        "mode": args.mode,
        "top_k": args.top_k,
        "chunks_path": str(chunks_path),
        "index_dir": str(index_dir),
        "results": [result.to_dict() for result in results],
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_human(payload)


if __name__ == "__main__":
    main()
