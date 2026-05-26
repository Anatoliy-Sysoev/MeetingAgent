from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import wave
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[2]


def load_script(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ingest = load_script("meeting_ingest_20", "scripts/20_ingest_meeting.py")
extract_audio = load_script("meeting_extract_audio_21", "scripts/21_extract_audio.py")


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


def test_ingest_creates_valid_meeting_card(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    write_tiny_wav(source)
    meetings_root = tmp_path / "meetings"

    code = ingest.run(
        argparse.Namespace(
            file=str(source),
            title="Схема уровня поддержки",
            date="2026-05-26",
            meeting_id=None,
            meetings_root=str(meetings_root),
            retention_policy="default",
            force=False,
        )
    )

    assert code == 0
    meeting_dir = meetings_root / "2026-05-26__shema-urovnya-podderzhki"
    meeting = read_json(meeting_dir / "meeting.json")
    validate_meeting(meeting)
    assert meeting["processing_status"] == "new"
    assert meeting["source"]["kind"] == "offline_record"
    assert meeting["source"]["media_files"][0]["path"] == "source/source.wav"
    assert (meeting_dir / "source" / "source.wav").exists()
    assert "source/source.wav" in meeting["rag"]["no_index_artifacts"]


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is required")
def test_extract_audio_updates_meeting_metadata(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    write_tiny_wav(source)
    meetings_root = tmp_path / "meetings"
    ingest.run(
        argparse.Namespace(
            file=str(source),
            title="Audio Smoke",
            date="2026-05-26",
            meeting_id=None,
            meetings_root=str(meetings_root),
            retention_policy="default",
            force=False,
        )
    )
    meeting_dir = meetings_root / "2026-05-26__audio-smoke"

    code = extract_audio.run(argparse.Namespace(meeting_dir=str(meeting_dir), force=False))

    assert code == 0
    meeting = read_json(meeting_dir / "meeting.json")
    validate_meeting(meeting)
    assert meeting["processing_status"] == "new"
    assert (meeting_dir / "source" / "audio_16k_mono.wav").exists()
    media_paths = [item["path"] for item in meeting["source"]["media_files"]]
    assert media_paths == ["source/source.wav", "source/audio_16k_mono.wav"]
    assert "source/audio_16k_mono.wav" in meeting["rag"]["no_index_artifacts"]
