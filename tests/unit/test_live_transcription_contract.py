from __future__ import annotations

import importlib.util
import json
import sys
import wave
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from meeting_agent.live_transcription import (  # noqa: E402
    AudioSourcePreflight,
    LiveSegment,
    LiveSessionReport,
    preflight_audio_source,
    write_live_artifacts,
)
from meeting_agent.live_transcription.audio_capture import list_audio_devices  # noqa: E402
from meeting_agent.live_transcription.vad import SpeechWindow, block_overlaps_speech  # noqa: E402
from meeting_agent.live_transcription.vosk_backend import (  # noqa: E402
    VoskBackendError,
    VoskLiveConfig,
    transcribe_vosk_live,
)


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


@pytest.mark.parametrize("capacity", [0, 1_025])
def test_vosk_backend_rejects_unbounded_mic_queue_capacity(
    tmp_path: Path,
    capacity: int,
) -> None:
    with pytest.raises(VoskBackendError, match="mic-queue-max-blocks"):
        transcribe_vosk_live(
            VoskLiveConfig(
                model_path=tmp_path,
                mic_queue_max_blocks=capacity,
            )
        )


class FakeSoundDevice:
    stream_opened = False
    format_checked = False

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
                "default_samplerate": 48_000,
            },
            {
                "name": "Speakers",
                "hostapi": 0,
                "max_input_channels": 0,
                "max_output_channels": 2,
                "default_samplerate": 48_000,
            },
        ]

    @classmethod
    def check_input_settings(cls, **settings):
        cls.format_checked = True
        assert settings == {
            "device": None,
            "channels": 1,
            "dtype": "int16",
            "samplerate": 16_000,
        }

    @classmethod
    def RawInputStream(cls, *args, **kwargs):
        cls.stream_opened = True
        raise AssertionError("preflight must not open an audio stream")


class MicrophoneOnlySoundDevice:
    @staticmethod
    def query_hostapis():
        return [{"name": "MME"}]

    @staticmethod
    def query_devices():
        return [
            {
                "name": "Microphone Array",
                "hostapi": 0,
                "max_input_channels": 2,
                "max_output_channels": 0,
            }
        ]


class FakeLoopbackManager:
    terminated = False
    stream_opened = False

    @staticmethod
    def _device():
        return {
            "index": 19,
            "name": "Synthetic speakers [Loopback]",
            "maxInputChannels": 2,
            "maxOutputChannels": 0,
            "defaultSampleRate": 48_000.0,
            "isLoopbackDevice": True,
        }

    def get_loopback_device_info_generator(self):
        yield self._device()

    def get_default_wasapi_loopback(self):
        return self._device()

    def open(self, **_kwargs):
        type(self).stream_opened = True
        raise AssertionError("preflight must not open a loopback stream")

    def terminate(self):
        type(self).terminated = True


class FakePyAudioModule:
    paInt16 = 8
    PyAudio = FakeLoopbackManager


def test_audio_device_listing_marks_only_wasapi_output_as_loopback_candidate() -> None:
    devices = list_audio_devices(sd_module=FakeSoundDevice)

    assert [device.name for device in devices] == ["Microphone Array", "Speakers"]
    assert devices[0].loopback_candidate is False
    assert devices[1].loopback_candidate is True
    assert FakeSoundDevice.stream_opened is False


def test_audio_device_listing_does_not_alias_invalid_hostapi_to_zero() -> None:
    class InvalidHostapiSoundDevice:
        @staticmethod
        def query_hostapis():
            return [{"name": "Windows WASAPI"}]

        @staticmethod
        def query_devices():
            return [
                {
                    "name": "Unassigned output",
                    "hostapi": -1,
                    "max_input_channels": 0,
                    "max_output_channels": 2,
                }
            ]

    devices = list_audio_devices(sd_module=InvalidHostapiSoundDevice)

    assert devices[0].hostapi == ""
    assert devices[0].loopback_candidate is False


