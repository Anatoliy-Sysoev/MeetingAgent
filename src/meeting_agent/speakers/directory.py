from __future__ import annotations

import datetime as dt
import json
import os
import re
import tempfile
import threading
import unicodedata
import uuid
from pathlib import Path
from typing import Any, Mapping


MAX_DIRECTORY_BYTES = 2 * 1024 * 1024
MAX_PROFILES = 5_000
MAX_FIELD_CHARS = 120
MAX_NOTES_CHARS = 500
_SPEAKER_ID_RE = re.compile(r"^spk_[0-9a-f]{32}$")
_PROFILE_KEYS = {
    "speaker_id", "name", "role", "company", "aliases", "notes", "created_at", "updated_at"
}


class DuplicateSpeakerProfileError(ValueError):
    pass


class SpeakerProfileNotFoundError(LookupError):
    pass


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _text(value: Any, *, field: str, required: bool = False, limit: int = MAX_FIELD_CHARS) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    normalized = " ".join(value.strip().split())
    if required and not normalized:
        raise ValueError(f"{field} is required")
    if len(normalized) > limit:
        raise ValueError(f"{field} exceeds {limit} characters")
    return normalized


def _dedup_key(name: str, company: str) -> str:
    normalized = unicodedata.normalize("NFKC", f"{name}\u0000{company}")
    return " ".join(normalized.casefold().split())


def _normalize_profile_input(data: Mapping[str, Any]) -> dict[str, Any]:
    aliases_raw = data.get("aliases", [])
    if not isinstance(aliases_raw, list) or len(aliases_raw) > 20:
        raise ValueError("aliases must be an array with at most 20 items")
    aliases: list[str] = []
    for value in aliases_raw:
        alias = _text(value, field="alias")
        if alias and alias.casefold() not in {item.casefold() for item in aliases}:
            aliases.append(alias)
    return {
        "name": _text(data.get("name", ""), field="name", required=True),
        "role": _text(data.get("role", ""), field="role"),
        "company": _text(data.get("company", ""), field="company"),
        "aliases": aliases,
        "notes": _text(data.get("notes", ""), field="notes", limit=MAX_NOTES_CHARS),
    }


