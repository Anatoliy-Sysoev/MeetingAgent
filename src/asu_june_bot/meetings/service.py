from __future__ import annotations

import datetime
import json
import os
from pathlib import Path
from typing import Any

# Allowlist: only these suffixes are served as text content.
# Anything not listed is treated as binary and refused (415).
_SAFE_ARTIFACT_SUFFIXES = {
    ".md", ".txt", ".json", ".jsonl", ".srt", ".vtt", ".csv", ".yaml", ".yml"
}


def _safe_meeting_id(meeting_id: str) -> bool:
    """Return True if meeting_id contains no traversal sequences."""
    if not meeting_id:
        return False
    p = Path(meeting_id)
    if p.is_absolute():
        return False
    if ".." in p.parts:
        return False
    if "/" in meeting_id or "\\" in meeting_id:
        return False
    return True


def _safe_artifact_name(name: str) -> bool:
    if not name:
        return False
    p = Path(name)
    if p.is_absolute():
        return False
    if ".." in p.parts:
        return False
    if "/" in name or "\\" in name:
        return False
    return True


def _read_meeting_json(card_path: Path) -> dict[str, Any]:
    with card_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("meeting.json root must be an object")
    return data


def _artifact_entry(meeting_dir: Path, key: str, rel_path: str) -> dict[str, Any]:
    abs_path = (meeting_dir / rel_path).resolve()
    # Ensure artifact stays inside meeting dir
    try:
        abs_path.relative_to(meeting_dir.resolve())
    except ValueError:
        return {"key": key, "path": rel_path, "exists": False, "error": "path_traversal"}
    exists = abs_path.exists() and abs_path.is_file()
    entry: dict[str, Any] = {"key": key, "path": rel_path, "exists": exists}
    if exists:
        stat = abs_path.stat()
        entry["size_bytes"] = stat.st_size
        entry["modified_at"] = datetime.datetime.fromtimestamp(
            stat.st_mtime, tz=datetime.timezone.utc
        ).isoformat()
    return entry


