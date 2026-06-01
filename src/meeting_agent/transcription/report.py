from __future__ import annotations

from .normalize import NormalizationResult
from .schema import CanonicalSegment, TranscriptionReport


def transcript_duration(segments: list[CanonicalSegment]) -> float:
    if not segments:
        return 0.0
    return round(max(segment.end for segment in segments) - min(segment.start for segment in segments), 3)


def chars_count(segments: list[CanonicalSegment]) -> int:
    return sum(len(segment.text) for segment in segments)


def build_transcription_report(
    normalization: NormalizationResult,
    *,
    engine: str,
    model: str | None = None,
    language: str | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
    elapsed_seconds: float | None = None,
) -> TranscriptionReport:
    warnings = list(normalization.warnings)
    if normalization.invalid_dropped:
        warnings.append(f"invalid_segments_dropped={normalization.invalid_dropped}")

    return TranscriptionReport(
        engine=engine,
        model=model,
        language=language,
        duration_seconds=transcript_duration(normalization.segments),
        segments_count=len(normalization.segments),
        chars_count=chars_count(normalization.segments),
        empty_segments_dropped=normalization.empty_dropped,
        warnings=warnings,
        started_at=started_at,
        finished_at=finished_at,
        elapsed_seconds=elapsed_seconds,
    )
