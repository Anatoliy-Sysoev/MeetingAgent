from __future__ import annotations

import argparse
import importlib.util
import json
import wave
from pathlib import Path

from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[2]


def load_script(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ingest = load_script("meeting_ingest_20_for_speaker", "scripts/20_ingest_meeting.py")
merge_speakers = load_script("meeting_merge_speakers_24", "scripts/24_merge_transcript_speakers.py")
chunk_meeting = load_script("meeting_chunk_26", "scripts/26_chunk_meeting.py")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def validate_meeting(meeting: dict) -> None:
    schema = read_json(REPO_ROOT / "configs" / "schemas" / "meeting.schema.json")
    Draft202012Validator(schema).validate(meeting)


def write_tiny_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 1600)


def make_meeting_with_segments(tmp_path: Path) -> Path:
    source = tmp_path / "source.wav"
    write_tiny_wav(source)
    meetings_root = tmp_path / "meetings"
    ingest.run(
        argparse.Namespace(
            file=str(source),
            title="Chunk Smoke",
            date="2026-05-26",
            meeting_id=None,
            meetings_root=str(meetings_root),
            retention_policy="default",
            force=False,
        )
    )
    meeting_dir = meetings_root / "2026-05-26__chunk-smoke"
    transcript_dir = meeting_dir / "transcript"
    transcript_dir.mkdir(exist_ok=True)
    segments = [
        {"start": 0.0, "end": 10.0, "text": "Первый сегмент.", "source": "MIX"},
        {"start": 10.0, "end": 70.0, "text": "Второй сегмент.", "source": "MIX"},
        {"start": 70.0, "end": 130.0, "text": "Третий сегмент.", "source": "MIX"},
    ]
    with (transcript_dir / "segments.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for segment in segments:
            fh.write(json.dumps(segment, ensure_ascii=False) + "\n")
    meeting = read_json(meeting_dir / "meeting.json")
    meeting["artifacts"]["segments"] = "transcript/segments.jsonl"
    meeting["processing_status"] = "transcribed"
    (meeting_dir / "meeting.json").write_text(
        json.dumps(meeting, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return meeting_dir


def test_merge_transcript_speakers_creates_unknown_speaker_transcript(tmp_path: Path) -> None:
    meeting_dir = make_meeting_with_segments(tmp_path)

    code = merge_speakers.run(argparse.Namespace(meeting_dir=str(meeting_dir), force=False))

    assert code == 0
    utterances = read_jsonl(meeting_dir / "transcript" / "speaker_transcript.jsonl")
    assert [row["utterance_id"] for row in utterances] == ["utt-000001", "utt-000002", "utt-000003"]
    assert {row["speaker"] for row in utterances} == {"SPEAKER_UNKNOWN"}
    assert {row["source"] for row in utterances} == {"MIX"}
    assert (meeting_dir / "transcript" / "speaker_transcript.txt").exists()
    meeting = read_json(meeting_dir / "meeting.json")
    validate_meeting(meeting)
    assert meeting["artifacts"]["speaker_transcript"] == "transcript/speaker_transcript.jsonl"


def test_chunk_meeting_groups_utterances_without_splitting_them(tmp_path: Path) -> None:
    meeting_dir = make_meeting_with_segments(tmp_path)
    merge_speakers.run(argparse.Namespace(meeting_dir=str(meeting_dir), force=False))

    code = chunk_meeting.run(
        argparse.Namespace(
            meeting_dir=str(meeting_dir),
            max_seconds=75.0,
            max_chars=6000,
            force=False,
        )
    )

    assert code == 0
    chunks = read_jsonl(meeting_dir / "transcript" / "chunks.jsonl")
    assert len(chunks) == 2
    assert chunks[0]["chunk_id"] == "2026-05-26__chunk-smoke-chunk-0001"
    assert chunks[0]["utterance_ids"] == ["utt-000001", "utt-000002"]
    assert chunks[1]["utterance_ids"] == ["utt-000003"]
    assert chunks[0]["speakers"] == ["SPEAKER_UNKNOWN"]
    assert chunks[0]["source_type"] == "meeting_chunk"
    meeting = read_json(meeting_dir / "meeting.json")
    validate_meeting(meeting)
    assert meeting["artifacts"]["chunks"] == "transcript/chunks.jsonl"
