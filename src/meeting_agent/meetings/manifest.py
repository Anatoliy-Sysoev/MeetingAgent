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

from meeting_agent.meetings.artifact_catalog import (
    ARTIFACT_CATALOG,
    ARTIFACT_DEFAULT_PATHS,
    STRUCTURED_INDEX_ARTIFACT_KEYS,
)
from meeting_agent.meetings.service import _artifact_map

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
    entries = [_entry(meeting_id, meeting_dir, spec, artifacts_map) for spec in ARTIFACT_CATALOG]

    rag = card.get("rag")
    indexed = rag.get("indexed_artifacts") if isinstance(rag, dict) else None
    indexed_set = {
        str(value) for value in indexed
    } if isinstance(indexed, list) else set()
    structured_index_markers = {
        str(artifacts_map.get(key) or ARTIFACT_DEFAULT_PATHS[key])
        for key in STRUCTURED_INDEX_ARTIFACT_KEYS
    }
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
    entries.append(
        {
            "artifact_key": "structured_index_status",
            "title": "Structured artifact search index",
            "stage": "index_artifacts",
            "content_type": "status",
            "exists": structured_index_markers.issubset(indexed_set),
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
