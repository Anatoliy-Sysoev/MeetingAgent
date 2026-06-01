from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CanonicalSegment:
    segment_id: str
    segment_index: int
    start: float
    end: float
    text: str
    source: str = "MIX"
    engine: str = "unknown"
    language: str | None = None
    avg_logprob: float | None = None
    no_speech_prob: float | None = None
    confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "segment_id": self.segment_id,
            "segment_index": self.segment_index,
            "start": self.start,
            "end": self.end,
            "text": self.text,
            "source": self.source,
            "engine": self.engine,
        }
        if self.language is not None:
            data["language"] = self.language
        if self.avg_logprob is not None:
            data["avg_logprob"] = self.avg_logprob
        if self.no_speech_prob is not None:
            data["no_speech_prob"] = self.no_speech_prob
        if self.confidence is not None:
            data["confidence"] = self.confidence
        if self.metadata:
            data["metadata"] = dict(self.metadata)
        return data


@dataclass(frozen=True)
class TranscriptDocument:
    meeting_id: str
    title: str
    engine: str
    model: str | None
    language: str | None
    segments: list[CanonicalSegment]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "meeting_id": self.meeting_id,
            "title": self.title,
            "engine": self.engine,
            "model": self.model,
            "language": self.language,
            "segments_count": len(self.segments),
            "segments": [segment.to_dict() for segment in self.segments],
        }
        if self.metadata:
            data["metadata"] = dict(self.metadata)
        return data


@dataclass(frozen=True)
class TranscriptionReport:
    engine: str
    model: str | None
    language: str | None
    duration_seconds: float
    segments_count: int
    chars_count: int
    empty_segments_dropped: int
    warnings: list[str]
    started_at: str | None = None
    finished_at: str | None = None
    elapsed_seconds: float | None = None
    backend_metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "engine": self.engine,
            "model": self.model,
            "language": self.language,
            "duration_seconds": self.duration_seconds,
            "segments_count": self.segments_count,
            "chars_count": self.chars_count,
            "empty_segments_dropped": self.empty_segments_dropped,
            "warnings": list(self.warnings),
        }
        if self.started_at is not None:
            data["started_at"] = self.started_at
        if self.finished_at is not None:
            data["finished_at"] = self.finished_at
        if self.elapsed_seconds is not None:
            data["elapsed_seconds"] = self.elapsed_seconds
        if self.backend_metrics:
            data["backend_metrics"] = dict(self.backend_metrics)
        return data
