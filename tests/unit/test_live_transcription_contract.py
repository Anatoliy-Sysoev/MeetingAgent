from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from meeting_agent.live_transcription import LiveSegment, LiveSessionReport, preflight_audio_source, write_live_artifacts
from meeting_agent.live_transcription.audio_capture import AudioSourcePreflight, list_audio_devices
from meeting_agent.live_transcription.vad import SpeechWindow, block_overlaps_speech
from meeting_agent.live_transcription.vosk_backend import VoskLiveConfig, transcribe_vosk_live


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


class FakeSoundDevice:
    @staticmethod
    def query_hostapis():
        return [{"name": "Windows WASAPI"}, {"name": "MME"}]

    @staticmethod
    def query_devices():
        return [
            {
                "name": "Microphone Array",
                "hostapi": 0,
                "max_input_channels": 2,
                "max_output_channels": 0,
                "default_samplerate": 48000.0,
            },
            {
                "name": "Speakers",
                "hostapi": 0,
                "max_input_channels": 0,
                "max_output_channels": 2,
                "default_samplerate": 48000.0,
            },
        ]


class OutputOnlyNoWasapiSoundDevice:
    @staticmethod
    def query_hostapis():
        return [{"name": "MME"}]

    @staticmethod
    def query_devices():
        return [
            {
                "name": "Speakers",
                "hostapi": 0,
                "max_input_channels": 0,
                "max_output_channels": 2,
                "default_samplerate": 48000.0,
            }
        ]


def test_audio_device_listing_marks_wasapi_loopback_candidates() -> None:
    devices = list_audio_devices(sd_module=FakeSoundDevice)

    assert [device.name for device in devices] == ["Microphone Array", "Speakers"]
    assert devices[0].supports_loopback is False
    assert devices[1].supports_loopback is True


def test_audio_preflight_reports_sounddevice_missing() -> None:
    result = preflight_audio_source("MIC", sd_module=False)

    assert result.available is False
    assert result.reason == "sounddevice_missing"


def test_audio_preflight_mic_available() -> None:
    result = preflight_audio_source("MIC", sd_module=FakeSoundDevice, system_name="Windows")

    assert result.available is True
    assert result.reason is None
    assert result.devices[0].name == "Microphone Array"
    assert result.sample_rate == 16000
    assert result.channels == 1
    assert result.dtype == "int16"


def test_audio_preflight_sys_requires_wasapi_loopback() -> None:
    result = preflight_audio_source("SYS", sd_module=OutputOnlyNoWasapiSoundDevice, system_name="Windows")

    assert result.available is False
    assert result.reason == "sys_loopback_device_missing"


def test_audio_preflight_sys_is_windows_only() -> None:
    result = preflight_audio_source("SYS", sd_module=FakeSoundDevice, system_name="Linux")

    assert result.available is False
    assert result.reason == "sys_loopback_windows_only"


def test_audio_preflight_mix_available_when_mic_available() -> None:
    result = preflight_audio_source("MIX", sd_module=FakeSoundDevice, system_name="Linux")

    assert result.available is True
    assert result.reason is None


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


