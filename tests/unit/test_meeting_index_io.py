from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def load_script(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


index_chunks = load_script("meeting_index_chunks_28", "scripts/28_index_meeting_chunks.py")
index_artifacts = load_script("meeting_index_artifacts_32_for_io", "scripts/32_index_meeting_artifacts.py")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_chunk_index_upsert_skips_invalid_lines_and_writes_atomically(tmp_path: Path) -> None:
    output = tmp_path / "meeting_chunks.jsonl"
    output.write_text(
        json.dumps({"meeting_id": "m1", "chunk_id": "old"}, ensure_ascii=False)
        + "\n"
        + "\x00\x00not-json\n"
        + json.dumps({"meeting_id": "m2", "chunk_id": "keep"}, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )

    index_chunks.upsert_rows(output, "m1", [{"meeting_id": "m1", "chunk_id": "new"}])

    rows = read_jsonl(output)
    assert [row["chunk_id"] for row in rows] == ["keep", "new"]
    assert not list(tmp_path.glob(".meeting_chunks.jsonl.*.tmp"))
    assert not (tmp_path / "meeting_chunks.jsonl.lock").exists()


def test_artifact_index_upsert_skips_invalid_lines_and_keeps_meeting_chunks(tmp_path: Path) -> None:
    output = tmp_path / "meeting_chunks.jsonl"
    output.write_text(
        json.dumps(
            {"meeting_id": "m1", "source_type": "meeting_chunk", "chunk_id": "m1-chunk"},
            ensure_ascii=False,
        )
        + "\n"
        + "{bad json\n"
        + json.dumps(
            {"meeting_id": "m1", "source_type": "meeting_decision", "chunk_id": "old-decision"},
            ensure_ascii=False,
        )
        + "\n"
        + json.dumps(
            {"meeting_id": "m2", "source_type": "meeting_decision", "chunk_id": "other"},
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    index_artifacts.upsert_rows(
        output,
        "m1",
        [{"meeting_id": "m1", "source_type": "meeting_decision", "chunk_id": "new-decision"}],
    )

    rows = read_jsonl(output)
    assert [row["chunk_id"] for row in rows] == ["m1-chunk", "other", "new-decision"]
    assert not list(tmp_path.glob(".meeting_chunks.jsonl.*.tmp"))
    assert not (tmp_path / "meeting_chunks.jsonl.lock").exists()
