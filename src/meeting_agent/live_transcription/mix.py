from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .exporters import write_live_artifacts
from .schema import LiveSegment, LiveSessionReport


LIVE_MIX_SOURCE_MAX_BYTES = 16 * 1024 * 1024
LIVE_MIX_DERIVED_MAX_BYTES = 48 * 1024 * 1024
LIVE_MIX_REPORT_MAX_BYTES = 64 * 1024
LIVE_MIX_SOURCE_SEGMENTS_MAX = 10_000
LIVE_MIX_DERIVED_SEGMENTS_MAX = 20_000
LIVE_MIX_TEXT_MAX = 20_000
LIVE_MIX_ID_MAX = 180
LIVE_MIX_CLOCK_OFFSET_MAX_SECONDS = 7 * 24 * 60 * 60
_SOURCES = ("MIC", "SYS")
_MIX_WARNING_CODES = frozenset(
    {
        "mic_segments_missing",
        "sys_segments_missing",
        "mic_segments_empty",
        "sys_segments_empty",
        "mic_clock_missing",
        "sys_clock_missing",
        "source_segments_invalid",
        "source_clock_out_of_range",
        "derived_segments_invalid",
    }
)


class LiveMixError(RuntimeError):
    pass


@dataclass(frozen=True)
class LiveMixBuildResult:
    segments: list[LiveSegment]
    written: dict[str, Path]
    sources_present: tuple[str, ...]
    warnings: tuple[str, ...]


def _bounded_text(value: Any, maximum: int) -> str:
    return " ".join(str(value or "").split())[:maximum]


def _finite_number(value: Any) -> float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _safe_input_path(path: Path, root: Path) -> Path:
    if path.is_symlink():
        raise LiveMixError("Live timeline source must not be a symbolic link")
    resolved_root = root.resolve()
    resolved = path.resolve()
    if resolved_root != resolved.parent and resolved_root not in resolved.parents:
        raise LiveMixError("Live timeline source escaped its artifact directory")
    return resolved


def _read_bounded_jsonl(
    path: Path,
    *,
    root: Path,
    max_bytes: int,
    max_segments: int,
) -> tuple[list[dict[str, Any]], int]:
    if not path.is_file():
        return [], 0
    safe_path = _safe_input_path(path, root)
    with safe_path.open("rb") as handle:
        payload = handle.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise LiveMixError("Live source transcript exceeds the MIX derivation limit")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LiveMixError("Live source transcript is not valid UTF-8") from exc

    rows: list[dict[str, Any]] = []
    invalid = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        if len(rows) >= max_segments:
            raise LiveMixError("Live source transcript has too many segments")
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            invalid += 1
            continue
        if isinstance(row, dict):
            rows.append(row)
        else:
            invalid += 1
    return rows, invalid


def _parse_iso_timestamp(value: Any) -> datetime | None:
    text = _bounded_text(value, 80)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _read_source_started_at(output_dir: Path, source: str) -> datetime | None:
    path = output_dir / f"live_report.{source}.json"
    if not path.is_file():
        return None
    safe_path = _safe_input_path(path, output_dir)
    with safe_path.open("rb") as handle:
        payload = handle.read(LIVE_MIX_REPORT_MAX_BYTES + 1)
    if len(payload) > LIVE_MIX_REPORT_MAX_BYTES:
        raise LiveMixError("Live source report exceeds the MIX derivation limit")
    try:
        report = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LiveMixError("Live source report is invalid") from exc
    if not isinstance(report, dict) or str(report.get("source") or "").upper() != source:
        return None
    return _parse_iso_timestamp(report.get("started_at"))


def _source_segment(
    row: dict[str, Any],
    source: str,
    *,
    offset_seconds: float = 0.0,
    source_started_at: str | None = None,
) -> LiveSegment | None:
    if str(row.get("source") or "").upper() != source:
        return None
    origin_id = _bounded_text(row.get("segment_id"), LIVE_MIX_ID_MAX)
    text = _bounded_text(row.get("text"), LIVE_MIX_TEXT_MAX)
    start = _finite_number(row.get("start"))
    end = _finite_number(row.get("end"))
    if not origin_id or not text or start is None or end is None:
        return None
    if start < 0 or end <= start or end > 7 * 24 * 60 * 60:
        return None

    confidence = _finite_number(row.get("confidence"))
    if confidence is not None and not 0 <= confidence <= 1:
        confidence = None
    model = _bounded_text(row.get("model"), 160) or None
    created_at = _bounded_text(row.get("created_at"), 80) or None
    digest = hashlib.sha256(f"{source}\0{origin_id}".encode("utf-8")).hexdigest()[:16]
    return LiveSegment(
        segment_id=f"live-mix-{source.lower()}-{digest}",
        segment_index=0,
        start=round(start + offset_seconds, 3),
        end=round(end + offset_seconds, 3),
        text=text,
        source=source,
        engine=_bounded_text(row.get("engine"), 80) or "vosk",
        model=model,
        confidence=confidence,
        is_final=True,
        created_at=created_at,
        metadata={
            "derived_track": "MIX",
            "origin_source": source,
            "origin_segment_id": origin_id,
            "origin_start": round(start, 3),
            "origin_end": round(end, 3),
            "source_offset_seconds": round(offset_seconds, 3),
            "source_started_at": source_started_at,
        },
    )


