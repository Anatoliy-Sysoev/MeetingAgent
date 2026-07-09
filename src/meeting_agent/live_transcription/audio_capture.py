from __future__ import annotations

import platform
from dataclasses import dataclass, field
from typing import Any

VALID_LIVE_SOURCES = {"MIC", "SYS", "MIX"}
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
    supports_loopback: bool = False

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "index": self.index,
            "name": self.name,
            "hostapi": self.hostapi,
            "max_input_channels": self.max_input_channels,
            "max_output_channels": self.max_output_channels,
            "supports_loopback": self.supports_loopback,
        }
        if self.default_samplerate is not None:
            data["default_samplerate"] = self.default_samplerate
        return data


@dataclass(frozen=True)
class AudioSourcePreflight:
    source: str
    available: bool
    reason: str | None = None
    sample_rate: int = LIVE_SAMPLE_RATE
    channels: int = LIVE_CHANNELS
    dtype: str = LIVE_DTYPE
    devices: list[AudioDevice] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "source": self.source,
            "available": self.available,
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
    except ImportError:
        return None
    return sd


def _hostapi_names(sd: Any) -> dict[int, str]:
    try:
        hostapis = sd.query_hostapis()
    except Exception:  # noqa: BLE001
        return {}
    names: dict[int, str] = {}
    for index, item in enumerate(hostapis or []):
        if isinstance(item, dict):
            names[index] = str(item.get("name") or "")
    return names


def list_audio_devices(*, sd_module: Any | None = None) -> list[AudioDevice]:
    sd = _load_sounddevice(sd_module)
    if sd is None:
        return []
    hostapis = _hostapi_names(sd)
    try:
        raw_devices = sd.query_devices()
    except Exception:  # noqa: BLE001
        return []

    devices: list[AudioDevice] = []
    for index, item in enumerate(raw_devices or []):
        if not isinstance(item, dict):
            continue
        hostapi_index = int(item.get("hostapi") or 0)
        hostapi = hostapis.get(hostapi_index, "")
        max_input = int(item.get("max_input_channels") or 0)
        max_output = int(item.get("max_output_channels") or 0)
        default_samplerate = item.get("default_samplerate")
        devices.append(
            AudioDevice(
                index=index,
                name=str(item.get("name") or f"Device {index}"),
                hostapi=hostapi,
                max_input_channels=max_input,
                max_output_channels=max_output,
                default_samplerate=float(default_samplerate) if isinstance(default_samplerate, (int, float)) else None,
                supports_loopback=("wasapi" in hostapi.lower() and max_output > 0),
            )
        )
    return devices


def preflight_audio_source(
    source: str,
    *,
    sd_module: Any | None = None,
    system_name: str | None = None,
) -> AudioSourcePreflight:
    normalized = source.upper()
    if normalized not in VALID_LIVE_SOURCES:
        return AudioSourcePreflight(source=source, available=False, reason="unsupported_source")

    sd = _load_sounddevice(sd_module)
    if sd is None:
        return AudioSourcePreflight(source=normalized, available=False, reason="sounddevice_missing")

    devices = list_audio_devices(sd_module=sd)
    if normalized == "MIC":
        input_devices = [device for device in devices if device.max_input_channels > 0]
        return AudioSourcePreflight(
            source=normalized,
            available=bool(input_devices),
            reason=None if input_devices else "mic_input_device_missing",
            devices=input_devices,
        )

    if normalized == "SYS":
        current_system = (system_name or platform.system()).lower()
        if current_system != "windows":
            return AudioSourcePreflight(
                source=normalized,
                available=False,
                reason="sys_loopback_windows_only",
                devices=[device for device in devices if device.max_output_channels > 0],
            )
        loopback_devices = [device for device in devices if device.supports_loopback]
        return AudioSourcePreflight(
            source=normalized,
            available=bool(loopback_devices),
            reason=None if loopback_devices else "sys_loopback_device_missing",
            devices=loopback_devices,
        )

    mic = preflight_audio_source("MIC", sd_module=sd, system_name=system_name)
    sys = preflight_audio_source("SYS", sd_module=sd, system_name=system_name)
    mix_devices = [*mic.devices, *sys.devices]
    return AudioSourcePreflight(
        source=normalized,
        available=mic.available or sys.available,
        reason=None if (mic.available or sys.available) else "mix_input_device_missing",
        devices=mix_devices,
    )
