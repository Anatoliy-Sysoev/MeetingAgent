from __future__ import annotations

import datetime
import json
import re
import shutil
from pathlib import Path
from typing import Any

import jsonschema

SUPPORTED_MEDIA_EXTENSIONS = frozenset({".mp4", ".mp3", ".wav", ".m4a"})
_VIDEO_EXTENSIONS = frozenset({".mp4"})

# Allowlist: only these suffixes are served as text content.
_SAFE_ARTIFACT_SUFFIXES = frozenset({
    ".md", ".txt", ".json", ".jsonl", ".srt", ".vtt", ".csv", ".yaml", ".yml"
})

_CYRILLIC_TRANSLIT: dict[str, str] = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d",
    "е": "e", "ё": "e", "ж": "zh", "з": "z", "и": "i",
    "й": "y", "к": "k", "л": "l", "м": "m", "н": "n",
    "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch",
    "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "",
    "э": "e", "ю": "yu", "я": "ya",
}

_SCHEMA_PATH = Path(__file__).resolve().parents[3] / "configs" / "schemas" / "meeting.schema.json"


class MeetingCardError(ValueError):
    """Raised when meeting.json cannot be parsed or has wrong root type."""


def _safe_meeting_id(meeting_id: str) -> bool:
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


def _slugify(value: str) -> str:
    lowered = value.strip().lower()
    transliterated = "".join(_CYRILLIC_TRANSLIT.get(c, c) for c in lowered)
    slug = re.sub(r"[^a-z0-9]+", "-", transliterated)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")[:40]
    return slug


def _media_type_for(suffix: str) -> str:
    return "video" if suffix in _VIDEO_EXTENSIONS else "audio"


def _read_meeting_json(card_path: Path) -> dict[str, Any]:
    try:
        with card_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise MeetingCardError(f"JSON parse error in {card_path.name}: {exc}") from exc
    if not isinstance(data, dict):
        raise MeetingCardError(f"meeting.json root must be an object, got {type(data).__name__}")
    return data


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


def _artifact_entry(meeting_dir: Path, key: str, rel_path: str) -> dict[str, Any]:
    abs_path = (meeting_dir / rel_path).resolve()
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


class MeetingsService:
    def __init__(self, meetings_root: Path | str = "meetings") -> None:
        self.root = Path(meetings_root)

    def _meeting_dir(self, meeting_id: str) -> Path:
        return self.root / meeting_id

    def _card_path(self, meeting_id: str) -> Path:
        return self._meeting_dir(meeting_id) / "meeting.json"

    # ------------------------------------------------------------------
    # Read-only API
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

    def get_meeting(self, meeting_id: str) -> dict[str, Any] | None:
        if not _safe_meeting_id(meeting_id):
            return None
        card = self._card_path(meeting_id)
        if not card.exists():
            return None
        return _read_meeting_json(card)

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

    def get_transcript(self, meeting_id: str) -> dict[str, Any] | None:
        if not _safe_meeting_id(meeting_id):
            return None
        card_path = self._card_path(meeting_id)
        if not card_path.exists():
            return None
        data = _read_meeting_json(card_path)
        artifacts: dict[str, str] = data.get("artifacts") or {}
        meeting_dir = self._meeting_dir(meeting_id)
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

    def get_artifact_content(self, meeting_id: str, artifact_name: str) -> dict[str, Any] | None:
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
    # Write / ingest
    # ------------------------------------------------------------------

    def find_by_sha256(self, sha256: str) -> str | None:
        """Return meeting_id of first card whose source.media_files contains sha256."""
        if not self.root.exists():
            return None
        for meeting_dir in self.root.iterdir():
            if not meeting_dir.is_dir():
                continue
            card_path = meeting_dir / "meeting.json"
            if not card_path.exists():
                continue
            try:
                data = _read_meeting_json(card_path)
            except MeetingCardError:
                continue
            media_files: list[dict] = (data.get("source") or {}).get("media_files") or []
            for mf in media_files:
                if mf.get("sha256") == sha256:
                    return str(data.get("meeting_id", meeting_dir.name))
        return None

    def unique_meeting_id(self, date_str: str, slug: str) -> str:
        """Return a meeting_id not already used as a directory under root."""
        candidate = f"{date_str}__{slug}"
        if not (self.root / candidate).exists():
            return candidate
        for i in range(2, 1000):
            candidate = f"{date_str}__{slug}-{i}"
            if not (self.root / candidate).exists():
                return candidate
        raise RuntimeError(f"Cannot allocate unique meeting_id for {date_str}__{slug}")

    def create_meeting(
        self,
        *,
        meeting_id: str,
        title: str,
        meeting_date: str,
        source_temp_path: Path,
        original_filename: str,
        sha256: str,
        schema_path: Path | None = None,
    ) -> dict[str, Any]:
        """Create meeting directory, copy media, write validated meeting.json.

        Rolls back (removes meeting_dir) on any error after directory creation.
        """
        if not _safe_meeting_id(meeting_id):
            raise ValueError(f"Invalid meeting_id: {meeting_id!r}")

        meeting_dir = self._meeting_dir(meeting_id)
        # Path traversal guard on the resolved meeting dir
        try:
            meeting_dir.resolve().relative_to(self.root.resolve())
        except ValueError as exc:
            raise ValueError(f"meeting_id escapes meetings root: {meeting_id!r}") from exc

        schema_path = schema_path or _SCHEMA_PATH

        # Defend against path traversal via the client-supplied filename.
        safe_name = Path(original_filename).name
        if not safe_name or safe_name in {".", ".."} or "/" in safe_name or "\\" in safe_name:
            raise ValueError(f"Unsafe original_filename: {original_filename!r}")
        suffix = Path(safe_name).suffix.lower()

        created = False
        try:
            source_dir = meeting_dir / "source"
            source_dir.mkdir(parents=True, exist_ok=False)
            created = True

            dest = source_dir / safe_name
            # Ensure the resolved destination stays inside source_dir.
            try:
                dest.resolve().relative_to(source_dir.resolve())
            except ValueError as exc:
                raise ValueError(f"original_filename escapes source dir: {original_filename!r}") from exc
            shutil.copy2(source_temp_path, dest)

            rel_path = dest.relative_to(meeting_dir).as_posix()
            timestamp = datetime.datetime.now(tz=datetime.timezone.utc).isoformat(timespec="seconds")

            card: dict[str, Any] = {
                "schema_version": 1,
                "meeting_id": meeting_id,
                "title": title,
                "date": meeting_date,
                "source": {
                    "kind": "offline_record",
                    "media_files": [
                        {"path": rel_path, "media_type": _media_type_for(suffix), "sha256": sha256}
                    ],
                    "derived_tracks": ["MIX"],
                },
                "processing_status": "new",
                "participants": [],
                "artifacts": {},
                "classification": {},
                "links": {},
                "retention": {"policy": "default"},
                "rag": {
                    "index_policy": "structured_artifacts_and_final_transcript",
                    "indexed_artifacts": [],
                    "no_index_artifacts": [rel_path],
                },
                "created_at": timestamp,
                "updated_at": timestamp,
            }

            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            jsonschema.Draft202012Validator(schema).validate(card)

            card_path = meeting_dir / "meeting.json"
            tmp = card_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(card, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            tmp.replace(card_path)
            return card

        except Exception:
            if created and meeting_dir.exists():
                shutil.rmtree(meeting_dir, ignore_errors=True)
            raise
