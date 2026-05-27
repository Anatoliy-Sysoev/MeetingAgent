from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


DEFAULT_CORPUS_KEY = "default"
ACTIVE_CORPUS_ENV = "ASU_JUNE_BOT_ACTIVE_CORPUS"


@dataclass(slots=True)
class CorpusConfig:
    key: str
    name: str
    chunks_path: str
    cache_path: str
    index_dir: str
    report_path: str


def _corpus_section(cfg: dict[str, Any]) -> dict[str, Any]:
    asu_cfg = cfg.get("asu_june_bot") if isinstance(cfg.get("asu_june_bot"), dict) else {}
    section = asu_cfg.get("corpus") if isinstance(asu_cfg.get("corpus"), dict) else {}
    return section


def get_active_corpus_key(cfg: dict[str, Any]) -> str:
    env_value = os.getenv(ACTIVE_CORPUS_ENV, "").strip()
    if env_value:
        return env_value
    section = _corpus_section(cfg)
    active = str(section.get("active") or DEFAULT_CORPUS_KEY).strip()
    return active or DEFAULT_CORPUS_KEY


def get_corpus_config(cfg: dict[str, Any], key: str | None = None) -> CorpusConfig:
    section = _corpus_section(cfg)
    registry = section.get("corpora") if isinstance(section.get("corpora"), dict) else {}
    effective_key = key or get_active_corpus_key(cfg)
    raw = registry.get(effective_key) if isinstance(registry.get(effective_key), dict) else None
    if raw is None:
        effective_key = DEFAULT_CORPUS_KEY
        raw = registry.get(DEFAULT_CORPUS_KEY) if isinstance(registry.get(DEFAULT_CORPUS_KEY), dict) else None
    if raw is None:
        raw = {
            "key": DEFAULT_CORPUS_KEY,
            "name": "asu_june_bot_v2",
            "chunks_path": "data/asu_june_bot/chunks_v2.jsonl",
            "cache_path": "data/asu_june_bot/embeddings_cache_v2.jsonl",
            "index_dir": "data/asu_june_bot/numpy_index_v2",
            "report_path": "data/asu_june_bot/index_v2_report.json",
        }
    return CorpusConfig(
        key=str(raw.get("key") or effective_key),
        name=str(raw.get("name") or effective_key),
        chunks_path=str(raw.get("chunks_path") or "data/asu_june_bot/chunks_v2.jsonl"),
        cache_path=str(raw.get("cache_path") or "data/asu_june_bot/embeddings_cache_v2.jsonl"),
        index_dir=str(raw.get("index_dir") or "data/asu_june_bot/numpy_index_v2"),
        report_path=str(raw.get("report_path") or "data/asu_june_bot/index_v2_report.json"),
    )