def test_audio_device_listing_handles_optional_runtime_query_failure() -> None:
    class BrokenSoundDevice:
        @staticmethod
        def query_hostapis():
            raise OSError("PortAudio unavailable")

        @staticmethod
        def query_devices():
            raise OSError("PortAudio unavailable")

    assert list_audio_devices(sd_module=BrokenSoundDevice) == []


def test_audio_preflight_reports_sounddevice_missing() -> None:
    result = preflight_audio_source("MIC", sd_module=False)

    assert result.available is False
    assert result.device_available is False
    assert result.capture_supported is False
    assert result.reason == "sounddevice_missing"


def test_audio_preflight_mic_is_runnable_without_opening_stream() -> None:
    FakeSoundDevice.stream_opened = False
    FakeSoundDevice.format_checked = False

    result = preflight_audio_source(
        "MIC", sd_module=FakeSoundDevice, system_name="Windows"
    )

    assert result.available is True
    assert result.device_available is True
    assert result.capture_supported is True
    assert result.reason is None
    assert result.devices[0].name == "Microphone Array"
    assert result.sample_rate == 16_000
    assert result.channels == 1
    assert result.dtype == "int16"
    assert FakeSoundDevice.stream_opened is False
    assert FakeSoundDevice.format_checked is True


def test_audio_preflight_mic_rejects_unsupported_capture_format() -> None:
    class UnsupportedFormatSoundDevice(FakeSoundDevice):
        @staticmethod
        def check_input_settings(**_settings):
            raise ValueError("unsupported sample rate")

    result = preflight_audio_source(
        "MIC", sd_module=UnsupportedFormatSoundDevice, system_name="Windows"
    )

    assert result.available is False
    assert result.device_available is True
    assert result.capture_supported is False
    assert result.reason == "mic_capture_format_unsupported"


def test_audio_preflight_mic_checks_the_selected_device_index() -> None:
    class SelectedDeviceSoundDevice(FakeSoundDevice):
        checked_device = None

        @classmethod
        def check_input_settings(cls, **settings):
            cls.checked_device = settings["device"]

    result = preflight_audio_source(
        "MIC",
        sd_module=SelectedDeviceSoundDevice,
        system_name="Windows",
        audio_device_index=0,
    )

    assert result.available is True
    assert SelectedDeviceSoundDevice.checked_device == 0


def test_audio_preflight_sys_is_runnable_with_wasapi_loopback_backend() -> None:
    FakeLoopbackManager.stream_opened = False
    FakeLoopbackManager.terminated = False

    result = preflight_audio_source(
        "SYS", pyaudio_module=FakePyAudioModule, system_name="Windows"
    )

    assert result.available is True
    assert result.device_available is True
    assert result.capture_supported is True
    assert result.reason is None
    assert [device.name for device in result.devices] == [
        "Synthetic speakers [Loopback]"
    ]
    assert result.devices[0].default_samplerate == 48_000.0
    assert FakeLoopbackManager.stream_opened is False
    assert FakeLoopbackManager.terminated is True


def test_audio_preflight_sys_requires_loopback_backend() -> None:
    result = preflight_audio_source(
        "SYS", pyaudio_module=False, system_name="Windows"
    )

    assert result.available is False
    assert result.device_available is False
    assert result.reason == "sys_loopback_backend_missing"


def test_audio_preflight_sys_is_windows_only() -> None:
    result = preflight_audio_source(
        "SYS", pyaudio_module=FakePyAudioModule, system_name="Linux"
    )

    assert result.available is False
    assert result.reason == "sys_loopback_windows_only"


def test_audio_preflight_sys_rejects_unknown_explicit_device_index() -> None:
    result = preflight_audio_source(
        "SYS",
        pyaudio_module=FakePyAudioModule,
        system_name="Windows",
        audio_device_index=999,
    )

    assert result.available is False
    assert result.device_available is False
    assert result.reason == "sys_loopback_device_not_found"


