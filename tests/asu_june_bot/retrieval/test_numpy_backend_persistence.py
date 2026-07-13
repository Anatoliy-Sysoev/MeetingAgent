from __future__ import annotations

import base64
import json
from pathlib import Path

import numpy as np

from asu_june_bot.retrieval.numpy_backend import (
    EMBEDDINGS_FILE,
    MANIFEST_FILE,
    METADATA_FILE,
    build_index,
    load_index,
)


NUMPY_126_FLOAT32_INDEX = base64.b64decode(
    "k05VTVBZAQB2AHsnZGVzY3InOiAnPGY0JywgJ2ZvcnRyYW5fb3JkZXInOiBGYWxzZSwg"
    "J3NoYXBlJzogKDIsIDIpLCB9ICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAg"
    "ICAgICAgICAgICAgICAgICAgICAgIAoAAIA/AAAAAAAAAAAAAIA/"
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )


def test_numpy_index_build_load_and_query_round_trip(tmp_path: Path) -> None:
    chunks_path = tmp_path / "chunks.jsonl"
    cache_path = tmp_path / "embeddings.jsonl"
    index_dir = tmp_path / "index"
    chunks = [
        {
            "chunk_id": "alpha",
            "text": "Alpha document",
            "source_path": "source/alpha.txt",
            "relative_path": "alpha.txt",
            "extension": ".txt",
            "sha256": "a" * 64,
            "mtime": 1.0,
            "chunk_index": 0,
            "chars": 14,
        },
        {
            "chunk_id": "beta",
            "text": "Beta document",
            "source_path": "source/beta.txt",
            "relative_path": "beta.txt",
            "extension": ".txt",
            "sha256": "b" * 64,
            "mtime": 2.0,
            "chunk_index": 0,
            "chars": 13,
        },
    ]
    cache = [
        {"chunk_id": "alpha", "embedding_model": "test", "embedding": [1.0, 0.0]},
        {"chunk_id": "beta", "embedding_model": "test", "embedding": [0.0, 1.0]},
    ]
    _write_jsonl(chunks_path, chunks)
    _write_jsonl(cache_path, cache)

    manifest = build_index(chunks_path, cache_path, index_dir, "test")
    index = load_index(index_dir)
    results = index.query([0.9, 0.1], top_k=2)

    assert manifest["count"] == 2
    assert index.embeddings.dtype == np.dtype("float32")
    assert isinstance(index.embeddings, np.memmap)
    assert [row["metadata"]["chunk_id"] for row in results] == ["alpha", "beta"]
    assert results[0]["score"] > results[1]["score"]


def test_numpy_2_loads_index_written_by_numpy_126(tmp_path: Path) -> None:
    index_dir = tmp_path / "legacy-index"
    index_dir.mkdir()
    (index_dir / EMBEDDINGS_FILE).write_bytes(NUMPY_126_FLOAT32_INDEX)
    (index_dir / MANIFEST_FILE).write_text(
        json.dumps({"count": 2, "embedding_dim": 2}),
        encoding="utf-8",
    )
    _write_jsonl(
        index_dir / METADATA_FILE,
        [
            {
                "row_id": 0,
                "document": "Legacy alpha",
                "metadata": {"chunk_id": "legacy-alpha", "relative_path": "alpha.txt"},
            },
            {
                "row_id": 1,
                "document": "Legacy beta",
                "metadata": {"chunk_id": "legacy-beta", "relative_path": "beta.txt"},
            },
        ],
    )

    index = load_index(index_dir)
    results = index.query([1.0, 0.0], top_k=1)

    assert index.embeddings.dtype == np.dtype("float32")
    assert results[0]["metadata"]["chunk_id"] == "legacy-alpha"
