from __future__ import annotations

from pathlib import Path
from typing import Any

from asu_june_bot.core.config import resolve_work_path


import json


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"JSONL file not found: {path}")
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_chunks(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    paths = cfg.get("paths", {})
    chunks_path = resolve_work_path(cfg, paths.get("chunks", "data/chunks.jsonl"))
    return read_jsonl(chunks_path)