def test_audio_preflight_mix_never_mislabels_mic_only_capture() -> None:
    result = preflight_audio_source(
        "MIX",
        sd_module=MicrophoneOnlySoundDevice,
        pyaudio_module=False,
        system_name="Windows",
    )

    assert result.available is False
    assert result.device_available is False
    assert result.capture_supported is False
    assert result.reason == "mix_source_device_missing"


def test_audio_preflight_mix_requires_backend_after_both_devices_exist() -> None:
    result = preflight_audio_source(
        "MIX",
        sd_module=FakeSoundDevice,
        pyaudio_module=FakePyAudioModule,
        system_name="Windows",
    )

    assert result.available is False
    assert result.device_available is True
    assert result.capture_supported is False
    assert result.reason == "mix_capture_not_implemented"


def test_audio_preflight_mix_preserves_colliding_backend_device_indexes() -> None:
    class CollidingLoopbackManager(FakeLoopbackManager):
        @staticmethod
        def _device():
            return {**FakeLoopbackManager._device(), "index": 0}

    class CollidingPyAudioModule:
        paInt16 = 8
        PyAudio = CollidingLoopbackManager

    result = preflight_audio_source(
        "MIX",
        sd_module=FakeSoundDevice,
        pyaudio_module=CollidingPyAudioModule,
        system_name="Windows",
    )

    assert result.reason == "mix_capture_not_implemented"
    assert [(device.index, device.hostapi) for device in result.devices] == [
        (0, "Windows WASAPI"),
        (0, "Windows WASAPI loopback"),
    ]


def test_audio_preflight_rejects_unknown_source() -> None:
    result = preflight_audio_source("camera", sd_module=FakeSoundDevice)

    assert result.available is False
    assert result.reason == "unsupported_source"


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


