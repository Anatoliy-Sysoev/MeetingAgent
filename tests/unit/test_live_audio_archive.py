from __future__ import annotations

import json
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

from meeting_agent.live_transcription.audio_archive import (
    AtomicPcm16WaveArchive,
    LiveAudioArchiveError,
)
from meeting_agent.live_transcription.vosk_backend import (
    _CanonicalStreamConsumer,
    _fill_microphone_gap,
    VoskLiveConfig,
    transcribe_vosk_live,
)


def test_atomic_archive_writes_valid_pcm16_mono_wav(tmp_path: Path) -> None:
    target = tmp_path / "source" / "live_audio.MIC.wav"
    writer = AtomicPcm16WaveArchive(
        target,
        sample_rate=16_000,
        min_free_bytes=0,
    )
    writer.open()
    writer.write(b"\x01\x00" * 1_600)
    result = writer.commit()

    assert result.path == target
    assert result.frames == 1_600
    assert result.duration_seconds == 0.1
    assert list(target.parent.glob(f".{target.name}.*.tmp")) == []
    with wave.open(str(target), "rb") as wav:
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        assert wav.getframerate() == 16_000
        assert wav.getnframes() == 1_600
        assert wav.readframes(1) == b"\x01\x00"


def test_archive_abort_removes_temp_and_preserves_existing_target(tmp_path: Path) -> None:
    target = tmp_path / "live_audio.SYS.wav"
    target.write_bytes(b"existing")
    writer = AtomicPcm16WaveArchive(
        target,
        sample_rate=16_000,
        min_free_bytes=0,
    )
    writer.open()
    writer.write(b"\x00\x00" * 10)
    writer.abort()

    assert target.read_bytes() == b"existing"
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_archive_rejects_size_overflow_without_publishing(tmp_path: Path) -> None:
    target = tmp_path / "live_audio.MIC.wav"
    writer = AtomicPcm16WaveArchive(
        target,
        sample_rate=16_000,
        max_bytes=8,
        min_free_bytes=0,
    )
    writer.open()
    with pytest.raises(LiveAudioArchiveError, match="size limit exceeded"):
        writer.write(b"\x00\x00" * 5)
    writer.abort()

    assert not target.exists()
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_archive_fails_before_temp_when_free_space_is_insufficient(tmp_path: Path) -> None:
    target = tmp_path / "live_audio.MIC.wav"
    writer = AtomicPcm16WaveArchive(
        target,
        sample_rate=16_000,
        min_free_bytes=1_000,
        disk_usage=lambda _path: SimpleNamespace(free=900),
    )

    with pytest.raises(LiveAudioArchiveError, match="insufficient free space"):
        writer.open()

    assert not target.exists()
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_canonical_archive_keeps_recovered_wall_clock_gaps(tmp_path: Path) -> None:
    archived = bytearray()

    class FakeRecognizer:
        def AcceptWaveform(self, _block: bytes) -> bool:
            return False

    metrics = {"mic_queue_gap_filled_frames": 0}
    consumer = _CanonicalStreamConsumer(
        config=VoskLiveConfig(
            model_path=tmp_path,
            source="MIC",
            save_partials=False,
            audio_sink=archived.extend,
        ),
        recognizer=FakeRecognizer(),
        model_label="fake",
        segments=[],
        partials=[],
        timeline=None,
        runtime_metrics=metrics,
    )

    _fill_microphone_gap(
        consumer,
        4,
        silence_chunk_frames=2,
        runtime_metrics=metrics,
    )
    consumer.consume(b"\x03\x00" * 2)

    assert bytes(archived) == (b"\x00\x00" * 4) + (b"\x03\x00" * 2)
    assert metrics["mic_queue_gap_filled_frames"] == 4


def test_vosk_capture_commits_archive_and_reports_path_free_metrics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import meeting_agent.live_transcription.vosk_backend as backend

    model_dir = tmp_path / "model"
    model_dir.mkdir()
    target = tmp_path / "private" / "live_audio.MIC.wav"

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

    def fake_capture(config, *_args):
        assert config.audio_sink is not None
        config.audio_sink(b"\x02\x00" * 3_200)
        return 0.2

    monkeypatch.setattr(backend, "_load_vosk", lambda: (FakeRecognizer, FakeModel))
    monkeypatch.setattr(backend, "_transcribe_microphone", fake_capture)

    result = transcribe_vosk_live(
        VoskLiveConfig(
            model_path=model_dir,
            source="MIC",
            audio_archive_path=target,
            audio_archive_min_free_bytes=0,
        )
    )

    assert result.audio_archive_path == target
    assert result.metrics["audio_archive_frames"] == 3_200
    assert result.metrics["audio_archive_duration_seconds"] == 0.2
    assert str(target) not in repr(result.metrics)
    with wave.open(str(target), "rb") as wav:
        assert wav.getnframes() == 3_200


def test_vosk_capture_failure_removes_archive_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import meeting_agent.live_transcription.vosk_backend as backend

    model_dir = tmp_path / "model"
    model_dir.mkdir()
    target = tmp_path / "live_audio.SYS.wav"

    class FakeModel:
        def __init__(self, _path: str) -> None:
            pass

    class FakeRecognizer:
        def __init__(self, _model, _sample_rate: float) -> None:
            pass

        def SetWords(self, _enabled: bool) -> None:
            pass

    def fail_capture(config, *_args):
        assert config.audio_sink is not None
        config.audio_sink(b"\x00\x00" * 100)
        raise RuntimeError("capture failed")

    monkeypatch.setattr(backend, "_load_vosk", lambda: (FakeRecognizer, FakeModel))
    monkeypatch.setattr(backend, "_transcribe_microphone", fail_capture)

    with pytest.raises(RuntimeError, match="capture failed"):
        transcribe_vosk_live(
            VoskLiveConfig(
                model_path=model_dir,
                source="MIC",
                audio_archive_path=target,
                audio_archive_min_free_bytes=0,
            )
        )

    assert not target.exists()
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_vosk_rejects_duration_larger_than_archive_before_model_load(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import meeting_agent.live_transcription.vosk_backend as backend

    model_dir = tmp_path / "model"
    model_dir.mkdir()
    model_loaded = False

    def unexpected_model_load():
        nonlocal model_loaded
        model_loaded = True
        raise AssertionError("model must not load")

    monkeypatch.setattr(backend, "_load_vosk", unexpected_model_load)

    with pytest.raises(
        backend.VoskBackendError,
        match="duration exceeds the audio archive size limit",
    ):
        transcribe_vosk_live(
            VoskLiveConfig(
                model_path=model_dir,
                source="MIC",
                duration_sec=2.0,
                audio_archive_path=tmp_path / "live.wav",
                audio_archive_max_bytes=32_000,
                audio_archive_min_free_bytes=0,
            )
        )

    assert model_loaded is False
