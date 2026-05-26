from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[2]


def load_script(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


enrich = load_script("meeting_enrich_27", "scripts/27_enrich_meeting_chunks.py")
index_meeting = load_script("meeting_index_28", "scripts/28_index_meeting_chunks.py")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def validate_meeting(meeting: dict) -> None:
    schema = read_json(REPO_ROOT / "configs" / "schemas" / "meeting.schema.json")
    Draft202012Validator(schema).validate(meeting)


def make_chunked_meeting(tmp_path: Path) -> Path:
    meeting_dir = tmp_path / "meetings" / "2026-05-26__semantic-smoke"
    (meeting_dir / "transcript").mkdir(parents=True)
    (meeting_dir / "artifacts").mkdir()
    meeting = {
        "schema_version": 1,
        "meeting_id": "2026-05-26__semantic-smoke",
        "title": "Semantic Smoke",
        "date": "2026-05-26",
        "source": {"kind": "offline_record", "media_files": [{"path": "source/source.wav", "media_type": "audio"}]},
        "processing_status": "transcribed",
        "participants": [],
        "artifacts": {"chunks": "transcript/chunks.jsonl"},
        "classification": {"project_stage": "PRJ-00", "needs_review": True},
        "links": {},
        "retention": {"policy": "default"},
        "rag": {"index_policy": "structured_artifacts_and_final_transcript"},
        "created_at": "2026-05-26T10:00:00+03:00",
        "updated_at": "2026-05-26T10:00:00+03:00",
    }
    (meeting_dir / "meeting.json").write_text(json.dumps(meeting, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    chunks = [
        {
            "chunk_id": "2026-05-26__semantic-smoke-chunk-0001",
            "meeting_id": "2026-05-26__semantic-smoke",
            "source_type": "meeting_chunk",
            "start": 0.0,
            "end": 60.0,
            "speakers": ["SPEAKER_UNKNOWN"],
            "sources": ["MIX"],
            "text": "[SPEAKER_UNKNOWN] Решили подготовить выгрузку по ФТТ. Нужно проверить НОВАДОК.",
            "utterance_ids": ["utt-000001"],
        }
    ]
    with (meeting_dir / "transcript" / "chunks.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for chunk in chunks:
            fh.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    return meeting_dir


def test_enrich_meeting_chunks_writes_semantic_metadata(tmp_path: Path) -> None:
    meeting_dir = make_chunked_meeting(tmp_path)

    code = enrich.run(argparse.Namespace(meeting_dir=str(meeting_dir), force=False))

    assert code == 0
    rows = read_jsonl(meeting_dir / "artifacts" / "enriched_chunks.jsonl")
    assert rows[0]["semantic_type"] == "decision"
    assert "ФТТ" in rows[0]["entities"]
    assert "НОВАДОК" in rows[0]["entities"]
    assert rows[0]["decisions"]
    meeting = read_json(meeting_dir / "meeting.json")
    validate_meeting(meeting)
    assert meeting["artifacts"]["enriched_chunks"] == "artifacts/enriched_chunks.jsonl"


def test_index_meeting_chunks_exports_rag_compatible_rows(tmp_path: Path) -> None:
    meeting_dir = make_chunked_meeting(tmp_path)
    enrich.run(argparse.Namespace(meeting_dir=str(meeting_dir), force=False))
    output = tmp_path / "meeting_chunks.jsonl"

    code = index_meeting.run(argparse.Namespace(meeting_dir=str(meeting_dir), output=str(output)))

    assert code == 0
    rows = read_jsonl(output)
    assert len(rows) == 1
    row = rows[0]
    assert row["source_type"] == "meeting_chunk"
    assert row["meeting_id"] == "2026-05-26__semantic-smoke"
    assert row["timestamp_start"] == "00:00:00"
    assert row["timestamp_end"] == "00:01:00"
    assert "Встреча: Semantic Smoke" in row["text"]
    assert row["semantic_type"] == "decision"
    meeting = read_json(meeting_dir / "meeting.json")
    validate_meeting(meeting)
    assert "transcript/chunks.jsonl" in meeting["rag"]["indexed_artifacts"]