def test_live_cli_lists_devices_and_source_readiness_without_meeting(
    monkeypatch, capsys
) -> None:
    cli = load_live_cli()

    class Device:
        def to_dict(self):
            return {"index": 0, "name": "Synthetic microphone"}

    monkeypatch.setattr(cli, "list_audio_devices", lambda: [Device()])
    monkeypatch.setattr(
        cli,
        "preflight_audio_source",
        lambda source, **_kwargs: AudioSourcePreflight(
            source=source,
            available=source == "MIC",
            device_available=source == "MIC",
            capture_supported=source == "MIC",
            reason=None if source == "MIC" else "not_implemented",
        ),
    )

    exit_code = cli.main_with_argv(["--list-audio-sources"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["devices"] == [{"index": 0, "name": "Synthetic microphone"}]
    assert [item["source"] for item in payload["sources"]] == ["MIC", "MIX", "SYS"]
    assert next(item for item in payload["sources"] if item["source"] == "MIC")[
        "available"
    ] is True


def test_live_cli_preflight_exit_code_is_automation_friendly(monkeypatch, capsys) -> None:
    cli = load_live_cli()
    monkeypatch.setattr(
        cli,
        "preflight_audio_source",
        lambda source, **_kwargs: AudioSourcePreflight(
            source=source,
            available=False,
            device_available=True,
            capture_supported=False,
            reason="sys_loopback_capture_not_implemented",
        ),
    )

    exit_code = cli.main_with_argv(["--preflight-source", "--source", "SYS"])

    assert exit_code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["source"] == "SYS"
    assert payload["available"] is False
    assert payload["device_available"] is True
    assert payload["capture_supported"] is False


def test_live_cli_preflight_returns_zero_for_runnable_mic(monkeypatch, capsys) -> None:
    cli = load_live_cli()
    monkeypatch.setattr(
        cli,
        "preflight_audio_source",
        lambda source, **_kwargs: AudioSourcePreflight(
            source=source,
            available=True,
            device_available=True,
            capture_supported=True,
        ),
    )

    exit_code = cli.main_with_argv(["--preflight-source", "--source", "MIC"])

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["available"] is True


def test_live_cli_discovery_modes_are_mutually_exclusive() -> None:
    cli = load_live_cli()

    with pytest.raises(SystemExit) as exc:
        cli.parse_args(["--list-audio-sources", "--preflight-source"])

    assert exc.value.code == 2


def test_live_cli_rejects_unbounded_partials() -> None:
    cli = load_live_cli()

    with pytest.raises(SystemExit) as exc:
        cli.parse_args(["--list-audio-sources", "--partials-max", "0"])

    assert exc.value.code == 2


def test_live_cli_blocks_unavailable_source_without_mutating_meeting(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    cli = load_live_cli()
    meeting_dir = tmp_path / "2026-06-08__live-smoke"
    meeting_dir.mkdir()
    meeting_path = meeting_dir / "meeting.json"
    original = minimal_meeting()
    meeting_path.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")
    model_dir = tmp_path / "vosk-model-small-ru-0.22"
    model_dir.mkdir()
    monkeypatch.setattr(
        cli,
        "preflight_audio_source",
        lambda source, **_kwargs: AudioSourcePreflight(
            source=source,
            available=False,
            device_available=True,
            capture_supported=False,
            reason="mix_capture_not_implemented",
        ),
    )
    monkeypatch.setattr(
        cli,
        "transcribe_vosk_live",
        lambda _config: pytest.fail("blocked source must not start capture"),
    )

    exit_code = cli.main_with_argv(
        [
            "--meeting-dir",
            str(meeting_dir),
            "--model-path",
            str(model_dir),
            "--source",
            "MIX",
        ]
    )

    assert exit_code == 1
    assert "mix_capture_not_implemented" in capsys.readouterr().err
    assert json.loads(meeting_path.read_text(encoding="utf-8")) == original


def test_live_cli_runnable_mic_preflight_starts_backend(tmp_path: Path, monkeypatch) -> None:
    cli = load_live_cli()
    meeting_dir = tmp_path / "2026-06-08__live-smoke"
    meeting_dir.mkdir()
    (meeting_dir / "meeting.json").write_text(
        json.dumps(minimal_meeting(), ensure_ascii=False), encoding="utf-8"
    )
    model_dir = tmp_path / "vosk-model-small-ru-0.22"
    model_dir.mkdir()
    seen: dict[str, object] = {}

    def fake_preflight(source, **kwargs):
        seen["preflight_source"] = source
        seen["preflight_device_index"] = kwargs.get("audio_device_index")
        return AudioSourcePreflight(
            source=source,
            available=True,
            device_available=True,
            capture_supported=True,
        )

    monkeypatch.setattr(cli, "preflight_audio_source", fake_preflight)

    def fake_transcribe(config):
        seen["backend_source"] = config.source
        seen["backend_device_index"] = config.audio_device_index
        assert config.audio_archive_path is not None
        config.audio_archive_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(config.audio_archive_path), "wb") as archive:
            archive.setnchannels(1)
            archive.setsampwidth(2)
            archive.setframerate(config.sample_rate)
            archive.writeframes(b"\x00\x00" * 160)
        return type(
            "FakeResult",
            (),
            {
                "segments": [],
                "partials": [],
                "metrics": {"duration": 0.01},
                "audio_archive_path": config.audio_archive_path,
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
            "MIC",
            "--audio-device-index",
            "0",
            "--force",
        ]
    )

    assert exit_code == 0
    assert seen == {
        "preflight_source": "MIC",
        "preflight_device_index": 0,
        "backend_source": "MIC",
        "backend_device_index": 0,
    }
    meeting = json.loads((meeting_dir / "meeting.json").read_text(encoding="utf-8"))
    assert meeting["artifacts"]["live_audio_mic"] == "source/live_audio.MIC.wav"
    assert meeting["source"]["media_files"] == [
        {
            "path": "source/live_audio.MIC.wav",
            "media_type": "audio",
            "duration_seconds": 0.01,
        }
    ]
    assert "source/live_audio.MIC.wav" in meeting["rag"]["no_index_artifacts"]


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
    wav_path = tmp_path / "audio_16k_mono.wav"
    wav_path.write_bytes(b"fake")

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
            "--input-wav",
            str(wav_path),
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

    assert cli.main_with_argv(
        [
            "--meeting-dir",
            str(meeting_dir),
            "--model-path",
            str(model_dir),
            "--source",
            "MIC",
            "--input-wav",
            str(wav_path),
        ]
    ) == 0
    assert cli.main_with_argv(
        [
            "--meeting-dir",
            str(meeting_dir),
            "--model-path",
            str(model_dir),
            "--source",
            "SYS",
            "--input-wav",
            str(wav_path),
        ]
    ) == 0

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
        seen["mic_queue_max_blocks"] = config.mic_queue_max_blocks
        seen["partials_max"] = config.partials_max
        seen["input_wav"] = config.input_wav
        return type(
            "FakeResult",
            (),
            {
                "segments": [],
                "partials": [],
                "metrics": {
                    "duration": 0.0,
                    "vad_warnings": ["vad_no_speech_detected"],
                    "mic_queue_dropped_frames": 512,
                    "input_status_events": 1,
                },
            },
        )()

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
            "--mic-queue-max-blocks",
            "7",
            "--partials-max",
            "9",
            "--force",
        ]
    )

    assert exit_code == 0
    assert seen == {
        "vad": "silero",
        "threshold": 0.62,
        "min_speech_ms": 300,
        "mic_queue_max_blocks": 7,
        "partials_max": 9,
        "input_wav": wav_path,
    }
    report = json.loads(
        (
            meeting_dir
            / "transcript"
            / "live"
            / "live_report.MIC.json"
        ).read_text(encoding="utf-8")
    )
    assert report["warnings"] == [
        "no_final_segments",
        "vad_no_speech_detected",
        "mic_audio_dropped",
        "mic_input_status_events",
    ]


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

    def fake_transcribe_microphone(
        config,
        _recognizer,
        _model_label,
        segments,
        partials,
        _runtime_metrics,
        _timeline,
    ):
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

    def fake_transcribe_microphone(
        _config,
        _recognizer,
        _model_label,
        _segments,
        _partials,
        runtime_metrics,
        _timeline,
    ):
        runtime_metrics["input_status_events"] = 2
        runtime_metrics["queue_timeouts"] = 3
        return 0.0

    monkeypatch.setattr(backend, "_load_vosk", lambda: (FakeRecognizer, FakeModel))
    monkeypatch.setattr(backend, "_transcribe_microphone", fake_transcribe_microphone)

    result = transcribe_vosk_live(VoskLiveConfig(model_path=model_dir, source="MIC"))

    assert result.metrics["input_status_events"] == 2
    assert result.metrics["queue_timeouts"] == 3


