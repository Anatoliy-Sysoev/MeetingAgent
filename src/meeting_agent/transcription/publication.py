from __future__ import annotations

from pathlib import Path
from typing import Any

from .checkpoints import CheckpointStore, atomic_json, file_sha256, _read


def publication_path(meeting_dir: Path) -> Path:
    return CheckpointStore(meeting_dir).path("transcript/transcription_state.json")


def begin_publication(meeting_dir: Path) -> None:
    atomic_json(publication_path(meeting_dir), {"version": 1, "state": "pending"})


def complete_publication(meeting_dir: Path, outputs: dict[str, Path]) -> None:
    files = {}
    for key, path in outputs.items():
        relative = path.resolve().relative_to(meeting_dir.resolve()).as_posix()
        files[key] = dict(path=relative, size=path.stat().st_size, sha256=file_sha256(path))
    atomic_json(publication_path(meeting_dir), {"version": 1, "state": "complete", "files": files})


def transcript_is_complete(meeting_dir: Path) -> bool:
    """Legacy cards have no publication marker; new attempts must finish it."""
    try:
        marker = publication_path(meeting_dir)
        if not marker.exists():
            return True
        value: dict[str, Any] = _read(marker, 64 * 1024)
        if value.get("version") != 1 or value.get("state") != "complete":
            return False
        files = value.get("files")
        if not isinstance(files, dict) or "segments" not in files or "report" not in files:
            return False
        for item in files.values():
            path = (meeting_dir / item["path"]).resolve()
            if not path.is_relative_to(meeting_dir.resolve()) or not path.is_file() or path.stat().st_size != item["size"]:
                return False
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False
