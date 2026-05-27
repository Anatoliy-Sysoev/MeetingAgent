from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "32_index_meeting_artifacts.py"


def load_module():
    spec = importlib.util.spec_from_file_location("meeting_artifact_index", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_to_index_rows_exports_decision_with_timestamp(tmp_path: Path) -> None:
    module = load_module()
    meeting = {
        "meeting_id": "2026-05-26__support-scheme",
        "title": "Схема уровня поддержки",
        "date": "2026-05-26",
        "artifacts": {"decisions": "artifacts/decisions.json"},
    }
    doc = {
        "items": [
            {
                "decision_id": "DEC-001",
                "title": "Линии поддержки",
                "decision": "Разделить поддержку по линиям.",
                "status": "accepted",
                "source_refs": [
                    {
                        "kind": "rag_source",
                        "path": "transcript/chunks.jsonl",
                        "start": 12.0,
                        "end": 42.0,
                        "quote": "Решили разделить поддержку по линиям.",
                    }
                ],
            }
        ]
    }

    rows = module.to_index_rows(tmp_path, meeting, "decisions", doc)

    assert rows[0]["source_type"] == "meeting_decision"
    assert rows[0]["artifact_id"] == "DEC-001"
    assert rows[0]["timestamp_start"] == "00:00:12"
    assert "Разделить поддержку" in rows[0]["text"]


def test_upsert_rows_preserves_meeting_chunks(tmp_path: Path) -> None:
    module = load_module()
    output = tmp_path / "meeting_chunks.jsonl"
    existing = [
        {"meeting_id": "m1", "source_type": "meeting_chunk", "chunk_id": "m1-chunk"},
        {"meeting_id": "m1", "source_type": "meeting_decision", "chunk_id": "old-decision"},
        {"meeting_id": "m2", "source_type": "meeting_decision", "chunk_id": "other-decision"},
    ]
    output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in existing), encoding="utf-8")

    module.upsert_rows(output, "m1", [{"meeting_id": "m1", "source_type": "meeting_decision", "chunk_id": "new-decision"}])
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]

    assert [row["chunk_id"] for row in rows] == ["m1-chunk", "other-decision", "new-decision"]
