from __future__ import annotations

from typing import Any

from .schema import DEFAULT_SPEAKER, DiarizationInterval


def overlap_seconds(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def assign_speaker(
    segment: dict[str, Any],
    intervals: list[DiarizationInterval],
    *,
    min_overlap_ratio: float = 0.3,
) -> tuple[str, float, float]:
    start = float(segment.get("start", 0.0))
    end = float(segment.get("end", start))
    duration = max(1e-6, end - start)

    best_speaker = DEFAULT_SPEAKER
    best_overlap = 0.0
    for interval in intervals:
        overlap = overlap_seconds(start, end, interval.start, interval.end)
        if overlap > best_overlap:
            best_speaker = interval.speaker
            best_overlap = overlap

    overlap_ratio = best_overlap / duration
    if overlap_ratio < min_overlap_ratio:
        return DEFAULT_SPEAKER, round(best_overlap, 3), round(overlap_ratio, 3)
    return best_speaker, round(best_overlap, 3), round(overlap_ratio, 3)


def merge_segments_with_diarization(
    segments: list[dict[str, Any]],
    intervals: list[DiarizationInterval],
    *,
    min_overlap_ratio: float = 0.3,
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for segment in segments:
        speaker, overlap, overlap_ratio = assign_speaker(
            segment,
            intervals,
            min_overlap_ratio=min_overlap_ratio,
        )
        row = dict(segment)
        row["speaker"] = speaker
        row["speaker_name"] = speaker
        row["speaker_overlap_seconds"] = overlap
        row["speaker_overlap_ratio"] = overlap_ratio
        merged.append(row)
    return merged
