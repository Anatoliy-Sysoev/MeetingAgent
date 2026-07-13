"""Common transcription contract for MeetingAgent."""

from .exporters import (
    build_markdown_transcript,
    build_plain_text_transcript,
    build_srt_transcript,
    build_vtt_transcript,
    write_transcript_exports,
)
from .faster_whisper_backend import (
    DEFAULT_FASTER_WHISPER_MODEL,
    FasterWhisperConfig,
    FasterWhisperResult,
    transcribe_faster_whisper,
)
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
from .refinement import (
    LiveRefinementError,
    begin_live_refinement,
    can_resume_live_refinement,
    complete_live_refinement,
    expected_live_audio_relative_path,
    fail_live_refinement,
    live_refinement_status,
    offline_model_for_engine,
    prepare_live_refinement,
    refinement_artifact_keys,
)
from .report import build_transcription_report
from .schema import CanonicalSegment, TranscriptDocument, TranscriptionReport

__all__ = [
    "CanonicalSegment",
    "NormalizationResult",
    "TranscriptDocument",
    "TranscriptionReport",
    "DEFAULT_FASTER_WHISPER_MODEL",
    "FasterWhisperConfig",
    "FasterWhisperResult",
    "GigaAMConfig",
    "GigaAMResult",
    "AnonymizationOptions",
    "AnonymizationResult",
    "TranscriptAnonymizer",
    "LiveRefinementError",
    "begin_live_refinement",
    "build_anonymization_report",
    "build_markdown_transcript",
    "build_plain_text_transcript",
    "build_srt_transcript",
    "build_transcription_report",
    "can_resume_live_refinement",
    "complete_live_refinement",
    "expected_live_audio_relative_path",
    "fail_live_refinement",
    "extract_initial_prompt",
    "HotwordsConfig",
    "HotwordsConfigError",
    "load_hotwords_config",
    "live_refinement_status",
    "load_terms_file",
    "merge_terms",
    "read_jsonl_rows",
    "terms_from_meeting_card",
    "build_vtt_transcript",
    "normalize_segments",
    "offline_model_for_engine",
    "prepare_live_refinement",
    "refinement_artifact_keys",
    "transcribe_faster_whisper",
    "transcribe_gigaam",
    "write_transcript_exports",
    "write_anonymization_report",
    "write_jsonl_rows",
]
