from __future__ import annotations

import platform
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .wasapi_loopback import LoopbackDiscovery, discover_wasapi_loopbacks


VALID_LIVE_SOURCES = frozenset({"MIC", "SYS", "MIX"})
LIVE_SAMPLE_RATE = 16_000
LIVE_CHANNELS = 1
LIVE_DTYPE = "int16"


@dataclass(frozen=True)
class AudioDevice:
    index: int
    name: str
    hostapi: str
    max_input_channels: int
    max_output_channels: int
    default_samplerate: float | None = None
    loopback_candidate: bool = False

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "index": self.index,
            "name": self.name,
            "hostapi": self.hostapi,
            "max_input_channels": self.max_input_channels,
            "max_output_channels": self.max_output_channels,
            "loopback_candidate": self.loopback_candidate,
        }
        if self.default_samplerate is not None:
            data["default_samplerate"] = self.default_samplerate
        return data


@dataclass(frozen=True)
class AudioSourcePreflight:
    source: str
    available: bool
    device_available: bool
    capture_supported: bool
    reason: str | None = None
    sample_rate: int = LIVE_SAMPLE_RATE
    channels: int = LIVE_CHANNELS
    dtype: str = LIVE_DTYPE
    devices: list[AudioDevice] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "source": self.source,
            "available": self.available,
            "device_available": self.device_available,
            "capture_supported": self.capture_supported,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "dtype": self.dtype,
            "devices": [device.to_dict() for device in self.devices],
        }
        if self.reason:
            data["reason"] = self.reason
        return data


def _load_sounddevice(sd_module: Any | None = None) -> Any | None:
    if sd_module is False:
        return None
    if sd_module is not None:
        return sd_module
    try:
        import sounddevice as sd
    except (ImportError, OSError):
        return None
    return sd


def _hostapi_names(sd: Any) -> dict[int, str]:
    try:
        hostapis = sd.query_hostapis()
    except Exception:  # noqa: BLE001 - optional PortAudio runtime may fail arbitrarily
        return {}
    names: dict[int, str] = {}
    for index, item in enumerate(hostapis or []):
        if isinstance(item, Mapping):
            names[index] = str(item.get("name") or "")
    return names


def _nonnegative_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError, OverflowError):
        return 0


