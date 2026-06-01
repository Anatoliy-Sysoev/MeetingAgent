"""Common transcription contract for MeetingAgent."""

from .exporters import (
    build_markdown_transcript,
    build_plain_text_transcript,
    build_srt_transcript,
    build_vtt_transcript,
    write_transcript_exports,
)
from .normalize import NormalizationResult, normalize_segments
from .report import build_transcription_report
from .schema import CanonicalSegment, TranscriptDocument, TranscriptionReport

__all__ = [
    "CanonicalSegment",
    "NormalizationResult",
    "TranscriptDocument",
    "TranscriptionReport",
    "build_markdown_transcript",
    "build_plain_text_transcript",
    "build_srt_transcript",
    "build_transcription_report",
    "build_vtt_transcript",
    "normalize_segments",
    "write_transcript_exports",
]
