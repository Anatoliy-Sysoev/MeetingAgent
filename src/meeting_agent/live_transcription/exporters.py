from __future__ import annotations

import json
from pathlib import Path

from meeting_agent.transcription.exporters import build_srt_transcript, build_vtt_transcript, format_hhmmss
from meeting_agent.transcription.schema import CanonicalSegment

from .schema import LiveSegment, LiveSessionReport


def _canonical(segment: LiveSegment) -> CanonicalSegment:
    return CanonicalSegment(
        segment_id=segment.segment_id,
        segment_index=segment.segment_index,
        start=segment.start,
        end=segment.end,
        text=segment.text,
        source=segment.source,
        engine=segment.engine,
        confidence=segment.confidence,
        metadata=segment.metadata,
    )


def build_live_text(segments: list[LiveSegment]) -> str:
    lines: list[str] = []
    for segment in segments:
        text = segment.text.strip()
        if not text:
            continue
        lines.append(f"[{format_hhmmss(segment.start)}] {segment.source}: {text}")
    return "\n".join(lines).rstrip() + ("\n" if lines else "")


def write_live_artifacts(
    output_dir: Path,
    segments: list[LiveSegment],
    partials: list[dict],
    report: LiveSessionReport,
    *,
    source: str | None = None,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    canonical_segments = [_canonical(segment) for segment in segments]
    written: dict[str, Path] = {}
    suffix = f".{source}" if source else ""

    live_segments = output_dir / f"live_segments{suffix}.jsonl"
    with live_segments.open("w", encoding="utf-8", newline="\n") as fh:
        for segment in segments:
            fh.write(json.dumps(segment.to_dict(), ensure_ascii=False) + "\n")
    written["live_segments"] = live_segments

    live_partials = output_dir / f"live_partials{suffix}.jsonl"
    with live_partials.open("w", encoding="utf-8", newline="\n") as fh:
        for partial in partials:
            fh.write(json.dumps(partial, ensure_ascii=False) + "\n")
    written["live_partials"] = live_partials

    live_transcript = output_dir / f"live_transcript{suffix}.txt"
    live_transcript.write_text(build_live_text(segments), encoding="utf-8")
    written["live_transcript"] = live_transcript

    live_srt = output_dir / f"live_subtitles{suffix}.srt"
    live_srt.write_text(build_srt_transcript(canonical_segments), encoding="utf-8")
    written["live_srt"] = live_srt

    live_vtt = output_dir / f"live_subtitles{suffix}.vtt"
    live_vtt.write_text(build_vtt_transcript(canonical_segments), encoding="utf-8")
    written["live_vtt"] = live_vtt

    live_report = output_dir / f"live_report{suffix}.json"
    live_report.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    written["live_report"] = live_report
    return written
