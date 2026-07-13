from __future__ import annotations

from collections.abc import Iterator, Mapping
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
