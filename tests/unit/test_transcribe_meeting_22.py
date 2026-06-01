from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import wave
from pathlib import Path

from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))


def load_script(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ingest = load_script("meeting_ingest_20_for_transcribe22", "scripts/20_ingest_meeting.py")
transcribe22 = load_script("meeting_transcribe_22", "scripts/22_transcribe_meeting.py")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_meeting(meeting: dict) -> None:
    schema = read_json(REPO_ROOT / "configs" / "schemas" / "meeting.schema.json")
    Draft202012Validator(schema).validate(meeting)


def write_tiny_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 1600)


def make_meeting(tmp_path: Path) -> Path:
    source = tmp_path / "source.wav"
    write_tiny_wav(source)
    meetings_root = tmp_path / "meetings"
    code = ingest.run(
        argparse.Namespace(
            file=str(source),
            title="Transcribe Contract",
            date="2026-06-01",
            meeting_id=None,
            meetings_root=str(meetings_root),
            retention_policy="default",
            force=False,
        )
    )
    assert code == 0
    return meetings_root / "2026-06-01__transcribe-contract"


def make_args(meeting_dir: Path, segments_path: Path, *, force: bool = False, dry_run: bool = False):
    return argparse.Namespace(
        meeting_dir=str(meeting_dir),
        engine="from-segments",
        segments_path=str(segments_path),
        model=None,
        language="ru",
        compute_type="int8",
        force=force,
        resume=False,
        dry_run=dry_run,
        output_formats="txt,md,srt,vtt,json,jsonl",
        chunk_seconds=24,
        gigaam_root=str(Path.home() / "GigaAM"),
        gigaam_cache_root=r"C:\ProgramData\gigaam_cache",
    )


def test_transcribe_from_segments_writes_canonical_outputs_and_meeting_artifacts(tmp_path: Path) -> None:
    meeting_dir = make_meeting(tmp_path)
    segments_path = tmp_path / "external_segments.jsonl"
    segments_path.write_text(
        "\n".join(
            [
                json.dumps({"start": 5, "end": 7, "text": "Второй сегмент."}, ensure_ascii=False),
                json.dumps({"start": 0, "end": 2.5, "text": "Первый сегмент.", "source": "MIC"}, ensure_ascii=False),
                json.dumps({"start": 9, "end": 10, "text": ""}, ensure_ascii=False),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    code = transcribe22.run(make_args(meeting_dir, segments_path))

    assert code == 0
    meeting = read_json(meeting_dir / "meeting.json")
    validate_meeting(meeting)
    assert meeting["processing_status"] == "transcribed"
    assert meeting["artifacts"]["segments"] == "transcript/segments.jsonl"
    assert meeting["artifacts"]["transcript"] == "transcript/transcript.md"
    assert meeting["artifacts"]["transcript_txt"] == "transcript/transcript.txt"
    assert meeting["artifacts"]["transcript_json"] == "transcript/transcript.json"
    assert meeting["artifacts"]["transcript_srt"] == "transcript/transcript.srt"
    assert meeting["artifacts"]["transcript_vtt"] == "transcript/transcript.vtt"
    assert meeting["artifacts"]["transcription_report"] == "transcript/transcription_report.json"

    rows = [
        json.loads(line)
        for line in (meeting_dir / "transcript" / "segments.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [row["segment_id"] for row in rows] == ["seg-000001", "seg-000002"]
    assert [row["text"] for row in rows] == ["Первый сегмент.", "Второй сегмент."]
    assert rows[0]["source"] == "MIC"
    assert rows[0]["engine"] == "from-segments"
    assert (meeting_dir / "transcript" / "transcript.srt").exists()
    assert (meeting_dir / "transcript" / "transcript.vtt").read_text(encoding="utf-8").startswith("WEBVTT")
    report = read_json(meeting_dir / "transcript" / "transcription_report.json")
    assert report["segments_count"] == 2
    assert report["empty_segments_dropped"] == 1


def test_transcribe_refuses_existing_transcript_without_force(tmp_path: Path) -> None:
    meeting_dir = make_meeting(tmp_path)
    segments_path = tmp_path / "segments.jsonl"
    segments_path.write_text(json.dumps({"start": 0, "end": 1, "text": "Текст."}, ensure_ascii=False) + "\n", encoding="utf-8")
    assert transcribe22.run(make_args(meeting_dir, segments_path)) == 0

    code = transcribe22.run(make_args(meeting_dir, segments_path))

    assert code == 1
    meeting = read_json(meeting_dir / "meeting.json")
    assert meeting["processing_status"] == "transcribed"


def test_transcribe_dry_run_does_not_mutate_meeting(tmp_path: Path) -> None:
    meeting_dir = make_meeting(tmp_path)
    segments_path = tmp_path / "segments.jsonl"
    segments_path.write_text(json.dumps({"start": 0, "end": 1, "text": "Текст."}, ensure_ascii=False) + "\n", encoding="utf-8")

    code = transcribe22.run(make_args(meeting_dir, segments_path, dry_run=True))

    assert code == 0
    meeting = read_json(meeting_dir / "meeting.json")
    assert meeting["processing_status"] == "new"
    assert not (meeting_dir / "transcript" / "segments.jsonl").exists()