def merge_live_source_segments(
    mic_rows: list[dict[str, Any]],
    sys_rows: list[dict[str, Any]],
    *,
    source_offsets: dict[str, float] | None = None,
    source_started_at: dict[str, str] | None = None,
) -> tuple[list[LiveSegment], int]:
    merged: list[LiveSegment] = []
    invalid = 0
    seen: set[tuple[str, str]] = set()
    offsets = source_offsets or {}
    started_at = source_started_at or {}
    for source, rows in (("MIC", mic_rows), ("SYS", sys_rows)):
        for row in rows:
            segment = _source_segment(
                row,
                source,
                offset_seconds=max(0.0, float(offsets.get(source, 0.0))),
                source_started_at=started_at.get(source),
            )
            if segment is None:
                invalid += 1
                continue
            origin_id = str(segment.metadata["origin_segment_id"])
            identity = (source, origin_id)
            if identity in seen:
                invalid += 1
                continue
            seen.add(identity)
            merged.append(segment)

    merged.sort(
        key=lambda segment: (
            segment.start,
            0 if segment.source == "MIC" else 1,
            str(segment.metadata["origin_segment_id"]),
            segment.end,
        )
    )
    return [
        replace(segment, segment_index=index)
        for index, segment in enumerate(merged)
    ], invalid


def build_derived_mix_artifacts(
    output_dir: Path,
    *,
    generated_at: str,
) -> LiveMixBuildResult | None:
    source_rows: dict[str, list[dict[str, Any]]] = {}
    sources_present: list[str] = []
    warnings: list[str] = []
    invalid_rows = 0
    source_datetimes: dict[str, datetime] = {}
    for source in _SOURCES:
        path = output_dir / f"live_segments.{source}.jsonl"
        if not path.is_file():
            source_rows[source] = []
            warnings.append(f"{source.lower()}_segments_missing")
            continue
        sources_present.append(source)
        rows, invalid = _read_bounded_jsonl(
            path,
            root=output_dir,
            max_bytes=LIVE_MIX_SOURCE_MAX_BYTES,
            max_segments=LIVE_MIX_SOURCE_SEGMENTS_MAX,
        )
        source_rows[source] = rows
        invalid_rows += invalid
        if not rows:
            warnings.append(f"{source.lower()}_segments_empty")
        started_at = _read_source_started_at(output_dir, source)
        if started_at is None:
            warnings.append(f"{source.lower()}_clock_missing")
        else:
            source_datetimes[source] = started_at

    if not sources_present:
        return None

    timeline_start = min(source_datetimes.values(), default=_parse_iso_timestamp(generated_at))
    if timeline_start is None:
        raise LiveMixError("MIX generation timestamp is invalid")
    source_offsets = {
        source: max(0.0, (started - timeline_start).total_seconds())
        for source, started in source_datetimes.items()
    }
    if any(
        offset > LIVE_MIX_CLOCK_OFFSET_MAX_SECONDS
        for offset in source_offsets.values()
    ):
        warnings.append("source_clock_out_of_range")
        source_offsets = {
            source: 0.0
            for source in source_offsets
        }
    source_started_at = {
        source: started.isoformat()
        for source, started in source_datetimes.items()
    }
    segments, rejected = merge_live_source_segments(
        source_rows["MIC"],
        source_rows["SYS"],
        source_offsets=source_offsets,
        source_started_at=source_started_at,
    )
    invalid_rows += rejected
    if invalid_rows:
        warnings.append("source_segments_invalid")
    duration = max((segment.end for segment in segments), default=0.0)
    report = LiveSessionReport(
        engine="derived-live-timeline",
        model=None,
        source="MIX",
        sample_rate=0,
        block_ms=0,
        duration_seconds=round(duration, 3),
        segments_count=len(segments),
        partials_count=0,
        chars_count=sum(len(segment.text) for segment in segments),
        started_at=timeline_start.isoformat(),
        finished_at=generated_at,
        elapsed_seconds=0.0,
        warnings=warnings,
        backend_metrics={
            "derived": True,
            "mic_segments": sum(1 for segment in segments if segment.source == "MIC"),
            "sys_segments": sum(1 for segment in segments if segment.source == "SYS"),
            "invalid_rows": invalid_rows,
            "source_offsets_seconds": {
                source: round(source_offsets.get(source, 0.0), 3)
                for source in sources_present
            },
            "source_started_at": source_started_at,
        },
    )
    written = write_live_artifacts(
        output_dir,
        segments,
        [],
        report,
        source="MIX",
    )
    return LiveMixBuildResult(
        segments=segments,
        written=written,
        sources_present=tuple(sources_present),
        warnings=tuple(warnings),
    )


