from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pytest

from meeting_agent.live_transcription import vosk_backend
from meeting_agent.live_transcription.vosk_backend import VoskLiveConfig
from meeting_agent.live_transcription.wasapi_loopback import (
    LoopbackDevice,
    OpenLoopbackStream,
    Pcm16MonoResampler,
    WasapiLoopbackError,
    discover_wasapi_loopbacks,
    open_wasapi_loopback_stream,
)


def _loopback_info(index: int = 19) -> dict:
    return {
        "index": index,
        "name": "Synthetic speakers [Loopback]",
        "maxInputChannels": 2,
        "maxOutputChannels": 0,
        "defaultSampleRate": 48_000.0,
        "isLoopbackDevice": True,
    }


class FakeStream:
    def __init__(self, blocks: list[bytes] | None = None) -> None:
        self.blocks = list(blocks or [])
        self.stopped = False
        self.closed = False
        self.read_calls: list[tuple[int, bool]] = []

    def read(self, frames: int, *, exception_on_overflow: bool) -> bytes:
        self.read_calls.append((frames, exception_on_overflow))
        if not self.blocks:
            raise AssertionError("unexpected loopback read")
        return self.blocks.pop(0)

    def stop_stream(self) -> None:
        self.stopped = True

    def close(self) -> None:
        self.closed = True


class FakeManager:
    instances: list["FakeManager"] = []

    def __init__(self) -> None:
        self.terminated = False
        self.open_calls: list[dict] = []
        self.stream = FakeStream()
        type(self).instances.append(self)

    def get_loopback_device_info_generator(self):
        yield _loopback_info()
        yield {**_loopback_info(20), "name": "  Secondary   output  "}
        yield {**_loopback_info(21), "isLoopbackDevice": False}

    def get_default_wasapi_loopback(self):
        return _loopback_info()

    def get_device_info_by_index(self, index: int):
        if index == 20:
            return {**_loopback_info(20), "name": "Secondary output"}
        if index == 7:
            return {**_loopback_info(7), "isLoopbackDevice": False}
        raise OSError("missing device")

    def open(self, **kwargs):
        self.open_calls.append(kwargs)
        return self.stream

    def terminate(self) -> None:
        self.terminated = True


class FakePyAudio:
    paInt16 = 8
    PyAudio = FakeManager


def test_discovery_lists_only_valid_loopbacks_and_closes_manager() -> None:
    FakeManager.instances.clear()

    discovery = discover_wasapi_loopbacks(pyaudio_module=FakePyAudio)

    assert discovery.backend_available is True
    assert discovery.default_device_index == 19
    assert [device.index for device in discovery.devices] == [19, 20]
    assert discovery.devices[1].name == "Secondary output"
    assert FakeManager.instances[-1].open_calls == []
    assert FakeManager.instances[-1].terminated is True


def test_discovery_reports_missing_optional_backend() -> None:
    discovery = discover_wasapi_loopbacks(pyaudio_module=False)

    assert discovery.backend_available is False
    assert discovery.devices == []
    assert discovery.reason == "sys_loopback_backend_missing"


def test_discovery_normalizes_native_failure_and_closes_manager() -> None:
    class BrokenDiscoveryManager(FakeManager):
        def get_loopback_device_info_generator(self):
            raise OSError("private native backend detail")

    class BrokenDiscoveryPyAudio:
        paInt16 = 8
        PyAudio = BrokenDiscoveryManager

    BrokenDiscoveryManager.instances.clear()
    discovery = discover_wasapi_loopbacks(
        pyaudio_module=BrokenDiscoveryPyAudio,
    )

    assert discovery.backend_available is True
    assert discovery.devices == []
    assert discovery.reason == "sys_loopback_discovery_failed"
    assert BrokenDiscoveryManager.instances[-1].terminated is True


