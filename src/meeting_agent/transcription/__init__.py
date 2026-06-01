"""Common transcription contract for MeetingAgent."""

from .exporters import (
    build_markdown_transcript,
    build_plain_text_transcript,
    build_srt_transcript,
    build_vtt_transcript,
    write_transcript_exports,
)
from .faster_whisper_backend import FasterWhisperConfig, FasterWhisperResult, transcribe_faster_whisper
from .gigaam_backend import GigaAMConfig, GigaAMResult, transcribe_gigaam
from .glossary import extract_initial_prompt
from .normalize import NormalizationResult, normalize_segments
from .report import build_transcription_report
from .schema import CanonicalSegment, TranscriptDocument, TranscriptionReport

__all__ = [
    "CanonicalSegment",
    "NormalizationResult",
    "TranscriptDocument",
    "TranscriptionReport",
    "FasterWhisperConfig",
    "FasterWhisperResult",
    "GigaAMConfig",
    "GigaAMResult",
    "build_markdown_transcript",
    "build_plain_text_transcript",
    "build_srt_transcript",
    "build_transcription_report",
    "extract_initial_prompt",
    "build_vtt_transcript",
    "normalize_segments",
    "transcribe_faster_whisper",
    "transcribe_gigaam",
    "write_transcript_exports",
]
