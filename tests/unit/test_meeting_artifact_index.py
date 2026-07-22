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
        "title": "Передача поддержки проекта",
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
                        "speaker_names": ["Алексей Петров"],
                        "speakers": ["SPEAKER_01"],
                        "utterance_ids": ["utt-1"],
                        "quote": "Решили разделить поддержку по линиям.",
                    }
                ],
                "confidence": 0.86,
                "needs_review": False,
            }
        ]
    }

    rows = module.to_index_rows(tmp_path, meeting, "decisions", doc)

    assert rows[0]["source_type"] == "meeting_decision"
    assert rows[0]["artifact_id"] == "DEC-001"
    assert rows[0]["timestamp_start"] == "00:00:12"
    assert rows[0]["confidence"] == 0.86
    assert rows[0]["speaker_names"] == ["Алексей Петров"]
    assert rows[0]["utterance_ids"] == ["utt-1"]
    assert "Разделить поддержку" in rows[0]["text"]
    assert "Уверенность: 0.86" in rows[0]["text"]
    assert "Спикеры: Алексей Петров" in rows[0]["text"]
    assert "source_path" not in rows[0]


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


def test_empty_artifact_upsert_removes_stale_rows_and_keeps_chunks(tmp_path: Path) -> None:
    module = load_module()
    output = tmp_path / "meeting_chunks.jsonl"
    existing = [
        {"meeting_id": "m1", "source_type": "meeting_chunk", "chunk_id": "m1-chunk"},
        {"meeting_id": "m1", "source_type": "meeting_action_item", "chunk_id": "stale-task"},
        {"meeting_id": "m2", "source_type": "meeting_decision", "chunk_id": "other"},
    ]
    output.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in existing),
        encoding="utf-8",
    )

    module.upsert_rows(output, "m1", [])

    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert [row["chunk_id"] for row in rows] == ["m1-chunk", "other"]


def test_safe_resolve_rejects_absolute_and_traversal_paths(tmp_path: Path) -> None:
    module = load_module()

    assert module.safe_resolve(tmp_path, "artifacts/tasks.json") == (
        tmp_path / "artifacts" / "tasks.json"
    ).resolve()
    assert module.safe_resolve(tmp_path, "../private.json") is None
    assert module.safe_resolve(tmp_path, str((tmp_path / "outside.json").resolve())) is None


def test_update_meeting_marks_only_artifacts_actually_processed() -> None:
    module = load_module()
    meeting = {
        "artifacts": {},
        "rag": {"indexed_artifacts": ["artifacts/enriched_chunks.jsonl"]},
    }

    module.update_meeting(meeting, ["decisions"])

    assert meeting["rag"]["indexed_artifacts"] == [
        "artifacts/decisions.json",
        "artifacts/enriched_chunks.jsonl",
    ]
