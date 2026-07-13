from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterable
from pathlib import Path

from meeting_agent.transcription.exporters import build_srt_transcript, build_vtt_transcript, format_hhmmss
from meeting_agent.transcription.schema import CanonicalSegment

from .schema import LiveSegment, LiveSessionReport


def _atomic_write_chunks(path: Path, chunks: Iterable[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_tmp = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    tmp = Path(raw_tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            for chunk in chunks:
                handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _atomic_write_text(path: Path, content: str) -> None:
    _atomic_write_chunks(path, (content,))


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

    live_partials = output_dir / f"live_partials{suffix}.jsonl"
    _atomic_write_chunks(
        live_partials,
        (
            json.dumps(partial, ensure_ascii=False) + "\n"
            for partial in partials
        ),
    )
    written["live_partials"] = live_partials

    live_transcript = output_dir / f"live_transcript{suffix}.txt"
    _atomic_write_text(live_transcript, build_live_text(segments))
    written["live_transcript"] = live_transcript

    live_srt = output_dir / f"live_subtitles{suffix}.srt"
    _atomic_write_text(live_srt, build_srt_transcript(canonical_segments))
    written["live_srt"] = live_srt

    live_vtt = output_dir / f"live_subtitles{suffix}.vtt"
    _atomic_write_text(live_vtt, build_vtt_transcript(canonical_segments))
    written["live_vtt"] = live_vtt

    live_report = output_dir / f"live_report{suffix}.json"
    _atomic_write_text(
        live_report,
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
    )
    written["live_report"] = live_report

    # Publish the canonical JSONL last. Readers treat it as the commit marker
    # for the rest of the source-scoped artifact set.
    live_segments = output_dir / f"live_segments{suffix}.jsonl"
    _atomic_write_chunks(
        live_segments,
        (
            json.dumps(segment.to_dict(), ensure_ascii=False) + "\n"
            for segment in segments
        ),
    )
    written["live_segments"] = live_segments
    return written
