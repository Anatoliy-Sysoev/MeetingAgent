from __future__ import annotations

import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any


MAX_DEVICE_NAME_CHARS = 200


class WasapiLoopbackError(RuntimeError):
    pass


@dataclass(frozen=True)
class LoopbackDevice:
    index: int
    name: str
    channels: int
    sample_rate: int


@dataclass(frozen=True)
class LoopbackDiscovery:
    backend_available: bool
    devices: list[LoopbackDevice] = field(default_factory=list)
    default_device_index: int | None = None
    reason: str | None = None

    def select(self, device_index: int | None = None) -> LoopbackDevice | None:
        selected_index = self.default_device_index if device_index is None else device_index
        if selected_index is None:
            return None
        return next(
            (device for device in self.devices if device.index == selected_index),
            None,
        )


@dataclass(frozen=True)
class OpenLoopbackStream:
    stream: Any
    device: LoopbackDevice


class LoopbackBlockReader:
    """Poll PortAudio without blocking and keep a native-rate wall clock."""

    def __init__(
        self,
        *,
        stream: Any,
        sample_rate: int,
        channels: int,
        block_ms: int,
        startup_grace_ms: int | None = None,
        poll_interval_ms: int | None = None,
        clock: Callable[[], float] | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        if sample_rate <= 0 or channels <= 0 or block_ms <= 0:
            raise WasapiLoopbackError("Loopback reader settings must be positive")
        self.stream = stream
        self.sample_rate = sample_rate
        self.channels = channels
        self.frames_per_block = max(1, int(sample_rate * block_ms / 1000))
        self.startup_grace_ms = (
            min(100, max(20, block_ms))
            if startup_grace_ms is None
            else startup_grace_ms
        )
        self.poll_interval_ms = (
            min(20, max(5, block_ms // 10))
            if poll_interval_ms is None
            else poll_interval_ms
        )
        if not 0 <= self.startup_grace_ms <= 1_000:
            raise WasapiLoopbackError(
                "Loopback startup grace must be in the range 0..1000 ms"
            )
        if not 1 <= self.poll_interval_ms <= 100:
            raise WasapiLoopbackError(
                "Loopback poll interval must be in the range 1..100 ms"
            )
        self._clock = clock or time.monotonic
        self._sleep = sleeper or time.sleep
        self.scheduled_frames = 0
        self.idle_frames = 0
        self.availability_checks = 0
        self.availability_errors = 0
        self.read_calls = 0
        self.read_errors = 0
        self.poll_sleeps = 0

    def iter_blocks(self, duration_sec: float | None) -> Iterator[bytes]:
        if duration_sec is not None and duration_sec <= 0:
            raise WasapiLoopbackError("Loopback duration must be positive")
        max_frames = (
            max(1, int(round(self.sample_rate * duration_sec)))
            if duration_sec is not None
            else None
        )
        started = self._clock()
        grace_seconds = self.startup_grace_ms / 1000.0
        poll_seconds = self.poll_interval_ms / 1000.0
        schedule_quantum_frames = max(1, int(self.sample_rate * poll_seconds))
        frame_width = self.channels * 2

        while max_frames is None or self.scheduled_frames < max_frames:
            elapsed = max(0.0, self._clock() - started - grace_seconds)
            if max_frames is not None and elapsed >= duration_sec:
                target_frames = max_frames
            else:
                elapsed_ticks = int(elapsed / poll_seconds)
                target_frames = elapsed_ticks * schedule_quantum_frames
                if max_frames is not None:
                    target_frames = min(target_frames, max_frames)
            due_frames = target_frames - self.scheduled_frames
            if due_frames <= 0:
                self.poll_sleeps += 1
                self._sleep(poll_seconds)
                continue

            available = self._read_available()
            block_frames = min(due_frames, self.frames_per_block)
            if available > 0:
                block_frames = min(block_frames, available)
                data = self._read(block_frames, frame_width)
            else:
                data = b"\x00" * (block_frames * frame_width)
                self.idle_frames += block_frames
            self.scheduled_frames += block_frames
            yield data

    def metrics(self) -> dict[str, int | float | str]:
        return {
            "loopback_poll_mode": "read_available",
            "loopback_startup_grace_ms": self.startup_grace_ms,
            "loopback_poll_interval_ms": self.poll_interval_ms,
            "loopback_schedule_quantum_frames": max(
                1,
                int(self.sample_rate * self.poll_interval_ms / 1000),
            ),
            "availability_checks": self.availability_checks,
            "availability_errors": self.availability_errors,
            "read_calls": self.read_calls,
            "read_errors": self.read_errors,
            "poll_sleeps": self.poll_sleeps,
            "idle_input_frames": self.idle_frames,
            "idle_seconds": round(self.idle_frames / self.sample_rate, 3),
        }

    def _read_available(self) -> int:
        self.availability_checks += 1
        try:
            value = self.stream.get_read_available()
        except Exception as exc:  # noqa: BLE001 - normalize native backend failures
            self.availability_errors += 1
            raise WasapiLoopbackError(
                "WASAPI loopback availability check failed"
            ) from exc
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            self.availability_errors += 1
            raise WasapiLoopbackError(
                "WASAPI loopback returned invalid available-frame count"
            )
        return value

    def _read(self, frames: int, frame_width: int) -> bytes:
        self.read_calls += 1
        try:
            raw = self.stream.read(frames, exception_on_overflow=False)
        except Exception as exc:  # noqa: BLE001 - normalize native backend failures
            self.read_errors += 1
            raise WasapiLoopbackError("WASAPI loopback stream read failed") from exc
        if not isinstance(raw, (bytes, bytearray, memoryview)):
            self.read_errors += 1
            raise WasapiLoopbackError("WASAPI loopback returned non-PCM audio data")
        data = bytes(raw)
        if len(data) != frames * frame_width:
            self.read_errors += 1
            raise WasapiLoopbackError(
                "WASAPI loopback returned an unexpected PCM frame count"
            )
        return data


def _load_pyaudio(pyaudio_module: Any | None = None) -> Any | None:
    if pyaudio_module is False:
        return None
    if pyaudio_module is not None:
        return pyaudio_module
    try:
        import pyaudiowpatch as pyaudio
    except (ImportError, OSError):
        return None
    return pyaudio


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if parsed > 0 else None


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if parsed >= 0 else None


def _device_from_info(info: Any) -> LoopbackDevice | None:
    if not isinstance(info, Mapping) or info.get("isLoopbackDevice") is not True:
        return None
    index = _nonnegative_int(info.get("index"))
    channels = _positive_int(info.get("maxInputChannels"))
    sample_rate = _positive_int(info.get("defaultSampleRate"))
    if index is None or channels is None or sample_rate is None:
        return None
    name = " ".join(str(info.get("name") or f"Loopback {index}").split())
    return LoopbackDevice(
        index=index,
        name=name[:MAX_DEVICE_NAME_CHARS],
        channels=channels,
        sample_rate=sample_rate,
    )


def _terminate_manager(manager: Any) -> None:
    try:
        manager.terminate()
    except Exception:  # noqa: BLE001 - cleanup must preserve the original result
        pass


def discover_wasapi_loopbacks(
    *,
    pyaudio_module: Any | None = None,
) -> LoopbackDiscovery:
    pyaudio = _load_pyaudio(pyaudio_module)
    if pyaudio is None:
        return LoopbackDiscovery(
            backend_available=False,
            reason="sys_loopback_backend_missing",
        )
    try:
        manager = pyaudio.PyAudio()
    except Exception:  # noqa: BLE001 - native backend errors are not public detail
        return LoopbackDiscovery(
            backend_available=True,
            reason="sys_loopback_discovery_failed",
        )

    try:
        try:
            raw_devices = list(manager.get_loopback_device_info_generator())
        except Exception:  # noqa: BLE001 - fail closed on native discovery errors
            return LoopbackDiscovery(
                backend_available=True,
                reason="sys_loopback_discovery_failed",
            )
        devices_by_index = {
            device.index: device
            for raw_device in raw_devices
            if (device := _device_from_info(raw_device)) is not None
        }
        default_device: LoopbackDevice | None = None
        try:
            default_device = _device_from_info(manager.get_default_wasapi_loopback())
        except Exception:  # noqa: BLE001 - explicit device selection can still work
            pass
        if default_device is not None:
            devices_by_index.setdefault(default_device.index, default_device)
        devices = sorted(devices_by_index.values(), key=lambda device: device.index)
        return LoopbackDiscovery(
            backend_available=True,
            devices=devices,
            default_device_index=(
                default_device.index if default_device is not None else None
            ),
            reason=None if devices else "sys_loopback_device_missing",
        )
    finally:
        _terminate_manager(manager)


def _resolve_runtime_device(manager: Any, device_index: int | None) -> LoopbackDevice:
    try:
        info = (
            manager.get_default_wasapi_loopback()
            if device_index is None
            else manager.get_device_info_by_index(device_index)
        )
    except Exception as exc:  # noqa: BLE001 - normalize native backend failures
        raise WasapiLoopbackError("WASAPI loopback device is unavailable") from exc
    device = _device_from_info(info)
    if device is None:
        raise WasapiLoopbackError("Selected audio device is not a WASAPI loopback input")
    return device


@contextmanager
def open_wasapi_loopback_stream(
    *,
    device_index: int | None,
    block_ms: int,
    pyaudio_module: Any | None = None,
) -> Iterator[OpenLoopbackStream]:
    pyaudio = _load_pyaudio(pyaudio_module)
    if pyaudio is None:
        raise WasapiLoopbackError(
            "PyAudioWPatch is not installed; install requirements-live.txt"
        )
    try:
        manager = pyaudio.PyAudio()
    except Exception as exc:  # noqa: BLE001 - normalize native backend failures
        raise WasapiLoopbackError("WASAPI loopback backend failed to initialize") from exc

    stream: Any | None = None
    try:
        device = _resolve_runtime_device(manager, device_index)
        frames_per_buffer = max(1, int(device.sample_rate * block_ms / 1000))
        try:
            stream = manager.open(
                format=pyaudio.paInt16,
                channels=device.channels,
                rate=device.sample_rate,
                input=True,
                input_device_index=device.index,
                frames_per_buffer=frames_per_buffer,
            )
        except Exception as exc:  # noqa: BLE001 - normalize native backend failures
            raise WasapiLoopbackError("WASAPI loopback stream failed to open") from exc
        yield OpenLoopbackStream(stream=stream, device=device)
    finally:
        if stream is not None:
            try:
                stream.stop_stream()
            except Exception:  # noqa: BLE001 - continue cleanup
                pass
            try:
                stream.close()
            except Exception:  # noqa: BLE001 - continue cleanup
                pass
        _terminate_manager(manager)


class Pcm16MonoResampler:
    def __init__(
        self,
        *,
        input_rate: int,
        input_channels: int,
        output_rate: int,
        soxr_module: Any | None = None,
    ) -> None:
        if input_rate <= 0 or input_channels <= 0 or output_rate <= 0:
            raise WasapiLoopbackError("Audio conversion settings must be positive")
        try:
            import numpy as np
        except ImportError as exc:
            raise WasapiLoopbackError("numpy is required for loopback conversion") from exc
        if soxr_module is None:
            try:
                import soxr as soxr_module
            except (ImportError, OSError) as exc:
                raise WasapiLoopbackError(
                    "soxr is not installed; install requirements-live.txt"
                ) from exc
        self._np = np
        self._input_channels = input_channels
        self._stream = soxr_module.ResampleStream(
            input_rate,
            output_rate,
            1,
            dtype="int16",
            quality="HQ",
        )
        self._finished = False
        self.input_frames = 0
        self.output_frames = 0

    def convert(
        self,
        block: bytes | bytearray | memoryview,
        *,
        last: bool = False,
    ) -> bytes:
        if self._finished:
            raise WasapiLoopbackError("Audio resampler is already finalized")
        if not isinstance(block, (bytes, bytearray, memoryview)):
            raise WasapiLoopbackError("Loopback stream returned non-PCM audio data")
        frame_width = 2 * self._input_channels
        if len(block) % frame_width:
            raise WasapiLoopbackError("Loopback block has an incomplete PCM frame")
        samples = self._np.frombuffer(block, dtype="<i2")
        frames = len(samples) // self._input_channels
        self.input_frames += frames
        if self._input_channels == 1:
            mono = samples.copy()
        else:
            matrix = samples.reshape(frames, self._input_channels)
            mono = self._np.rint(matrix.astype(self._np.float64).mean(axis=1))
            mono = self._np.clip(mono, -32768, 32767).astype("<i2")
        output = self._stream.resample_chunk(mono, last=last)
        output_array = self._np.asarray(output, dtype="<i2")
        self.output_frames += len(output_array)
        if last:
            self._finished = True
        return output_array.tobytes()

    def flush(self) -> bytes:
        return self.convert(b"", last=True)

    @property
    def clips(self) -> int:
        try:
            return int(self._stream.num_clips())
        except Exception:  # noqa: BLE001 - metrics must not break capture
            return 0
