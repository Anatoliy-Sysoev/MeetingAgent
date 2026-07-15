from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


SOURCE_ARTIFACT_KEYS = {
    "MIC": {
        "live_segments": "live_segments_mic",
        "live_partials": "live_partials_mic",
        "live_transcript": "live_transcript_mic",
        "live_srt": "live_srt_mic",
        "live_vtt": "live_vtt_mic",
        "live_report": "live_report_mic",
        "live_audio": "live_audio_mic",
    },
    "SYS": {
        "live_segments": "live_segments_sys",
        "live_partials": "live_partials_sys",
        "live_transcript": "live_transcript_sys",
        "live_srt": "live_srt_sys",
        "live_vtt": "live_vtt_sys",
        "live_report": "live_report_sys",
        "live_audio": "live_audio_sys",
        "live_diarization": "live_diarization_sys",
    },
    "MIX": {
        "live_segments": "live_segments_mix",
        "live_partials": "live_partials_mix",
        "live_transcript": "live_transcript_mix",
        "live_srt": "live_srt_mix",
        "live_vtt": "live_vtt_mix",
        "live_report": "live_report_mix",
    },
}


@dataclass(frozen=True)
class LiveSegment:
    segment_id: str
    segment_index: int
    start: float
    end: float
    text: str
    source: str
    engine: str
    model: str | None = None
    confidence: float | None = None
    is_final: bool = True
    created_at: str | None = None
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
            "is_final": self.is_final,
        }
        if self.model is not None:
            data["model"] = self.model
        if self.confidence is not None:
            data["confidence"] = self.confidence
        if self.created_at is not None:
            data["created_at"] = self.created_at
        if self.metadata:
            data["metadata"] = dict(self.metadata)
        return data


@dataclass(frozen=True)
class LiveSessionReport:
    engine: str
    model: str | None
    source: str
    sample_rate: int
    block_ms: int
    duration_seconds: float
    segments_count: int
    partials_count: int
    chars_count: int
    started_at: str
    finished_at: str
    elapsed_seconds: float
    warnings: list[str] = field(default_factory=list)
    backend_metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "engine": self.engine,
            "model": self.model,
            "source": self.source,
            "sample_rate": self.sample_rate,
            "block_ms": self.block_ms,
            "duration_seconds": self.duration_seconds,
            "segments_count": self.segments_count,
            "partials_count": self.partials_count,
            "chars_count": self.chars_count,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "elapsed_seconds": self.elapsed_seconds,
            "warnings": list(self.warnings),
        }
        if self.backend_metrics:
            data["backend_metrics"] = dict(self.backend_metrics)
        return data
