from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.core.config import load_asu_config  # noqa: E402
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
                    "private": {
                        "key": "private",
                        "name": "private_corpus",
                        "chunks_path": "data/private_corpus/chunks_v2.jsonl",
                        "cache_path": "data/private_corpus/embeddings_cache_v2.jsonl",
                        "index_dir": "data/private_corpus/numpy_index_v2",
                        "report_path": "data/private_corpus/index_v2_report.json",
                    },
                },
            }
        }
    }

    old = os.environ.get("ASU_JUNE_BOT_ACTIVE_CORPUS")
    os.environ["ASU_JUNE_BOT_ACTIVE_CORPUS"] = "private"
    try:
        assert get_active_corpus_key(cfg) == "private"
        corpus = get_corpus_config(cfg)
        assert corpus.key == "private"
        assert corpus.index_dir.endswith("data/private_corpus/numpy_index_v2")
    finally:
        if old is None:
            os.environ.pop("ASU_JUNE_BOT_ACTIVE_CORPUS", None)
        else:
            os.environ["ASU_JUNE_BOT_ACTIVE_CORPUS"] = old


def test_private_corpus_can_be_added_through_ignored_local_overlay(tmp_path: Path) -> None:
    (tmp_path / "corpus.yaml").write_text(
        """active: default
corpora:
  default:
    key: default
    name: public_default
    chunks_path: data/default/chunks.jsonl
""",
        encoding="utf-8",
    )
    (tmp_path / "corpus.local.yaml").write_text(
        """corpora:
  private_project:
    key: private_project
    name: private_project_corpus
    chunks_path: data/private_project/chunks.jsonl
    cache_path: data/private_project/cache.jsonl
    index_dir: data/private_project/index
    report_path: data/private_project/report.json
""",
        encoding="utf-8",
    )

    old = os.environ.get("ASU_JUNE_BOT_ACTIVE_CORPUS")
    os.environ["ASU_JUNE_BOT_ACTIVE_CORPUS"] = "private_project"
    try:
        loaded = load_asu_config(tmp_path)
        corpus = get_corpus_config({"asu_june_bot": loaded})
        assert loaded["corpus"]["corpora"]["default"]["name"] == "public_default"
        assert corpus.key == "private_project"
        assert corpus.name == "private_project_corpus"
        assert corpus.chunks_path.endswith("data/private_project/chunks.jsonl")
        assert corpus.index_dir.endswith("data/private_project/index")
    finally:
        if old is None:
            os.environ.pop("ASU_JUNE_BOT_ACTIVE_CORPUS", None)
        else:
            os.environ["ASU_JUNE_BOT_ACTIVE_CORPUS"] = old