def _optional_index(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        index = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return index if index >= 0 else None


def _optional_rate(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        rate = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return rate if rate > 0 else None


def list_audio_devices(*, sd_module: Any | None = None) -> list[AudioDevice]:
    """Discover PortAudio devices without opening an input or output stream."""
    sd = _load_sounddevice(sd_module)
    if sd is None:
        return []
    hostapis = _hostapi_names(sd)
    try:
        raw_devices = sd.query_devices()
    except Exception:  # noqa: BLE001 - discovery must fail closed
        return []

    devices: list[AudioDevice] = []
    for index, item in enumerate(raw_devices or []):
        if not isinstance(item, Mapping):
            continue
        hostapi_index = _optional_index(item.get("hostapi"))
        hostapi = hostapis.get(hostapi_index, "") if hostapi_index is not None else ""
        max_input = _nonnegative_int(item.get("max_input_channels"))
        max_output = _nonnegative_int(item.get("max_output_channels"))
        devices.append(
            AudioDevice(
                index=index,
                name=str(item.get("name") or f"Device {index}"),
                hostapi=hostapi,
                max_input_channels=max_input,
                max_output_channels=max_output,
                default_samplerate=_optional_rate(item.get("default_samplerate")),
                loopback_candidate="wasapi" in hostapi.lower() and max_output > 0,
            )
        )
    return devices


def _result(
    source: str,
    *,
    device_available: bool,
    capture_supported: bool,
    reason: str | None,
    devices: list[AudioDevice],
) -> AudioSourcePreflight:
    return AudioSourcePreflight(
        source=source,
        available=device_available and capture_supported,
        device_available=device_available,
        capture_supported=capture_supported,
        reason=reason,
        devices=devices,
    )


def _mic_format_supported(sd: Any, device_index: int | None) -> bool:
    check_input_settings = getattr(sd, "check_input_settings", None)
    if not callable(check_input_settings):
        return False
    try:
        check_input_settings(
            device=device_index,
            channels=LIVE_CHANNELS,
            dtype=LIVE_DTYPE,
            samplerate=LIVE_SAMPLE_RATE,
        )
    except Exception:  # noqa: BLE001 - PortAudio reports backend-specific errors
        return False
    return True


def _loopback_audio_devices(discovery: LoopbackDiscovery) -> list[AudioDevice]:
    return [
        AudioDevice(
            index=device.index,
            name=device.name,
            hostapi="Windows WASAPI loopback",
            max_input_channels=device.channels,
            max_output_channels=0,
            default_samplerate=float(device.sample_rate),
            loopback_candidate=True,
        )
        for device in discovery.devices
    ]


def preflight_audio_source(
    source: str,
    *,
    sd_module: Any | None = None,
    pyaudio_module: Any | None = None,
    system_name: str | None = None,
    audio_device_index: int | None = None,
) -> AudioSourcePreflight:
    """Report whether the current backend can capture one explicit source."""
    normalized = str(source or "").upper()
    if normalized not in VALID_LIVE_SOURCES:
        return _result(
            normalized or str(source),
            device_available=False,
            capture_supported=False,
            reason="unsupported_source",
            devices=[],
        )

    current_system = (system_name or platform.system()).lower()
    if normalized == "SYS":
        if current_system != "windows":
            return _result(
                normalized,
                device_available=False,
                capture_supported=False,
                reason="sys_loopback_windows_only",
                devices=[],
            )
        discovery = discover_wasapi_loopbacks(pyaudio_module=pyaudio_module)
        loopback_devices = _loopback_audio_devices(discovery)
        selected = discovery.select(audio_device_index)
        reason = discovery.reason
        if reason is None and selected is None:
            reason = (
                "sys_loopback_device_not_found"
                if audio_device_index is not None
                else "sys_loopback_default_missing"
            )
        return _result(
            normalized,
            device_available=selected is not None,
            capture_supported=selected is not None,
            reason=reason,
            devices=loopback_devices,
        )

    sd = _load_sounddevice(sd_module)
    if sd is None:
        return _result(
            normalized,
            device_available=False,
            capture_supported=False,
            reason="sounddevice_missing",
            devices=[],
        )

    devices = list_audio_devices(sd_module=sd)
    if normalized == "MIC":
        input_devices = [device for device in devices if device.max_input_channels > 0]
        if not input_devices:
            return _result(
                normalized,
                device_available=False,
                capture_supported=False,
                reason="mic_input_device_missing",
                devices=[],
            )
        selected_input = next(
            (
                device
                for device in input_devices
                if device.index == audio_device_index
            ),
            None,
        )
        if audio_device_index is not None and selected_input is None:
            return _result(
                normalized,
                device_available=False,
                capture_supported=False,
                reason="mic_input_device_not_found",
                devices=input_devices,
            )
        format_supported = _mic_format_supported(sd, audio_device_index)
        return _result(
            normalized,
            device_available=True,
            capture_supported=format_supported,
            reason=None if format_supported else "mic_capture_format_unsupported",
            devices=input_devices,
        )

    mic_devices = [device for device in devices if device.max_input_channels > 0]
    discovery = discover_wasapi_loopbacks(pyaudio_module=pyaudio_module)
    loopback_devices = _loopback_audio_devices(discovery)
    # sounddevice and PyAudioWPatch use independent device-index namespaces.
    # Keep both inventories even when their numeric indexes happen to collide.
    mix_devices = [*mic_devices, *loopback_devices]
    if current_system != "windows":
        return _result(
            normalized,
            device_available=False,
            capture_supported=False,
            reason="mix_loopback_windows_only",
            devices=mic_devices,
        )
    selected_loopback = discovery.select(audio_device_index)
    if not mic_devices or selected_loopback is None:
        return _result(
            normalized,
            device_available=False,
            capture_supported=False,
            reason="mix_source_device_missing",
            devices=mix_devices,
        )
    return _result(
        normalized,
        device_available=True,
        capture_supported=False,
        reason="mix_capture_not_implemented",
        devices=mix_devices,
    )
