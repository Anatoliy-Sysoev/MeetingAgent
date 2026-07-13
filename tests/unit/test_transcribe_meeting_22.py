from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest
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


def test_choose_media_can_select_registered_live_audio(tmp_path: Path) -> None:
    meeting_dir = make_meeting(tmp_path)
    live_audio = meeting_dir / "source" / "live_audio.SYS.wav"
    write_tiny_wav(live_audio)
    meeting_path = meeting_dir / "meeting.json"
    meeting = read_json(meeting_path)
    meeting["source"]["media_files"].append(
        {
            "path": "source/live_audio.SYS.wav",
            "media_type": "audio",
            "duration_seconds": 0.1,
        }
    )

    selected = transcribe22.choose_media(
        meeting_dir,
        meeting,
        "source/live_audio.SYS.wav",
    )

    assert selected == live_audio.resolve()


@pytest.mark.parametrize(
    "selected",
    ["source/not-registered.wav", "../outside.wav", r"C:\private\audio.wav"],
)
def test_choose_media_rejects_unsafe_or_unregistered_selection(
    tmp_path: Path,
    selected: str,
) -> None:
    meeting_dir = make_meeting(tmp_path)
    meeting = read_json(meeting_dir / "meeting.json")

    with pytest.raises(transcribe22.TranscribeMeetingError):
        transcribe22.choose_media(meeting_dir, meeting, selected)


