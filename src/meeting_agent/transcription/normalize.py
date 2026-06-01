from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .schema import CanonicalSegment


@dataclass(frozen=True)
class NormalizationResult:
    segments: list[CanonicalSegment]
    empty_dropped: int
    invalid_dropped: int
    warnings: list[str]


def _as_float(value: Any, field_name: str, row_index: int) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"segment {row_index}: {field_name} must be numeric") from exc


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def normalize_segments(
    raw_segments: Iterable[dict[str, Any]],
    *,
    engine: str,
    language: str | None = None,
    source: str = "MIX",
    segment_id_prefix: str = "seg",
) -> NormalizationResult:
    normalized: list[CanonicalSegment] = []
    warnings: list[str] = []
    empty_dropped = 0
    invalid_dropped = 0

    for input_index, row in enumerate(raw_segments, start=1):
        text = _clean_text(row.get("text"))
        if not text:
            empty_dropped += 1
            continue

        try:
            start = round(_as_float(row.get("start"), "start", input_index), 3)
            end = round(_as_float(row.get("end"), "end", input_index), 3)
        except ValueError as exc:
            invalid_dropped += 1
            warnings.append(str(exc))
            continue

        if start < 0:
            warnings.append(f"segment {input_index}: start below zero was clamped")
            start = 0.0
        if end <= start:
            invalid_dropped += 1
            warnings.append(f"segment {input_index}: end must be greater than start")
            continue

        metadata = dict(row.get("metadata", {})) if isinstance(row.get("metadata"), dict) else {}
        if "window_id" in row:
            metadata.setdefault("window_id", row["window_id"])
        if "raw_segment_index" in row:
            metadata.setdefault("raw_segment_index", row["raw_segment_index"])

        normalized.append(
            CanonicalSegment(
                segment_id="",
                segment_index=0,
                start=start,
                end=end,
                text=text,
                source=str(row.get("source") or source),
                engine=str(row.get("engine") or engine),
                language=str(row.get("language") or language) if (row.get("language") or language) else None,
                avg_logprob=_optional_float(row.get("avg_logprob")),
                no_speech_prob=_optional_float(row.get("no_speech_prob")),
                confidence=_optional_float(row.get("confidence")),
                metadata=metadata,
            )
        )

    normalized.sort(key=lambda segment: (segment.start, segment.end, segment.text))

    reindexed: list[CanonicalSegment] = []
    for index, segment in enumerate(normalized, start=1):
        reindexed.append(
            CanonicalSegment(
                segment_id=f"{segment_id_prefix}-{index:06d}",
                segment_index=index,
                start=segment.start,
                end=segment.end,
                text=segment.text,
                source=segment.source,
                engine=segment.engine,
                language=segment.language,
                avg_logprob=segment.avg_logprob,
                no_speech_prob=segment.no_speech_prob,
                confidence=segment.confidence,
                metadata=segment.metadata,
            )
        )

    return NormalizationResult(
        segments=reindexed,
        empty_dropped=empty_dropped,
        invalid_dropped=invalid_dropped,
        warnings=warnings,
    )