def read_derived_mix_timeline(
    output_dir: Path,
    *,
    after: int = 0,
    limit: int = 200,
) -> dict[str, Any]:
    if after < 0 or not 1 <= limit <= 1_000:
        raise ValueError("Invalid live timeline pagination")
    rows, invalid = _read_bounded_jsonl(
        output_dir / "live_segments.MIX.jsonl",
        root=output_dir,
        max_bytes=LIVE_MIX_DERIVED_MAX_BYTES,
        max_segments=LIVE_MIX_DERIVED_SEGMENTS_MAX,
    )
    safe_rows: list[dict[str, Any]] = []
    for row in rows:
        source = str(row.get("source") or "").upper()
        segment_id = _bounded_text(row.get("segment_id"), LIVE_MIX_ID_MAX)
        text = _bounded_text(row.get("text"), LIVE_MIX_TEXT_MAX)
        start = _finite_number(row.get("start"))
        end = _finite_number(row.get("end"))
        if (
            source not in _SOURCES
            or not segment_id
            or not text
            or start is None
            or end is None
            or start < 0
            or end <= start
        ):
            invalid += 1
            continue
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        origin_id = _bounded_text(metadata.get("origin_segment_id"), LIVE_MIX_ID_MAX)
        origin_start = _finite_number(metadata.get("origin_start"))
        origin_end = _finite_number(metadata.get("origin_end"))
        if (
            not origin_id
            or origin_start is None
            or origin_end is None
            or origin_start < 0
            or origin_end <= origin_start
        ):
            invalid += 1
            continue
        confidence = _finite_number(row.get("confidence"))
        if confidence is not None and not 0 <= confidence <= 1:
            confidence = None
        safe_rows.append(
            {
                "segment_id": segment_id,
                "origin_segment_id": origin_id,
                "source": source,
                "start": round(start, 3),
                "end": round(end, 3),
                "origin_start": round(origin_start, 3),
                "origin_end": round(origin_end, 3),
                "text": text,
                "confidence": confidence,
            }
        )

    safe_rows.sort(
        key=lambda row: (
            row["start"],
            0 if row["source"] == "MIC" else 1,
            row["origin_segment_id"],
            row["end"],
        )
    )

    total = len(safe_rows)
    page = safe_rows[after : after + limit]
    next_after = after + len(page)
    timeline_started_at: str | None = None
    report_warnings: list[str] = []
    report_path = output_dir / "live_report.MIX.json"
    if report_path.is_file():
        safe_report = _safe_input_path(report_path, output_dir)
        with safe_report.open("rb") as handle:
            report_payload = handle.read(LIVE_MIX_REPORT_MAX_BYTES + 1)
        if len(report_payload) <= LIVE_MIX_REPORT_MAX_BYTES:
            try:
                report = json.loads(report_payload.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                report = None
            if (
                isinstance(report, dict)
                and str(report.get("source") or "").upper() == "MIX"
                and _parse_iso_timestamp(report.get("started_at"))
            ):
                timeline_started_at = _bounded_text(report.get("started_at"), 80)
                raw_warnings = report.get("warnings")
                if isinstance(raw_warnings, list):
                    report_warnings = [
                        warning
                        for warning in (
                            _bounded_text(value, 80) for value in raw_warnings[:50]
                        )
                        if warning in _MIX_WARNING_CODES
                    ]

    warnings = list(dict.fromkeys(report_warnings))
    if invalid and "derived_segments_invalid" not in warnings:
        warnings.append("derived_segments_invalid")

    return {
        "source": "MIX",
        "timeline_started_at": timeline_started_at,
        "segments": page,
        "after": after,
        "next_after": next_after,
        "total": total,
        "truncated": next_after < total,
        "warnings": warnings,
    }
