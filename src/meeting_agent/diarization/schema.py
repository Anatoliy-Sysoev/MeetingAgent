from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


DEFAULT_SPEAKER = "SPEAKER_UNKNOWN"


@dataclass(frozen=True)
class DiarizationInterval:
    speaker: str
    start: float
    end: float
    confidence: float | None = None
    backend: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "speaker": self.speaker,
            "start": self.start,
            "end": self.end,
            "confidence": self.confidence,
            "backend": self.backend,
        }
        if self.metadata:
            data["metadata"] = dict(self.metadata)
        return data


@dataclass(frozen=True)
class DiarizationReport:
    backend: str
    segmentation_model: str | None
    embedding_model: str | None
    num_speakers: int | str | None
    min_speakers: int | None
    max_speakers: int | None
    cluster_threshold: float | None
    min_duration_on: float | None
    min_duration_off: float | None
    sample_rate: int | None
    audio_duration_sec: float | None
    processed_in_sec: float | None
    rtf: float | None
    intervals_count: int
    speakers_count: int
    created_at: str
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "segmentation_model": self.segmentation_model,
            "embedding_model": self.embedding_model,
            "num_speakers": self.num_speakers,
            "min_speakers": self.min_speakers,
            "max_speakers": self.max_speakers,
            "cluster_threshold": self.cluster_threshold,
            "min_duration_on": self.min_duration_on,
            "min_duration_off": self.min_duration_off,
            "sample_rate": self.sample_rate,
            "audio_duration_sec": self.audio_duration_sec,
            "processed_in_sec": self.processed_in_sec,
            "rtf": self.rtf,
            "intervals_count": self.intervals_count,
            "speakers_count": self.speakers_count,
            "created_at": self.created_at,
            "warnings": list(self.warnings),
        }