def test_live_cli_lists_audio_sources_without_meeting_or_model(monkeypatch, capsys) -> None:
    cli = load_live_cli()

    class Device:
        def to_dict(self):
            return {"index": 0, "name": "Microphone Array", "hostapi": "Windows WASAPI"}

    monkeypatch.setattr(cli, "list_audio_devices", lambda: [Device()])

    exit_code = cli.main_with_argv(["--list-audio-sources"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["devices"][0]["name"] == "Microphone Array"


def test_live_cli_preflights_source_without_meeting_or_model(monkeypatch, capsys) -> None:
    cli = load_live_cli()
    monkeypatch.setattr(
        cli,
        "preflight_audio_source",
        lambda source: AudioSourcePreflight(source=source, available=False, reason="sounddevice_missing"),
    )

    exit_code = cli.main_with_argv(["--preflight-source", "--source", "SYS"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["source"] == "SYS"
    assert payload["available"] is False
    assert payload["reason"] == "sounddevice_missing"


def test_live_cli_refuses_unavailable_runtime_audio_source(tmp_path: Path, monkeypatch, capsys) -> None:
    cli = load_live_cli()
    meeting_dir = tmp_path / "2026-06-08__live-smoke"
    meeting_dir.mkdir()
    (meeting_dir / "meeting.json").write_text(json.dumps(minimal_meeting(), ensure_ascii=False), encoding="utf-8")
    model_dir = tmp_path / "vosk-model-small-ru-0.22"
    model_dir.mkdir()
    monkeypatch.setattr(
        cli,
        "preflight_audio_source",
        lambda source: AudioSourcePreflight(source=source, available=False, reason="sounddevice_missing"),
    )

    exit_code = cli.main_with_argv(["--meeting-dir", str(meeting_dir), "--model-path", str(model_dir)])

    assert exit_code == 1
    assert "sounddevice_missing" in capsys.readouterr().err


def test_live_cli_refuses_sys_loopback_runtime_until_backend_is_wired(tmp_path: Path, monkeypatch, capsys) -> None:
    cli = load_live_cli()
    meeting_dir = tmp_path / "2026-06-08__live-smoke"
    meeting_dir.mkdir()
    (meeting_dir / "meeting.json").write_text(json.dumps(minimal_meeting(), ensure_ascii=False), encoding="utf-8")
    model_dir = tmp_path / "vosk-model-small-ru-0.22"
    model_dir.mkdir()
    monkeypatch.setattr(
        cli,
        "preflight_audio_source",
        lambda source: AudioSourcePreflight(source=source, available=True),
    )

    exit_code = cli.main_with_argv(["--meeting-dir", str(meeting_dir), "--model-path", str(model_dir), "--source", "SYS"])

    assert exit_code == 1
    assert "SYS loopback capture is detected but not implemented" in capsys.readouterr().err


def test_live_cli_refuses_overwrite_without_force(tmp_path: Path, capsys) -> None:
    cli = load_live_cli()
    meeting_dir = tmp_path / "2026-06-08__live-smoke"
    live_dir = meeting_dir / "transcript" / "live"
    live_dir.mkdir(parents=True)
    (meeting_dir / "meeting.json").write_text(json.dumps(minimal_meeting(), ensure_ascii=False), encoding="utf-8")
    (live_dir / "live_segments.MIC.jsonl").write_text("{}", encoding="utf-8")
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
    monkeypatch.setattr(cli, "preflight_audio_source", lambda source: AudioSourcePreflight(source=source, available=True))

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
    assert meeting["processing_status"] == "processing"
    assert meeting["source"]["derived_tracks"] == ["MIX"]
    assert meeting["artifacts"]["live_segments_mix"] == "transcript/live/live_segments.MIX.jsonl"
    assert meeting["artifacts"]["live_report_mix"] == "transcript/live/live_report.MIX.json"
    assert "transcript/live/live_partials.MIX.jsonl" in meeting["rag"]["no_index_artifacts"]
    assert "transcript/live/live_segments.MIX.jsonl" in meeting["rag"]["no_index_artifacts"]
    assert (meeting_dir / "transcript" / "live" / "live_segments.MIX.jsonl").exists()


def test_live_cli_allows_multiple_sources_without_overwrite(tmp_path: Path, monkeypatch) -> None:
    cli = load_live_cli()
    meeting_dir = tmp_path / "2026-06-08__live-smoke"
    meeting_dir.mkdir()
    meeting_path = meeting_dir / "meeting.json"
    meeting_path.write_text(json.dumps(minimal_meeting(), ensure_ascii=False), encoding="utf-8")
    model_dir = tmp_path / "vosk-model-small-ru-0.22"
    model_dir.mkdir()
    wav_path = tmp_path / "audio_16k_mono.wav"
    wav_path.write_bytes(b"fake")

    def fake_transcribe(config):
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
                        text=f"{config.source} фраза",
                        source=config.source,
                        engine="vosk",
                        model="vosk-model-small-ru-0.22",
                    )
                ],
                "partials": [],
                "metrics": {"duration": 1.0},
            },
        )()

    monkeypatch.setattr(cli, "transcribe_vosk_live", fake_transcribe)

    assert cli.main_with_argv(["--meeting-dir", str(meeting_dir), "--model-path", str(model_dir), "--source", "MIC", "--input-wav", str(wav_path)]) == 0
    assert cli.main_with_argv(["--meeting-dir", str(meeting_dir), "--model-path", str(model_dir), "--source", "SYS", "--input-wav", str(wav_path)]) == 0

    meeting = json.loads(meeting_path.read_text(encoding="utf-8"))
    assert meeting["artifacts"]["live_segments_mic"] == "transcript/live/live_segments.MIC.jsonl"
    assert meeting["artifacts"]["live_segments_sys"] == "transcript/live/live_segments.SYS.jsonl"
    assert sorted(meeting["source"]["audio_tracks"]) == ["MIC", "SYS"]
    assert (meeting_dir / "transcript" / "live" / "live_segments.MIC.jsonl").exists()
    assert (meeting_dir / "transcript" / "live" / "live_segments.SYS.jsonl").exists()


