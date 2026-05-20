from __future__ import annotations

import argparse
import json
from pathlib import Path

from rag_common import ensure_runtime_dirs, load_config, resolve_work_path
from rag_fts import FTSIndex


def main() -> None:
    parser = argparse.ArgumentParser(description="Пересборка локального SQLite FTS5/BM25 индекса по chunks.jsonl")
    parser.add_argument("--chunks", default=None, help="Путь к chunks.jsonl. По умолчанию берётся из config.yaml")
    parser.add_argument("--output", default="data/fts_index.sqlite", help="Путь к SQLite FTS5 индексу")
    args = parser.parse_args()

    cfg = load_config()
    ensure_runtime_dirs(cfg)

    chunks_path = Path(args.chunks) if args.chunks else resolve_work_path(cfg, cfg["paths"]["chunks"])
    if not chunks_path.is_absolute():
        chunks_path = resolve_work_path(cfg, str(chunks_path))

    fts_path = Path(args.output)
    if not fts_path.is_absolute():
        fts_path = resolve_work_path(cfg, str(fts_path))

    result = FTSIndex(fts_path).rebuild(chunks_path)
    result["chunks_path"] = str(chunks_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
