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


class MeetingsService:
    def __init__(self, meetings_root: Path | str = "meetings") -> None:
        self.root = Path(meetings_root)

    def _meeting_dir(self, meeting_id: str) -> Path:
        return self.root / meeting_id

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