def test_vosk_wav_metrics_do_not_expose_input_path(tmp_path: Path, monkeypatch) -> None:
    import meeting_agent.live_transcription.vosk_backend as backend

    model_dir = tmp_path / "vosk-model-small-ru-0.22"
    model_dir.mkdir()
    wav_path = tmp_path / "private" / "source.wav"
    wav_path.parent.mkdir()
    with wave.open(str(wav_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16_000)
        wav.writeframes(b"\x00\x00" * 160)

    class FakeModel:
        def __init__(self, _path: str) -> None:
            pass

    class FakeRecognizer:
        def __init__(self, _model, _sample_rate: float) -> None:
            pass

        def SetWords(self, _enabled: bool) -> None:
            pass

        def AcceptWaveform(self, _block: bytes) -> bool:
            return False

        def PartialResult(self) -> str:
            return '{"partial": ""}'

        def FinalResult(self) -> str:
            return '{"text": ""}'

    monkeypatch.setattr(backend, "_load_vosk", lambda: (FakeRecognizer, FakeModel))

    result = transcribe_vosk_live(
        VoskLiveConfig(model_path=model_dir, source="SYS", input_wav=wav_path)
    )

    assert result.metrics["input_mode"] == "wav"
    assert str(wav_path) not in repr(result.metrics)