class MeetingsService:
    def __init__(self, meetings_root: Path | str | None = None) -> None:
        if meetings_root is None:
            env_root = os.getenv("MEETINGS_ROOT", "").strip()
            meetings_root = env_root if env_root else "meetings"
        self.root = Path(meetings_root)

    def _meeting_dir(self, meeting_id: str) -> Path:
        return self.root / meeting_id

    def _card_path(self, meeting_id: str) -> Path:
        return self._meeting_dir(meeting_id) / "meeting.json"

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def list_meetings(self, offset: int = 0, limit: int = 50) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []

        if not self.root.exists():
            return {"items": [], "total": 0, "offset": offset, "limit": limit}

        dirs = sorted(
            (d for d in self.root.iterdir() if d.is_dir()),
            key=lambda d: d.name,
        )
        for meeting_dir in dirs:
            card_path = meeting_dir / "meeting.json"
            if not card_path.exists():
                continue
            try:
                data = _read_meeting_json(card_path)
                items.append(_summary(data))
            except Exception as exc:
                errors.append({"meeting_id": meeting_dir.name, "error": str(exc)})

        total = len(items)
        page = items[offset: offset + limit]
        result: dict[str, Any] = {
            "items": page,
            "total": total,
            "offset": offset,
            "limit": limit,
        }
        if errors:
            result["errors"] = errors
        return result

    # ------------------------------------------------------------------
    # Detail
    # ------------------------------------------------------------------

    def get_meeting(self, meeting_id: str) -> dict[str, Any] | None:
        if not _safe_meeting_id(meeting_id):
            return None
        card = self._card_path(meeting_id)
        if not card.exists():
            return None
        return _read_meeting_json(card)

    # ------------------------------------------------------------------
    # Artifacts
    # ------------------------------------------------------------------

    def list_artifacts(self, meeting_id: str) -> list[dict[str, Any]] | None:
        if not _safe_meeting_id(meeting_id):
            return None
        card_path = self._card_path(meeting_id)
        if not card_path.exists():
            return None
        data = _read_meeting_json(card_path)
        artifacts_map: dict[str, str] = data.get("artifacts") or {}
        meeting_dir = self._meeting_dir(meeting_id)
        return [
            _artifact_entry(meeting_dir, key, rel)
            for key, rel in artifacts_map.items()
            if rel
        ]

    # ------------------------------------------------------------------
    # Transcript
    # ------------------------------------------------------------------

    def get_transcript(self, meeting_id: str) -> dict[str, Any] | None:
        """Return transcript content or None if not found."""
        if not _safe_meeting_id(meeting_id):
            return None
        card_path = self._card_path(meeting_id)
        if not card_path.exists():
            return None
        data = _read_meeting_json(card_path)
        artifacts: dict[str, str] = data.get("artifacts") or {}
        meeting_dir = self._meeting_dir(meeting_id)

        # Priority: segments.jsonl → transcript_json → transcript_txt → transcript (md)
        for key in ("segments", "transcript_json", "transcript_txt", "transcript"):
            rel = artifacts.get(key)
            if not rel:
                continue
            abs_path = (meeting_dir / rel).resolve()
            try:
                abs_path.relative_to(meeting_dir.resolve())
            except ValueError:
                continue
            if not abs_path.exists():
                continue
            content_type = _detect_content_type(abs_path)
            if content_type is None:
                continue
            text = abs_path.read_text(encoding="utf-8", errors="replace")
            if content_type == "jsonl":
                lines = [json.loads(ln) for ln in text.splitlines() if ln.strip()]
                return {"artifact": key, "format": "jsonl", "segments": lines}
            if content_type == "json":
                return {"artifact": key, "format": "json", "content": json.loads(text)}
            return {"artifact": key, "format": "text", "content": text}
        return {"artifact": None, "format": None, "content": None, "available": False}

    # ------------------------------------------------------------------
    # Artifact content
    # ------------------------------------------------------------------

    def get_artifact_content(self, meeting_id: str, artifact_name: str) -> dict[str, Any] | None:
        """Return content of a named artifact (text only, no binary)."""
        if not _safe_meeting_id(meeting_id) or not _safe_artifact_name(artifact_name):
            return None
        card_path = self._card_path(meeting_id)
        if not card_path.exists():
            return None
        data = _read_meeting_json(card_path)
        artifacts: dict[str, str] = data.get("artifacts") or {}
        rel = artifacts.get(artifact_name)
        if not rel:
            return None
        meeting_dir = self._meeting_dir(meeting_id)
        abs_path = (meeting_dir / rel).resolve()
        try:
            abs_path.relative_to(meeting_dir.resolve())
        except ValueError:
            return None
        if not abs_path.exists():
            return None
        suffix = abs_path.suffix.lower()
        if suffix not in _SAFE_ARTIFACT_SUFFIXES:
            return {"error": "binary_artifact", "key": artifact_name}
        text = abs_path.read_text(encoding="utf-8", errors="replace")
        fmt = "jsonl" if suffix == ".jsonl" else ("json" if suffix == ".json" else "text")
        return {"artifact": artifact_name, "format": fmt, "content": text}


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _detect_content_type(path: Path) -> str | None:
    """Return format string for allowlisted suffixes, None for everything else."""
    suffix = path.suffix.lower()
    if suffix not in _SAFE_ARTIFACT_SUFFIXES:
        return None
    if suffix == ".jsonl":
        return "jsonl"
    if suffix == ".json":
        return "json"
    return "text"


def _summary(data: dict[str, Any]) -> dict[str, Any]:
    artifacts: dict[str, str] = data.get("artifacts") or {}
    media_files: list[dict] = (data.get("source") or {}).get("media_files") or []
    result: dict[str, Any] = {
        "meeting_id": data.get("meeting_id"),
        "title": data.get("title"),
        "date": data.get("date"),
        "processing_status": data.get("processing_status"),
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
        "artifacts_count": len([v for v in artifacts.values() if v]),
        "artifact_keys": list(artifacts.keys()),
    }
    if media_files:
        result["media_files"] = [
            {"path": f.get("path"), "media_type": f.get("media_type"), "sha256": f.get("sha256")}
            for f in media_files
        ]
    last_error = data.get("last_error")
    if last_error:
        result["last_error"] = last_error
    return result