class SpeakerDirectory:
    """Bounded private speaker profile store with atomic same-directory writes."""

    def __init__(self, path: Path | str, *, max_bytes: int = MAX_DIRECTORY_BYTES) -> None:
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
            raise ValueError("max_bytes must be a positive integer")
        self.path = Path(path)
        self.max_bytes = max_bytes
        self._lock = threading.RLock()

    def _read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        size = self.path.stat().st_size
        if size > self.max_bytes:
            raise ValueError("speaker directory exceeds the configured size limit")
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("speaker directory is invalid or unreadable") from exc
        if not isinstance(document, dict) or document.get("schema_version") != 1:
            raise ValueError("speaker directory schema is invalid")
        raw_profiles = document.get("profiles")
        if not isinstance(raw_profiles, list) or len(raw_profiles) > MAX_PROFILES:
            raise ValueError("speaker directory profiles are invalid")
        profiles: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        seen_keys: set[str] = set()
        for item in raw_profiles:
            if not isinstance(item, dict) or set(item) - _PROFILE_KEYS:
                raise ValueError("speaker directory profile is invalid")
            speaker_id = item.get("speaker_id")
            if not isinstance(speaker_id, str) or not _SPEAKER_ID_RE.fullmatch(speaker_id):
                raise ValueError("speaker directory profile id is invalid")
            normalized = _normalize_profile_input(item)
            created_at = _text(item.get("created_at", ""), field="created_at", required=True, limit=80)
            updated_at = _text(item.get("updated_at", ""), field="updated_at", required=True, limit=80)
            dedup_key = _dedup_key(normalized["name"], normalized["company"])
            if speaker_id in seen_ids or dedup_key in seen_keys:
                raise ValueError("speaker directory contains duplicate profiles")
            seen_ids.add(speaker_id)
            seen_keys.add(dedup_key)
            profiles.append(
                {
                    "speaker_id": speaker_id,
                    **normalized,
                    "created_at": created_at,
                    "updated_at": updated_at,
                }
            )
        return profiles

    def _write(self, profiles: list[dict[str, Any]]) -> None:
        if len(profiles) > MAX_PROFILES:
            raise ValueError("speaker directory profile limit exceeded")
        payload = json.dumps(
            {"schema_version": 1, "profiles": profiles},
            ensure_ascii=False,
            indent=2,
        ) + "\n"
        encoded = payload.encode("utf-8")
        if len(encoded) > self.max_bytes:
            raise ValueError("speaker directory exceeds the configured size limit")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=".speaker-directory.", suffix=".tmp", dir=str(self.path.parent)
        )
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, self.path)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

    @staticmethod
    def _public(profile: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "speaker_id": str(profile.get("speaker_id") or ""),
            "name": str(profile.get("name") or ""),
            "role": str(profile.get("role") or ""),
            "company": str(profile.get("company") or ""),
            "aliases": list(profile.get("aliases") or []),
            "notes": str(profile.get("notes") or ""),
            "created_at": str(profile.get("created_at") or ""),
            "updated_at": str(profile.get("updated_at") or ""),
        }

    def list(self, *, query: str = "") -> list[dict[str, Any]]:
        needle = unicodedata.normalize("NFKC", query).casefold().strip()
        with self._lock:
            profiles = self._read()
        if needle:
            profiles = [
                profile
                for profile in profiles
                if needle
                in unicodedata.normalize(
                    "NFKC",
                    " ".join(
                        [
                            str(profile.get("name") or ""),
                            str(profile.get("role") or ""),
                            str(profile.get("company") or ""),
                            *[str(value) for value in profile.get("aliases") or []],
                        ]
                    ),
                ).casefold()
            ]
        return [self._public(item) for item in sorted(profiles, key=lambda p: str(p.get("name", "")).casefold())]

    def create(self, data: Mapping[str, Any]) -> dict[str, Any]:
        normalized = _normalize_profile_input(data)
        with self._lock:
            profiles = self._read()
            key = _dedup_key(normalized["name"], normalized["company"])
            if any(_dedup_key(str(p.get("name", "")), str(p.get("company", ""))) == key for p in profiles):
                raise DuplicateSpeakerProfileError("speaker profile already exists")
            now = _now_iso()
            profile = {
                "speaker_id": f"spk_{uuid.uuid4().hex}",
                **normalized,
                "created_at": now,
                "updated_at": now,
            }
            profiles.append(profile)
            self._write(profiles)
        return self._public(profile)

    def update(self, speaker_id: str, data: Mapping[str, Any]) -> dict[str, Any]:
        normalized = _normalize_profile_input(data)
        with self._lock:
            profiles = self._read()
            index = next((i for i, item in enumerate(profiles) if item.get("speaker_id") == speaker_id), None)
            if index is None:
                raise SpeakerProfileNotFoundError(speaker_id)
            key = _dedup_key(normalized["name"], normalized["company"])
            if any(
                i != index and _dedup_key(str(p.get("name", "")), str(p.get("company", ""))) == key
                for i, p in enumerate(profiles)
            ):
                raise DuplicateSpeakerProfileError("speaker profile already exists")
            current = profiles[index]
            updated = {
                "speaker_id": speaker_id,
                **normalized,
                "created_at": str(current.get("created_at") or _now_iso()),
                "updated_at": _now_iso(),
            }
            profiles[index] = updated
            self._write(profiles)
        return self._public(updated)

    def delete(self, speaker_id: str) -> None:
        with self._lock:
            profiles = self._read()
            retained = [item for item in profiles if item.get("speaker_id") != speaker_id]
            if len(retained) == len(profiles):
                raise SpeakerProfileNotFoundError(speaker_id)
            self._write(retained)