def make_args(meeting_dir: Path, segments_path: Path | None, *, force: bool = False, resume: bool = False, dry_run: bool = False):
    return argparse.Namespace(
        meeting_dir=str(meeting_dir),
        engine="from-segments",
        segments_path=str(segments_path) if segments_path is not None else None,
        model=None,
        language="ru",
        compute_type="int8",
        force=force,
        resume=resume,
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
    assert report["engine"] == "from-segments"
    assert report["backend_metrics"]["asr_engine"] == "from-segments"
    assert report["backend_metrics"]["input_rows"] == 3


def test_transcribe_refuses_existing_transcript_without_force(tmp_path: Path) -> None:
    meeting_dir = make_meeting(tmp_path)
    segments_path = tmp_path / "segments.jsonl"
    segments_path.write_text(json.dumps({"start": 0, "end": 1, "text": "Текст."}, ensure_ascii=False) + "\n", encoding="utf-8")
    assert transcribe22.run(make_args(meeting_dir, segments_path)) == 0

    code = transcribe22.run(make_args(meeting_dir, segments_path))

    assert code == 0
    meeting = read_json(meeting_dir / "meeting.json")
    assert meeting["processing_status"] == "transcribed"
    assert "last_error" not in meeting


def test_transcribe_dry_run_does_not_mutate_meeting(tmp_path: Path) -> None:
    meeting_dir = make_meeting(tmp_path)
    segments_path = tmp_path / "segments.jsonl"
    segments_path.write_text(json.dumps({"start": 0, "end": 1, "text": "Текст."}, ensure_ascii=False) + "\n", encoding="utf-8")

    code = transcribe22.run(make_args(meeting_dir, segments_path, dry_run=True))

    assert code == 0
    meeting = read_json(meeting_dir / "meeting.json")
    assert meeting["processing_status"] == "new"
    assert not (meeting_dir / "transcript" / "segments.jsonl").exists()


def test_transcribe_resume_reuses_existing_segments_after_failed_status(tmp_path: Path) -> None:
    meeting_dir = make_meeting(tmp_path)
    transcript_dir = meeting_dir / "transcript"
    transcript_dir.mkdir(parents=True, exist_ok=True)
    segments_path = transcript_dir / "segments.jsonl"
    segments_path.write_text(
        json.dumps({"start": 0, "end": 1.5, "text": "Сегмент для resume."}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    meeting = read_json(meeting_dir / "meeting.json")
    meeting["processing_status"] = "failed"
    meeting["artifacts"]["segments"] = "transcript/segments.jsonl"
    meeting["last_error"] = {"stage": "asr", "message": "previous failure", "timestamp": "2026-06-01T10:00:00+03:00"}
    (meeting_dir / "meeting.json").write_text(json.dumps(meeting, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    code = transcribe22.run(make_args(meeting_dir, None, resume=True))

    assert code == 0
    meeting = read_json(meeting_dir / "meeting.json")
    validate_meeting(meeting)
    assert meeting["processing_status"] == "transcribed"
    assert "last_error" not in meeting
    report = read_json(meeting_dir / "transcript" / "transcription_report.json")
    assert report["backend_metrics"]["resume"] is True
    assert report["backend_metrics"]["input_rows"] == 1


def test_transcribe_failed_requires_force_or_resume(tmp_path: Path) -> None:
    meeting_dir = make_meeting(tmp_path)
    segments_path = tmp_path / "segments.jsonl"
    segments_path.write_text(json.dumps({"start": 0, "end": 1, "text": "Текст."}, ensure_ascii=False) + "\n", encoding="utf-8")
    meeting = read_json(meeting_dir / "meeting.json")
    meeting["processing_status"] = "failed"
    (meeting_dir / "meeting.json").write_text(json.dumps(meeting, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    code = transcribe22.run(make_args(meeting_dir, segments_path))

    assert code == 1
    meeting = read_json(meeting_dir / "meeting.json")
    assert meeting["processing_status"] == "failed"


def test_success_validates_written_artifact_paths(tmp_path: Path, monkeypatch) -> None:
    meeting_dir = make_meeting(tmp_path)
    segments_path = tmp_path / "segments.jsonl"
    segments_path.write_text(json.dumps({"start": 0, "end": 1, "text": "Текст."}, ensure_ascii=False) + "\n", encoding="utf-8")
    real_write_exports = transcribe22.write_transcript_exports

    def fake_write_exports(output_dir, document, *, formats=None):
        written = real_write_exports(output_dir, document, formats=formats)
        written["transcript_txt"].unlink()
        return written

    monkeypatch.setattr(transcribe22, "write_transcript_exports", fake_write_exports)

    code = transcribe22.run(make_args(meeting_dir, segments_path))

    assert code == 1
    meeting = read_json(meeting_dir / "meeting.json")
    assert meeting["processing_status"] == "failed"
    assert meeting["last_error"]["stage"] == "artifact_validation"


def test_faster_whisper_backend_uses_normalized_audio_and_writes_metrics(tmp_path: Path, monkeypatch) -> None:
    meeting_dir = make_meeting(tmp_path)
    normalized_audio = meeting_dir / "source" / "audio_16k_mono.wav"
    write_tiny_wav(normalized_audio)
    meeting = read_json(meeting_dir / "meeting.json")
    meeting["source"]["media_files"].append({"path": "source/audio_16k_mono.wav", "media_type": "audio"})
    (meeting_dir / "meeting.json").write_text(json.dumps(meeting, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    seen: dict[str, object] = {}

    def fake_transcribe(media_path: Path, args):
        seen["media_path"] = media_path
        return (
            [
                {
                    "start": 0,
                    "end": 1.5,
                    "text": "Тестовая фраза.",
                    "source": "MIX",
                    "engine": "faster-whisper",
                    "language": "ru",
                    "avg_logprob": -0.1,
                    "no_speech_prob": 0.02,
                }
            ],
            {
                "asr_engine": "faster-whisper",
                "asr_model": "small",
                "device": "cpu",
                "compute_type": "int8",
                "beam_size": 5,
                "vad_filter": True,
            },
        )

    monkeypatch.setattr(transcribe22, "transcribe_faster_whisper", fake_transcribe)
    args = argparse.Namespace(
        meeting_dir=str(meeting_dir),
        engine="faster-whisper",
        segments_path=None,
        media_path=None,
        model="small",
        language="ru",
        compute_type="int8",
        device="cpu",
        beam_size=5,
        vad_filter=True,
        check_model=False,
        force=False,
        resume=False,
        dry_run=False,
        output_formats="txt,md,srt,vtt,json,jsonl",
        chunk_seconds=24,
        gigaam_root=str(Path.home() / "GigaAM"),
        gigaam_cache_root=r"C:\ProgramData\gigaam_cache",
    )

    code = transcribe22.run(args)

    assert code == 0
    assert seen["media_path"] == normalized_audio
    rows = [
        json.loads(line)
        for line in (meeting_dir / "transcript" / "segments.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert rows[0]["avg_logprob"] == -0.1
    assert rows[0]["no_speech_prob"] == 0.02
    report = read_json(meeting_dir / "transcript" / "transcription_report.json")
    assert report["backend_metrics"]["asr_engine"] == "faster-whisper"
    assert report["backend_metrics"]["asr_model"] == "small"


def test_gigaam_backend_writes_card_outputs_from_backend_rows(tmp_path: Path, monkeypatch) -> None:
    meeting_dir = make_meeting(tmp_path)
    work_dir = meeting_dir / "transcript" / "_gigaam"
    raw_segments_path = work_dir / "raw_segments.jsonl"

    def fake_gigaam_backend(**kwargs):
        work_dir.mkdir(parents=True, exist_ok=True)
        raw_segments_path.write_text(
            json.dumps({"start": 0, "end": 2, "text": "GigaAM текст."}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return SimpleNamespace(
            segments=[
                {
                    "start": 0,
                    "end": 2,
                    "text": "GigaAM текст.",
                    "source": "MIX",
                    "engine": "gigaam",
                    "language": "ru",
                }
            ],
            metrics={
                "asr_engine": "gigaam",
                "asr_model": "gigaam/v3_e2e_rnnt",
                "chunk_seconds": 24,
                "chunks": 1,
                "raw_segments": str(raw_segments_path),
                "cache_root": r"C:\ProgramData\gigaam_cache",
            },
            work_dir=work_dir,
            raw_segments_path=raw_segments_path,
        )

    monkeypatch.setattr(transcribe22, "run_gigaam_backend", fake_gigaam_backend)
    args = argparse.Namespace(
        meeting_dir=str(meeting_dir),
        engine="gigaam",
        segments_path=None,
        media_path=None,
        model="v3_e2e_rnnt",
        language="ru",
        compute_type="int8",
        device="cpu",
        beam_size=5,
        vad_filter=True,
        check_model=False,
        force=False,
        resume=False,
        dry_run=False,
        output_formats="txt,md,srt,vtt,json,jsonl",
        chunk_seconds=24,
        gigaam_root=str(Path.home() / "GigaAM"),
        gigaam_cache_root=r"C:\ProgramData\gigaam_cache",
    )

    code = transcribe22.run(args)

    assert code == 0
    assert raw_segments_path.exists()
    rows = [
        json.loads(line)
        for line in (meeting_dir / "transcript" / "segments.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert rows[0]["engine"] == "gigaam"
    assert rows[0]["source"] == "MIX"
    report = read_json(meeting_dir / "transcript" / "transcription_report.json")
    assert report["engine"] == "gigaam"
    assert report["backend_metrics"]["raw_segments"].endswith("raw_segments.jsonl")
    assert report["backend_metrics"]["cache_root"] == r"C:\ProgramData\gigaam_cache"
