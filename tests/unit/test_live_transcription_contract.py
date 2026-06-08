from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from meeting_agent.live_transcription import LiveSegment, LiveSessionReport, write_live_artifacts


def load_live_cli():
    script_path = REPO_ROOT / "scripts" / "33_live_transcribe_meeting.py"
    spec = importlib.util.spec_from_file_location("live_cli", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def minimal_meeting() -> dict:
    return {
        "schema_version": 1,
        "meeting_id": "2026-06-08__live-smoke",
        "title": "Live smoke",
        "date": "2026-06-08",
        "source": {"kind": "live_session", "audio_tracks": ["MIC"], "derived_tracks": []},
        "processing_status": "new",
        "participants": [],
        "artifacts": {},
        "classification": {},
        "links": {},
        "retention": {"policy": "default"},
        "rag": {
            "index_policy": "structured_artifacts_and_final_transcript",
            "indexed_artifacts": [],
            "no_index_artifacts": [],
        },
        "created_at": "2026-06-08T10:00:00+03:00",
        "updated_at": "2026-06-08T10:00:00+03:00",
    }


def test_live_artifacts_export_jsonl_text_subtitles_and_report(tmp_path: Path) -> None:
    segments = [
        LiveSegment(
            segment_id="live-seg-000000",
            segment_index=0,
            start=0.0,
            end=1.2,
            text="Первый фрагмент",
            source="MIC",
            engine="vosk",
            model="vosk-model-small-ru-0.22",
            confidence=0.91,
        ),
        LiveSegment(
            segment_id="live-seg-000001",
            segment_index=1,
            start=2.0,
            end=3.0,
            text="Второй фрагмент",
            source="MIC",
            engine="vosk",
            model="vosk-model-small-ru-0.22",
        ),
    ]
    partials = [{"text": "Перв", "source": "MIC", "is_final": False}]
    report = LiveSessionReport(
        engine="vosk",
        model="vosk-model-small-ru-0.22",
        source="MIC",
        sample_rate=16000,
        block_ms=300,
        duration_seconds=3.0,
        segments_count=2,
        partials_count=1,
        chars_count=31,
        started_at="2026-06-08T10:00:00+03:00",
        finished_at="2026-06-08T10:00:02+03:00",
        elapsed_seconds=2.0,
    )

    written = write_live_artifacts(tmp_path, segments, partials, report)

    assert set(written) == {
        "live_segments",
        "live_partials",
        "live_transcript",
        "live_srt",
        "live_vtt",
        "live_report",
    }
    rows = [json.loads(line) for line in (tmp_path / "live_segments.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows[0]["segment_id"] == "live-seg-000000"
    assert rows[0]["source"] == "MIC"
    assert "[00:00:00] MIC: Первый фрагмент" in (tmp_path / "live_transcript.txt").read_text(encoding="utf-8")
    assert "00:00:00,000 --> 00:00:01,200" in (tmp_path / "live_subtitles.srt").read_text(encoding="utf-8")
    assert (tmp_path / "live_subtitles.vtt").read_text(encoding="utf-8").startswith("WEBVTT\n\n")
    assert json.loads((tmp_path / "live_report.json").read_text(encoding="utf-8"))["partials_count"] == 1


def test_live_cli_dry_run_validates_meeting_contract(tmp_path: Path, capsys) -> None:
    cli = load_live_cli()
    meeting_dir = tmp_path / "2026-06-08__live-smoke"
    meeting_dir.mkdir()
    (meeting_dir / "meeting.json").write_text(json.dumps(minimal_meeting(), ensure_ascii=False), encoding="utf-8")
    model_dir = tmp_path / "vosk-model-small-ru-0.22"
    model_dir.mkdir()

    exit_code = cli.main_with_argv(
        [
            "--meeting-dir",
            str(meeting_dir),
            "--engine",
            "vosk",
            "--model-path",
            str(model_dir),
            "--source",
            "MIC",
            "--dry-run",
        ]
    )

    assert exit_code == 0
    assert "dry-run ok" in capsys.readouterr().out


def test_live_cli_refuses_overwrite_without_force(tmp_path: Path, capsys) -> None:
    cli = load_live_cli()
    meeting_dir = tmp_path / "2026-06-08__live-smoke"
    live_dir = meeting_dir / "transcript" / "live"
    live_dir.mkdir(parents=True)
    (meeting_dir / "meeting.json").write_text(json.dumps(minimal_meeting(), ensure_ascii=False), encoding="utf-8")
    (live_dir / "live_segments.jsonl").write_text("{}", encoding="utf-8")
    model_dir = tmp_path / "vosk-model-small-ru-0.22"
    model_dir.mkdir()

    exit_code = cli.main_with_argv(
        [
            "--meeting-dir",
            str(meeting_dir),
            "--model-path",
            str(model_dir),
            "--dry-run",
        ]
    )

    assert exit_code == 1
    assert "already exists" in capsys.readouterr().err


def test_live_cli_writes_artifacts_and_updates_meeting_json(tmp_path: Path, monkeypatch) -> None:
    cli = load_live_cli()
    meeting_dir = tmp_path / "2026-06-08__live-smoke"
    meeting_dir.mkdir()
    meeting_path = meeting_dir / "meeting.json"
    meeting_path.write_text(json.dumps(minimal_meeting(), ensure_ascii=False), encoding="utf-8")
    model_dir = tmp_path / "vosk-model-small-ru-0.22"
    model_dir.mkdir()

    def fake_transcribe(_config):
        return type(
            "FakeResult",
            (),
            {
                "segments": [
                    LiveSegment(
                        segment_id="live-seg-000000",
                        segment_index=0,
                        start=0.0,
                        end=1.0,
                        text="Тестовая live фраза",
                        source="MIX",
                        engine="vosk",
                        model="vosk-model-small-ru-0.22",
                    )
                ],
                "partials": [{"text": "Тестовая", "source": "MIX", "is_final": False}],
                "metrics": {"duration": 1.0, "elapsed_seconds": 0.01},
            },
        )()

    monkeypatch.setattr(cli, "transcribe_vosk_live", fake_transcribe)

    exit_code = cli.main_with_argv(
        [
            "--meeting-dir",
            str(meeting_dir),
            "--model-path",
            str(model_dir),
            "--source",
            "MIX",
            "--force",
        ]
    )

    assert exit_code == 0
    meeting = json.loads(meeting_path.read_text(encoding="utf-8"))
    assert meeting["processing_status"] == "transcribed"
    assert meeting["source"]["derived_tracks"] == ["MIX"]
    assert meeting["artifacts"]["live_segments"] == "transcript/live/live_segments.jsonl"
    assert meeting["artifacts"]["live_report"] == "transcript/live/live_report.json"
    assert "transcript/live/live_partials.jsonl" in meeting["rag"]["no_index_artifacts"]
    assert "transcript/live/live_segments.jsonl" in meeting["rag"]["no_index_artifacts"]
    assert (meeting_dir / "transcript" / "live" / "live_segments.jsonl").exists()
