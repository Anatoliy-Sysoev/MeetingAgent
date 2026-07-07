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
from .hotwords import HotwordsConfig, HotwordsConfigError, load_hotwords_config
from .anonymize import (
    AnonymizationOptions,
    AnonymizationResult,
    TranscriptAnonymizer,
    build_report as build_anonymization_report,
    load_terms_file,
    merge_terms,
    read_jsonl_rows,
    terms_from_meeting_card,
    write_json_atomic as write_anonymization_report,
    write_jsonl_rows,
)
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
    "AnonymizationOptions",
    "AnonymizationResult",
    "TranscriptAnonymizer",
    "build_anonymization_report",
    "build_markdown_transcript",
    "build_plain_text_transcript",
    "build_srt_transcript",
    "build_transcription_report",
    "extract_initial_prompt",
    "HotwordsConfig",
    "HotwordsConfigError",
    "load_hotwords_config",
    "load_terms_file",
    "merge_terms",
    "read_jsonl_rows",
    "terms_from_meeting_card",
    "build_vtt_transcript",
    "normalize_segments",
    "transcribe_faster_whisper",
    "transcribe_gigaam",
    "write_transcript_exports",
    "write_anonymization_report",
    "write_jsonl_rows",
]
