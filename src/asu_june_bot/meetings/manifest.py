"""Meeting artifact manifest — stable artifact contract for the Workspace UI
(MA-MEETING-ARTIFACT-CONTRACT, #119).

One endpoint tells the UI which artifacts exist per pipeline stage instead of
the UI guessing from files.  Entries carry only meeting-relative knowledge:
no absolute paths or private filesystem details ever leave this module.
"""
from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

from asu_june_bot.meetings.service import _artifact_map

# Curated catalog: artifact_key → (title, stage, default relative path,
# content_type).  The meeting card's artifacts map overrides the default
# path when it names the same key.
_CATALOG: list[dict[str, Any]] = [
    {"artifact_key": "segments", "title": "Transcript segments", "stage": "transcribe",
     "default_path": "transcript/segments.jsonl", "content_type": "jsonl"},
    {"artifact_key": "transcript_txt", "title": "Transcript (plain text)", "stage": "transcribe",
     "default_path": "transcript/transcript.txt", "content_type": "text"},
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


def _safe_rel_target(meeting_dir: Path, rel: str) -> Path | None:
    """Resolve rel inside meeting_dir; None on traversal/absolute values."""
    rel_path = Path(str(rel).replace("\\", "/"))
    if rel_path.is_absolute() or ".." in rel_path.parts:
        return None
    target = (meeting_dir / rel_path).resolve()
    try:
        target.relative_to(meeting_dir.resolve())
    except ValueError:
        return None
    return target


def _entry(
    meeting_id: str,
    meeting_dir: Path,
    spec: dict[str, Any],
    artifacts_map: dict[str, Any],
) -> dict[str, Any]:
    key = spec["artifact_key"]
    rel = artifacts_map.get(key) or spec["default_path"]
    entry: dict[str, Any] = {
        "artifact_key": key,
        "title": spec["title"],
        "stage": spec["stage"],
        "content_type": spec["content_type"],
        "exists": False,
        "size_bytes": None,
        "updated_at": None,
        "view_url": None,
        "download_url": None,
    }
    target = _safe_rel_target(meeting_dir, str(rel))
    if target is None:
        # Malformed/traversal path in the card: report as absent, no details.
        entry["error"] = "invalid_artifact_path"
        return entry
    if target.exists() and target.is_file():
        stat = target.stat()
        entry["exists"] = True
        entry["size_bytes"] = stat.st_size
        entry["updated_at"] = datetime.datetime.fromtimestamp(
            stat.st_mtime, tz=datetime.timezone.utc
        ).isoformat(timespec="seconds")
        url = f"/meetings/{meeting_id}/artifacts/{key}"
        entry["view_url"] = url
        entry["download_url"] = url
    return entry


def build_artifact_manifest(
    meeting_id: str,
    meeting_dir: Path,
    card: dict[str, Any],
) -> dict[str, Any]:
    """Build the full manifest for one meeting.

    Includes an ``index_status`` pseudo-artifact derived from
    ``rag.indexed_artifacts`` in the meeting card (no backing file).
    """
    artifacts_map = _artifact_map(card)
    entries = [_entry(meeting_id, meeting_dir, spec, artifacts_map) for spec in _CATALOG]

    rag = card.get("rag")
    indexed = rag.get("indexed_artifacts") if isinstance(rag, dict) else None
    entries.append(
        {
            "artifact_key": "index_status",
            "title": "Search index",
            "stage": "index",
            "content_type": "status",
            "exists": bool(indexed),
            "size_bytes": None,
            "updated_at": None,
            "view_url": None,
            "download_url": None,
        }
    )
    return {
        "meeting_id": meeting_id,
        "artifacts": entries,
    }
