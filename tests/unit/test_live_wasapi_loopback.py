from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pytest

from meeting_agent.live_transcription import vosk_backend
from meeting_agent.live_transcription.vosk_backend import VoskLiveConfig
from meeting_agent.live_transcription.wasapi_loopback import (
    LoopbackDevice,
    LoopbackBlockReader,
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


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


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


def test_nonblocking_reader_fills_idle_wall_clock_without_blocking_read() -> None:
    class IdleStream:
        read_called = False

        def get_read_available(self) -> int:
            return 0

        def read(self, *_args, **_kwargs) -> bytes:
            self.read_called = True
            pytest.fail("idle stream must not use blocking read")

    clock = FakeClock()
    stream = IdleStream()
    reader = LoopbackBlockReader(
        stream=stream,
        sample_rate=1_000,
        channels=2,
        block_ms=50,
        startup_grace_ms=0,
        poll_interval_ms=10,
        clock=clock.monotonic,
        sleeper=clock.sleep,
    )

    blocks = list(reader.iter_blocks(0.1))

    assert sum(len(block) // 4 for block in blocks) == 100
    assert all(set(block) <= {0} for block in blocks)
    assert stream.read_called is False
    assert 0.1 <= clock.now <= 0.12
    assert reader.metrics() == {
        "loopback_poll_mode": "read_available",
        "loopback_startup_grace_ms": 0,
        "loopback_poll_interval_ms": 10,
        "loopback_schedule_quantum_frames": 10,
        "availability_checks": len(blocks),
        "availability_errors": 0,
        "read_calls": 0,
        "read_errors": 0,
        "poll_sleeps": len(clock.sleeps),
        "idle_input_frames": 100,
        "idle_seconds": 0.1,
    }


def test_nonblocking_reader_reads_only_frames_reported_available() -> None:
    class ActiveStream:
        def __init__(self) -> None:
            self.read_calls: list[int] = []

        def get_read_available(self) -> int:
            return 1_000

        def read(self, frames: int, *, exception_on_overflow: bool) -> bytes:
            assert exception_on_overflow is False
            self.read_calls.append(frames)
            return b"\x01\x00" * frames

    clock = FakeClock()
    stream = ActiveStream()
    reader = LoopbackBlockReader(
        stream=stream,
        sample_rate=1_000,
        channels=1,
        block_ms=50,
        startup_grace_ms=0,
        poll_interval_ms=10,
        clock=clock.monotonic,
        sleeper=clock.sleep,
    )

    blocks = list(reader.iter_blocks(0.1))

    assert sum(stream.read_calls) == 100
    assert b"".join(blocks) == b"\x01\x00" * 100
    assert reader.idle_frames == 0
    assert reader.read_calls == len(stream.read_calls)


@pytest.mark.parametrize("available", [-1, True, 1.5, "bad"])
def test_nonblocking_reader_rejects_invalid_available_frame_count(available) -> None:
    class InvalidStream:
        def get_read_available(self):
            return available

    clock = FakeClock()
    reader = LoopbackBlockReader(
        stream=InvalidStream(),
        sample_rate=1_000,
        channels=1,
        block_ms=50,
        startup_grace_ms=0,
        poll_interval_ms=10,
        clock=clock.monotonic,
        sleeper=clock.sleep,
    )

    with pytest.raises(WasapiLoopbackError, match="invalid available-frame"):
        list(reader.iter_blocks(0.1))
    assert reader.availability_errors == 1


def test_nonblocking_reader_rejects_short_pcm_read_without_private_detail() -> None:
    class ShortReadStream:
        def get_read_available(self) -> int:
            return 100

        def read(self, frames: int, *, exception_on_overflow: bool) -> bytes:
            assert frames > 1
            assert exception_on_overflow is False
            return b"\x00\x00" * (frames - 1)

    clock = FakeClock()
    reader = LoopbackBlockReader(
        stream=ShortReadStream(),
        sample_rate=1_000,
        channels=1,
        block_ms=50,
        startup_grace_ms=0,
        poll_interval_ms=10,
        clock=clock.monotonic,
        sleeper=clock.sleep,
    )

    with pytest.raises(WasapiLoopbackError, match="unexpected PCM frame count"):
        list(reader.iter_blocks(0.1))
    assert reader.read_errors == 1


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

    class FakeReader:
        def __init__(self, *, stream, **_kwargs) -> None:
            self.stream = stream

        def iter_blocks(self, duration_sec):
            assert duration_sec == 0.02
            yield self.stream.read(480, exception_on_overflow=False)
            yield self.stream.read(480, exception_on_overflow=False)

        def metrics(self) -> dict:
            return {
                "loopback_poll_mode": "read_available",
                "loopback_startup_grace_ms": 20,
                "loopback_poll_interval_ms": 5,
                "availability_checks": 2,
                "availability_errors": 0,
                "read_calls": 2,
                "read_errors": 0,
                "poll_sleeps": 1,
                "idle_input_frames": 0,
                "idle_seconds": 0.0,
            }

    class Recognizer:
        def AcceptWaveform(self, _block: bytes) -> bool:
            return False

        def PartialResult(self) -> str:
            return '{"partial": ""}'

    monkeypatch.setattr(vosk_backend, "open_wasapi_loopback_stream", fake_open)
    monkeypatch.setattr(vosk_backend, "Pcm16MonoResampler", FakeConverter)
    monkeypatch.setattr(vosk_backend, "LoopbackBlockReader", FakeReader)
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
        "converted_frames": 320,
        "output_frames": 320,
        "resampler_clips": 0,
        "loopback_poll_mode": "read_available",
        "loopback_startup_grace_ms": 20,
        "loopback_poll_interval_ms": 5,
        "availability_checks": 2,
        "availability_errors": 0,
        "read_calls": 2,
        "read_errors": 0,
        "poll_sleeps": 1,
        "idle_input_frames": 0,
        "idle_seconds": 0.0,
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
            self.output_frames = 0
            self.clips = 0
            self.flushed = False
            type(self).instances.append(self)

        def convert(self, _block: bytes) -> bytes:
            pytest.fail("failed read must not reach conversion")

        def flush(self) -> bytes:
            self.flushed = True
            return b""

    class BrokenReader:
        def __init__(self, **_kwargs) -> None:
            pass

        def iter_blocks(self, _duration_sec):
            if False:
                yield b""
            try:
                raise OSError("private native read detail")
            except OSError as exc:
                raise WasapiLoopbackError(
                    "WASAPI loopback stream read failed"
                ) from exc

        def metrics(self) -> dict:
            return {
                "availability_checks": 1,
                "availability_errors": 0,
                "read_calls": 1,
                "read_errors": 1,
                "idle_input_frames": 0,
                "idle_seconds": 0.0,
            }

    monkeypatch.setattr(vosk_backend, "open_wasapi_loopback_stream", fake_open)
    monkeypatch.setattr(vosk_backend, "Pcm16MonoResampler", FakeConverter)
    monkeypatch.setattr(vosk_backend, "LoopbackBlockReader", BrokenReader)
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


def test_vosk_system_capture_keyboard_interrupt_finalizes_partial_audio(
    tmp_path: Path,
    monkeypatch,
) -> None:
    native_block = np.zeros((480, 2), dtype="<i2").tobytes()

    @contextmanager
    def fake_open(**_kwargs):
        yield OpenLoopbackStream(
            stream=object(),
            device=LoopbackDevice(
                index=19,
                name="Private device name",
                channels=2,
                sample_rate=48_000,
            ),
        )

    class InterruptingReader:
        def __init__(self, **_kwargs) -> None:
            pass

        def iter_blocks(self, _duration_sec):
            yield native_block
            raise KeyboardInterrupt

        def metrics(self) -> dict:
            return {
                "availability_checks": 2,
                "availability_errors": 0,
                "read_calls": 1,
                "read_errors": 0,
                "idle_input_frames": 0,
                "idle_seconds": 0.0,
            }

    class FakeConverter:
        def __init__(self, **_kwargs) -> None:
            self.input_frames = 0
            self.output_frames = 0
            self.clips = 0
            self.flushed = False

        def convert(self, block: bytes) -> bytes:
            self.input_frames += len(block) // 4
            self.output_frames += 160
            return b"\x00\x00" * 160

        def flush(self) -> bytes:
            self.flushed = True
            return b""

    class Recognizer:
        def AcceptWaveform(self, _block: bytes) -> bool:
            return False

        def PartialResult(self) -> str:
            return '{"partial":""}'

    monkeypatch.setattr(vosk_backend, "open_wasapi_loopback_stream", fake_open)
    monkeypatch.setattr(vosk_backend, "Pcm16MonoResampler", FakeConverter)
    monkeypatch.setattr(vosk_backend, "LoopbackBlockReader", InterruptingReader)
    metrics: dict = {}

    duration = vosk_backend._transcribe_system_loopback(
        VoskLiveConfig(model_path=tmp_path, source="SYS"),
        Recognizer(),
        "synthetic-vosk",
        [],
        [],
        metrics,
    )

    assert duration == pytest.approx(0.01)
    assert metrics["interrupted"] is True
    assert metrics["input_frames"] == 480
    assert metrics["output_frames"] == 160


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


@pytest.mark.parametrize("duration", [0.0, -1.0])
def test_vosk_rejects_nonpositive_duration_before_loading_model(
    tmp_path: Path,
    duration: float,
) -> None:
    model_path = tmp_path / "model"
    model_path.mkdir()

    with pytest.raises(vosk_backend.VoskBackendError, match="duration-sec"):
        vosk_backend.transcribe_vosk_live(
            VoskLiveConfig(
                model_path=model_path,
                source="SYS",
                duration_sec=duration,
            )
        )