def test_live_cli_passes_silero_vad_config_to_backend(tmp_path: Path, monkeypatch) -> None:
    cli = load_live_cli()
    meeting_dir = tmp_path / "2026-06-08__live-smoke"
    meeting_dir.mkdir()
    meeting_path = meeting_dir / "meeting.json"
    meeting_path.write_text(json.dumps(minimal_meeting(), ensure_ascii=False), encoding="utf-8")
    model_dir = tmp_path / "vosk-model-small-ru-0.22"
    model_dir.mkdir()
    wav_path = tmp_path / "audio_16k_mono.wav"
    wav_path.write_bytes(b"fake")
    seen = {}

    def fake_transcribe(config):
        seen["vad"] = config.vad
        seen["threshold"] = config.silero_vad.threshold
        seen["min_speech_ms"] = config.silero_vad.min_speech_ms
        seen["input_wav"] = config.input_wav
        return type("FakeResult", (), {"segments": [], "partials": [], "metrics": {"duration": 0.0}})()

    monkeypatch.setattr(cli, "transcribe_vosk_live", fake_transcribe)

    exit_code = cli.main_with_argv(
        [
            "--meeting-dir",
            str(meeting_dir),
            "--model-path",
            str(model_dir),
            "--input-wav",
            str(wav_path),
            "--vad",
            "silero",
            "--vad-threshold",
            "0.62",
            "--vad-min-speech-ms",
            "300",
            "--force",
        ]
    )

    assert exit_code == 0
    assert seen == {
        "vad": "silero",
        "threshold": 0.62,
        "min_speech_ms": 300,
        "input_wav": wav_path,
    }


def test_speech_window_overlap_detection() -> None:
    windows = [SpeechWindow(start=1.0, end=2.0), SpeechWindow(start=4.0, end=5.0)]

    assert block_overlaps_speech(0.0, 0.5, windows) is False
    assert block_overlaps_speech(0.5, 1.1, windows) is True
    assert block_overlaps_speech(2.0, 3.0, windows) is False
    assert block_overlaps_speech(4.5, 6.0, windows) is True


def test_vosk_backend_keyboard_interrupt_returns_partial_result(tmp_path: Path, monkeypatch) -> None:
    import meeting_agent.live_transcription.vosk_backend as backend

    model_dir = tmp_path / "vosk-model-small-ru-0.22"
    model_dir.mkdir()

    class FakeModel:
        def __init__(self, _path: str) -> None:
            pass

    class FakeRecognizer:
        def __init__(self, _model, _sample_rate: float) -> None:
            pass

        def SetWords(self, _enabled: bool) -> None:
            pass

        def FinalResult(self) -> str:
            return json.dumps({"text": "финальная фраза"})

    def fake_transcribe_microphone(config, _recognizer, _model_label, segments, partials, _runtime_metrics):
        segments.append(
            LiveSegment(
                segment_id="live-seg-000000",
                segment_index=0,
                start=0.0,
                end=1.0,
                text="накопленная фраза",
                source=config.source,
                engine="vosk",
                model="vosk-model-small-ru-0.22",
            )
        )
        partials.append({"text": "накоп", "source": config.source, "is_final": False})
        raise KeyboardInterrupt

    monkeypatch.setattr(backend, "_load_vosk", lambda: (FakeRecognizer, FakeModel))
    monkeypatch.setattr(backend, "_transcribe_microphone", fake_transcribe_microphone)

    result = transcribe_vosk_live(VoskLiveConfig(model_path=model_dir, source="MIC"))

    assert result.metrics["interrupted"] is True
    assert [segment.text for segment in result.segments] == ["накопленная фраза", "финальная фраза"]
    assert result.partials == [{"text": "накоп", "source": "MIC", "is_final": False}]


def test_vosk_backend_reports_microphone_runtime_metrics(tmp_path: Path, monkeypatch) -> None:
    import meeting_agent.live_transcription.vosk_backend as backend

    model_dir = tmp_path / "vosk-model-small-ru-0.22"
    model_dir.mkdir()

    class FakeModel:
        def __init__(self, _path: str) -> None:
            pass

    class FakeRecognizer:
        def __init__(self, _model, _sample_rate: float) -> None:
            pass

        def SetWords(self, _enabled: bool) -> None:
            pass

        def FinalResult(self) -> str:
            return json.dumps({"text": ""})

    def fake_transcribe_microphone(_config, _recognizer, _model_label, _segments, _partials, runtime_metrics):
        runtime_metrics["input_status_events"] = 2
        runtime_metrics["queue_timeouts"] = 3
        return 0.0

    monkeypatch.setattr(backend, "_load_vosk", lambda: (FakeRecognizer, FakeModel))
    monkeypatch.setattr(backend, "_transcribe_microphone", fake_transcribe_microphone)

    result = transcribe_vosk_live(VoskLiveConfig(model_path=model_dir, source="MIC"))

    assert result.metrics["input_status_events"] == 2
    assert result.metrics["queue_timeouts"] == 3
