"""Shared meeting artifact catalog (MA-MEETING-ARTIFACT-CONTRACT, #119).

Single source of truth for artifact keys, their pipeline stage, default
meeting-relative path and content type.  Used by both the manifest builder
(``meetings/manifest.py``) and the artifact viewer resolver
(``MeetingsService.get_artifact_content``) so a manifest ``view_url`` is
always served by the viewer endpoint — including default-path artifacts that
are not (yet) registered in ``meeting.json.artifacts``.
"""
from __future__ import annotations

ARTIFACT_CATALOG: list[dict[str, str]] = [
    {"artifact_key": "segments", "title": "Transcript segments", "stage": "transcribe",
     "default_path": "transcript/segments.jsonl", "content_type": "jsonl"},
    {"artifact_key": "transcript_txt", "title": "Transcript (plain text)", "stage": "transcribe",
     "default_path": "transcript/transcript.txt", "content_type": "text"},
    {"artifact_key": "transcription_report", "title": "Transcription report", "stage": "transcribe",
     "default_path": "transcript/transcription_report.json", "content_type": "json"},
    {"artifact_key": "live_refinement_mic", "title": "MIC refinement report", "stage": "transcribe",
     "default_path": "transcript/live/refinement.MIC.json", "content_type": "json"},
    {"artifact_key": "live_refinement_sys", "title": "SYS refinement report", "stage": "transcribe",
     "default_path": "transcript/live/refinement.SYS.json", "content_type": "json"},
    {"artifact_key": "diarization", "title": "Diarization", "stage": "diarize",
     "default_path": "transcript/diarization.jsonl", "content_type": "jsonl"},
    {"artifact_key": "speaker_transcript", "title": "Speaker transcript", "stage": "merge",
     "default_path": "transcript/speaker_transcript.jsonl", "content_type": "jsonl"},
    {"artifact_key": "chunks", "title": "Transcript chunks", "stage": "chunk",
     "default_path": "transcript/chunks.jsonl", "content_type": "jsonl"},
    {"artifact_key": "enriched_chunks", "title": "Enriched chunks", "stage": "enrich",
     "default_path": "artifacts/enriched_chunks.jsonl", "content_type": "jsonl"},
    {"artifact_key": "memo", "title": "Summary", "stage": "analyze",
     "default_path": "artifacts/summary.md", "content_type": "markdown"},
    {"artifact_key": "protocol", "title": "Protocol", "stage": "analyze",
     "default_path": "artifacts/protocol.md", "content_type": "markdown"},
    {"artifact_key": "decisions", "title": "Decisions", "stage": "analyze",
     "default_path": "artifacts/decisions.json", "content_type": "json"},
    {"artifact_key": "tasks", "title": "Tasks", "stage": "analyze",
     "default_path": "artifacts/tasks.json", "content_type": "json"},
    {"artifact_key": "risks", "title": "Risks", "stage": "analyze",
     "default_path": "artifacts/risks.json", "content_type": "json"},
    {"artifact_key": "open_questions", "title": "Open questions", "stage": "analyze",
     "default_path": "artifacts/open_questions.json", "content_type": "json"},
]

# artifact_key → default meeting-relative path (viewer fallback resolver).
ARTIFACT_DEFAULT_PATHS: dict[str, str] = {
    spec["artifact_key"]: spec["default_path"] for spec in ARTIFACT_CATALOG
}
