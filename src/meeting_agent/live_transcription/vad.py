from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SpeechWindow:
    start: float
    end: float

    def overlaps(self, start: float, end: float) -> bool:
        return self.start < end and self.end > start

    def to_dict(self) -> dict[str, float]:
        return {"start": round(self.start, 3), "end": round(self.end, 3)}


@dataclass(frozen=True)
class SileroVadConfig:
    threshold: float = 0.5
    min_speech_ms: int = 250
    min_silence_ms: int = 100
    speech_pad_ms: int = 100


class VadBackendError(RuntimeError):
    pass


def detect_silero_speech_windows(
    wav_path: Path,
    *,
    sample_rate: int,
    config: SileroVadConfig,
) -> list[SpeechWindow]:
    try:
        from silero_vad import get_speech_timestamps, load_silero_vad, read_audio
    except ImportError as exc:
        raise VadBackendError(
            "Silero VAD is not installed. Install optional live dependencies: "
            "python -m pip install -r requirements-live.txt"
        ) from exc

    wav = read_audio(str(wav_path), sampling_rate=sample_rate)
    model = load_silero_vad()
    timestamps: list[dict[str, Any]] = get_speech_timestamps(
        wav,
        model,
        sampling_rate=sample_rate,
        threshold=config.threshold,
        min_speech_duration_ms=config.min_speech_ms,
        min_silence_duration_ms=config.min_silence_ms,
        speech_pad_ms=config.speech_pad_ms,
        return_seconds=True,
    )
    return [
        SpeechWindow(start=float(item["start"]), end=float(item["end"]))
        for item in timestamps
        if isinstance(item, dict) and "start" in item and "end" in item and float(item["end"]) > float(item["start"])
    ]


def block_overlaps_speech(start: float, end: float, windows: list[SpeechWindow]) -> bool:
    if not windows:
        return False
    return any(window.overlaps(start, end) for window in windows)
