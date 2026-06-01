from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .schema import CanonicalSegment, TranscriptDocument


def format_hhmmss(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def format_srt_time(seconds: float) -> str:
    milliseconds_total = max(0, int(round(seconds * 1000)))
    hours = milliseconds_total // 3_600_000
    minutes = (milliseconds_total % 3_600_000) // 60_000
    secs = (milliseconds_total % 60_000) // 1000
    millis = milliseconds_total % 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def format_vtt_time(seconds: float) -> str:
    return format_srt_time(seconds).replace(",", ".")


def build_plain_text_transcript(segments: Iterable[CanonicalSegment]) -> str:
    lines = [segment.text for segment in segments if segment.text.strip()]
    return "\n".join(lines).rstrip() + ("\n" if lines else "")


def build_markdown_transcript(
    document: TranscriptDocument,
    *,
    include_metadata: bool = True,
) -> str:
    lines: list[str] = [f"# Транскрипт: {document.title}", ""]
    if include_metadata:
        lines.extend(
            [
                f"- meeting_id: `{document.meeting_id}`",
                f"- engine: `{document.engine}`",
                f"- model: `{document.model or ''}`",
                f"- language: `{document.language or ''}`",
                "",
            ]
        )
    for segment in document.segments:
        lines.append(f"[{format_hhmmss(segment.start)}] {segment.text}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_srt_transcript(segments: Iterable[CanonicalSegment]) -> str:
    blocks: list[str] = []
    for index, segment in enumerate(segments, start=1):
        blocks.append(
            "\n".join(
                [
                    str(index),
                    f"{format_srt_time(segment.start)} --> {format_srt_time(segment.end)}",
                    segment.text,
                ]
            )
        )
    return "\n\n".join(blocks).rstrip() + ("\n" if blocks else "")


def build_vtt_transcript(segments: Iterable[CanonicalSegment]) -> str:
    blocks = ["WEBVTT", ""]
    for segment in segments:
        blocks.extend(
            [
                f"{format_vtt_time(segment.start)} --> {format_vtt_time(segment.end)}",
                segment.text,
                "",
            ]
        )
    return "\n".join(blocks).rstrip() + "\n"


def write_jsonl(path: Path, segments: Iterable[CanonicalSegment]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for segment in segments:
            fh.write(json.dumps(segment.to_dict(), ensure_ascii=False) + "\n")


def write_transcript_exports(
    output_dir: Path,
    document: TranscriptDocument,
    *,
    formats: set[str] | None = None,
) -> dict[str, Path]:
    selected = formats or {"jsonl", "json", "txt", "md", "srt", "vtt"}
    output_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}

    if "jsonl" in selected:
        path = output_dir / "segments.jsonl"
        write_jsonl(path, document.segments)
        written["segments"] = path
    if "json" in selected:
        path = output_dir / "transcript.json"
        path.write_text(json.dumps(document.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written["transcript_json"] = path
    if "txt" in selected:
        path = output_dir / "transcript.txt"
        path.write_text(build_plain_text_transcript(document.segments), encoding="utf-8")
        written["transcript_txt"] = path
    if "md" in selected:
        path = output_dir / "transcript.md"
        path.write_text(build_markdown_transcript(document), encoding="utf-8")
        written["transcript_md"] = path
    if "srt" in selected:
        path = output_dir / "transcript.srt"
        path.write_text(build_srt_transcript(document.segments), encoding="utf-8")
        written["transcript_srt"] = path
    if "vtt" in selected:
        path = output_dir / "transcript.vtt"
        path.write_text(build_vtt_transcript(document.segments), encoding="utf-8")
        written["transcript_vtt"] = path

    return written
