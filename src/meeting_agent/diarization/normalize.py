from __future__ import annotations

from typing import Any, Iterable

from .schema import DEFAULT_SPEAKER, DiarizationInterval


def _as_float(value: Any, field_name: str, row_index: int) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"diarization interval {row_index}: {field_name} must be numeric") from exc


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_speaker(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return DEFAULT_SPEAKER
    if text.upper().startswith("SPEAKER_"):
        suffix = text.split("_", 1)[1]
        if suffix.isdigit():
            return f"SPEAKER_{int(suffix):02d}"
        return text.upper()
    if text.isdigit():
        return f"SPEAKER_{int(text):02d}"
    return text


def normalize_intervals(
    raw_intervals: Iterable[dict[str, Any]],
    *,
    backend: str,
) -> tuple[list[DiarizationInterval], list[str]]:
    intervals: list[DiarizationInterval] = []
    warnings: list[str] = []

    for row_index, row in enumerate(raw_intervals, start=1):
        try:
            start = round(_as_float(row.get("start"), "start", row_index), 3)
            end = round(_as_float(row.get("end"), "end", row_index), 3)
        except ValueError as exc:
            warnings.append(str(exc))
            continue

        if start < 0:
            warnings.append(f"diarization interval {row_index}: start below zero was clamped")
            start = 0.0
        if end <= start:
            warnings.append(f"diarization interval {row_index}: end must be greater than start")
            continue

        metadata = dict(row.get("metadata", {})) if isinstance(row.get("metadata"), dict) else {}
        intervals.append(
            DiarizationInterval(
                speaker=normalize_speaker(row.get("speaker")),
                start=start,
                end=end,
                confidence=_optional_float(row.get("confidence")),
                backend=str(row.get("backend") or backend),
                metadata=metadata,
            )
        )

    intervals.sort(key=lambda item: (item.start, item.end, item.speaker))
    return intervals, warnings