def test_open_loopback_stream_uses_native_format_and_always_cleans_up() -> None:
    FakeManager.instances.clear()

    with open_wasapi_loopback_stream(
        device_index=20,
        block_ms=100,
        pyaudio_module=FakePyAudio,
    ) as opened:
        assert opened.device.index == 20
        stream = opened.stream

    manager = FakeManager.instances[-1]
    assert manager.open_calls == [
        {
            "format": 8,
            "channels": 2,
            "rate": 48_000,
            "input": True,
            "input_device_index": 20,
            "frames_per_buffer": 4_800,
        }
    ]
    assert stream.stopped is True
    assert stream.closed is True
    assert manager.terminated is True


def test_open_loopback_stream_rejects_non_loopback_input() -> None:
    FakeManager.instances.clear()

    with pytest.raises(WasapiLoopbackError, match="not a WASAPI loopback"):
        with open_wasapi_loopback_stream(
            device_index=7,
            block_ms=100,
            pyaudio_module=FakePyAudio,
        ):
            pytest.fail("invalid device must not open")

    assert FakeManager.instances[-1].open_calls == []
    assert FakeManager.instances[-1].terminated is True


def test_open_loopback_stream_normalizes_open_failure_and_closes_manager() -> None:
    class BrokenOpenManager(FakeManager):
        def open(self, **kwargs):
            self.open_calls.append(kwargs)
            raise OSError("private native open detail")

    class BrokenOpenPyAudio:
        paInt16 = 8
        PyAudio = BrokenOpenManager

    BrokenOpenManager.instances.clear()

    with pytest.raises(WasapiLoopbackError, match="stream failed to open"):
        with open_wasapi_loopback_stream(
            device_index=None,
            block_ms=100,
            pyaudio_module=BrokenOpenPyAudio,
        ):
            pytest.fail("failed stream must not yield")

    assert BrokenOpenManager.instances[-1].terminated is True


class PassthroughResampleStream:
    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs
        self.last_values: list[bool] = []

    def resample_chunk(self, data, *, last: bool = False):
        self.last_values.append(last)
        return data

    def num_clips(self) -> int:
        return 0


class FakeSoxr:
    ResampleStream = PassthroughResampleStream


def test_pcm_converter_downmixes_stereo_and_finalizes_once() -> None:
    converter = Pcm16MonoResampler(
        input_rate=48_000,
        input_channels=2,
        output_rate=16_000,
        soxr_module=FakeSoxr,
    )
    stereo = np.asarray([[1000, -1000], [3000, 1000]], dtype="<i2").tobytes()

    output = np.frombuffer(converter.convert(stereo), dtype="<i2").tolist()
    flushed = converter.flush()

    assert output == [0, 2000]
    assert flushed == b""
    assert converter.input_frames == 2
    assert converter.output_frames == 2
    assert converter.clips == 0
    with pytest.raises(WasapiLoopbackError, match="already finalized"):
        converter.flush()


def test_pcm_converter_rejects_incomplete_native_frame() -> None:
    converter = Pcm16MonoResampler(
        input_rate=44_100,
        input_channels=2,
        output_rate=16_000,
        soxr_module=FakeSoxr,
    )

    with pytest.raises(WasapiLoopbackError, match="incomplete PCM frame"):
        converter.convert(b"\x00\x01")


def test_pcm_converter_rejects_non_pcm_native_result() -> None:
    converter = Pcm16MonoResampler(
        input_rate=48_000,
        input_channels=2,
        output_rate=16_000,
        soxr_module=FakeSoxr,
    )

    with pytest.raises(WasapiLoopbackError, match="non-PCM"):
        converter.convert(None)  # type: ignore[arg-type]


