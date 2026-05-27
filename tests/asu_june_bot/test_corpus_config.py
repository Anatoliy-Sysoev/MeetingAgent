from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.core.corpus import get_active_corpus_key, get_corpus_config  # noqa: E402


def test_default_corpus_config_is_resolved() -> None:
    cfg = {
        "asu_june_bot": {
            "corpus": {
                "active": "default",
                "corpora": {
                    "default": {
                        "key": "default",
                        "name": "asu_june_bot_v2",
                        "chunks_path": "data/asu_june_bot/chunks_v2.jsonl",
                        "cache_path": "data/asu_june_bot/embeddings_cache_v2.jsonl",
                        "index_dir": "data/asu_june_bot/numpy_index_v2",
                        "report_path": "data/asu_june_bot/index_v2_report.json",
                    }
                },
            }
        }
    }

    corpus = get_corpus_config(cfg)
    assert corpus.key == "default"
    assert corpus.name == "asu_june_bot_v2"
    assert corpus.chunks_path.endswith("data/asu_june_bot/chunks_v2.jsonl")


def test_env_override_switches_active_corpus() -> None:
    cfg = {
        "asu_june_bot": {
            "corpus": {
                "active": "default",
                "corpora": {
                    "default": {
                        "key": "default",
                        "name": "asu_june_bot_v2",
                        "chunks_path": "data/asu_june_bot/chunks_v2.jsonl",
                        "cache_path": "data/asu_june_bot/embeddings_cache_v2.jsonl",
                        "index_dir": "data/asu_june_bot/numpy_index_v2",
                        "report_path": "data/asu_june_bot/index_v2_report.json",
                    },
                    "ntk": {
                        "key": "ntk",
                        "name": "ntk_yandex_corpus",
                        "chunks_path": "data/asu_june_bot_ntk/chunks_v2.jsonl",
                        "cache_path": "data/asu_june_bot_ntk/embeddings_cache_v2.jsonl",
                        "index_dir": "data/asu_june_bot_ntk/numpy_index_v2",
                        "report_path": "data/asu_june_bot_ntk/index_v2_report.json",
                    },
                },
            }
        }
    }

    old = os.environ.get("ASU_JUNE_BOT_ACTIVE_CORPUS")
    os.environ["ASU_JUNE_BOT_ACTIVE_CORPUS"] = "ntk"
    try:
        assert get_active_corpus_key(cfg) == "ntk"
        corpus = get_corpus_config(cfg)
        assert corpus.key == "ntk"
        assert corpus.index_dir.endswith("data/asu_june_bot_ntk/numpy_index_v2")
    finally:
        if old is None:
            os.environ.pop("ASU_JUNE_BOT_ACTIVE_CORPUS", None)
        else:
            os.environ["ASU_JUNE_BOT_ACTIVE_CORPUS"] = old
