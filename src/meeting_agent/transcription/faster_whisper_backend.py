from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_FASTER_WHISPER_MODEL = "large-v3-turbo"


@dataclass(frozen=True)
class FasterWhisperConfig:
    model: str = DEFAULT_FASTER_WHISPER_MODEL
    language: str = "ru"
    compute_type: str = "int8"
    device: str = "cpu"
    beam_size: int = 5
    vad_filter: bool = True
    source: str = "MIX"
    initial_prompt: str | None = None
    # faster-whisper >= 1.0 supports hotwords= directly (additive boosting).
    # When set, hotwords takes priority over initial_prompt for term boosting.
    hotwords: list[str] | None = None


@dataclass(frozen=True)
class FasterWhisperResult:
    segments: list[dict[str, Any]]
    metrics: dict[str, Any] = field(default_factory=dict)


def load_model(config: FasterWhisperConfig):
    from faster_whisper import WhisperModel

    return WhisperModel(config.model, device=config.device, compute_type=config.compute_type)


def transcribe_faster_whisper(media_path: Path, config: FasterWhisperConfig) -> FasterWhisperResult:
    model = load_model(config)
    transcribe_kwargs: dict = {
        "language": config.language,
        "vad_filter": config.vad_filter,
        "beam_size": config.beam_size,
    }
    if config.hotwords:
        transcribe_kwargs["hotwords"] = " ".join(config.hotwords)
    elif config.initial_prompt:
        transcribe_kwargs["initial_prompt"] = config.initial_prompt
    segment_iter, info = model.transcribe(str(media_path), **transcribe_kwargs)

    rows: list[dict[str, Any]] = []
    for segment in segment_iter:
        row: dict[str, Any] = {
            "start": round(float(segment.start), 3),
            "end": round(float(segment.end), 3),
            "text": str(segment.text or "").strip(),
            "source": config.source,
            "engine": "faster-whisper",
            "language": config.language,
        }
        avg_logprob = getattr(segment, "avg_logprob", None)
        no_speech_prob = getattr(segment, "no_speech_prob", None)
        if avg_logprob is not None:
            row["avg_logprob"] = float(avg_logprob)
        if no_speech_prob is not None:
            row["no_speech_prob"] = float(no_speech_prob)
        rows.append(row)

    metrics = {
        "asr_model": config.model,
        "asr_engine": "faster-whisper",
        "language": getattr(info, "language", config.language),
        "language_probability": getattr(info, "language_probability", None),
        "duration": getattr(info, "duration", None),
        "duration_after_vad": getattr(info, "duration_after_vad", None),
        "device": config.device,
        "compute_type": config.compute_type,
        "beam_size": config.beam_size,
        "vad_filter": config.vad_filter,
    }
    return FasterWhisperResult(
        segments=rows, metrics={key: value for key, value in metrics.items() if value is not None}
    )