def test_vosk_system_capture_uses_canonical_frames_and_path_free_metrics(
    tmp_path: Path, monkeypatch
) -> None:
    native_block = np.zeros((480, 2), dtype="<i2").tobytes()
    fake_stream = FakeStream([native_block, native_block])

    @contextmanager
    def fake_open(**_kwargs):
        yield OpenLoopbackStream(
            stream=fake_stream,
            device=LoopbackDevice(
                index=19,
                name="Private device name",
                channels=2,
                sample_rate=48_000,
            ),
        )

    class FakeConverter:
        def __init__(self, **_kwargs) -> None:
            self.input_frames = 0
            self.output_frames = 0
            self.clips = 0

        def convert(self, block: bytes) -> bytes:
            self.input_frames += len(block) // 4
            self.output_frames += 160
            return b"\x00\x00" * 160

        def flush(self) -> bytes:
            return b""

    class Recognizer:
        def AcceptWaveform(self, _block: bytes) -> bool:
            return False

        def PartialResult(self) -> str:
            return '{"partial": ""}'

    monkeypatch.setattr(vosk_backend, "open_wasapi_loopback_stream", fake_open)
    monkeypatch.setattr(vosk_backend, "Pcm16MonoResampler", FakeConverter)
    metrics: dict = {}

    duration = vosk_backend._transcribe_system_loopback(
        VoskLiveConfig(
            model_path=tmp_path,
            source="SYS",
            sample_rate=16_000,
            block_ms=10,
            duration_sec=0.02,
            audio_device_index=19,
        ),
        Recognizer(),
        "synthetic-vosk",
        [],
        [],
        metrics,
    )

    assert duration == pytest.approx(0.02)
    assert fake_stream.read_calls == [(480, False), (480, False)]
    assert metrics == {
        "capture_backend": "pyaudiowpatch",
        "input_device_index": 19,
        "input_sample_rate": 48_000,
        "input_channels": 2,
        "input_dtype": "int16",
        "output_sample_rate": 16_000,
        "output_channels": 1,
        "output_dtype": "int16",
        "resampler": "soxr_hq",
        "input_frames": 960,
        "output_frames": 320,
        "resampler_clips": 0,
        "read_errors": 0,
        "interrupted": False,
    }
    assert "Private device name" not in repr(metrics)


def test_vosk_system_capture_preserves_read_error_without_flushing(
    tmp_path: Path, monkeypatch
) -> None:
    class BrokenReadStream:
        def read(self, _frames: int, *, exception_on_overflow: bool) -> bytes:
            assert exception_on_overflow is False
            raise OSError("private native read detail")

    @contextmanager
    def fake_open(**_kwargs):
        yield OpenLoopbackStream(
            stream=BrokenReadStream(),
            device=LoopbackDevice(
                index=19,
                name="Private device name",
                channels=2,
                sample_rate=48_000,
            ),
        )

    class FakeConverter:
        instances: list["FakeConverter"] = []

        def __init__(self, **_kwargs) -> None:
            self.input_frames = 0
            self.clips = 0
            self.flushed = False
            type(self).instances.append(self)

        def convert(self, _block: bytes) -> bytes:
            pytest.fail("failed read must not reach conversion")

        def flush(self) -> bytes:
            self.flushed = True
            return b""

    monkeypatch.setattr(vosk_backend, "open_wasapi_loopback_stream", fake_open)
    monkeypatch.setattr(vosk_backend, "Pcm16MonoResampler", FakeConverter)
    metrics: dict = {}

    with pytest.raises(WasapiLoopbackError, match="stream read failed") as exc:
        vosk_backend._transcribe_system_loopback(
            VoskLiveConfig(
                model_path=tmp_path,
                source="SYS",
                sample_rate=16_000,
                block_ms=10,
                duration_sec=0.02,
            ),
            object(),
            "synthetic-vosk",
            [],
            [],
            metrics,
        )

    assert "private native read detail" not in str(exc.value)
    assert FakeConverter.instances[-1].flushed is False
    assert metrics["read_errors"] == 1


def test_vosk_rejects_live_mix_before_loading_model(tmp_path: Path) -> None:
    model_path = tmp_path / "model"
    model_path.mkdir()

    with pytest.raises(vosk_backend.VoskBackendError, match="MIX capture"):
        vosk_backend.transcribe_vosk_live(
            VoskLiveConfig(model_path=model_path, source="MIX")
        )


def test_vosk_rejects_noncanonical_live_sys_rate_before_loading_model(
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "model"
    model_path.mkdir()

    with pytest.raises(vosk_backend.VoskBackendError, match="canonical 16000 Hz"):
        vosk_backend.transcribe_vosk_live(
            VoskLiveConfig(model_path=model_path, source="SYS", sample_rate=8_000)
        )
