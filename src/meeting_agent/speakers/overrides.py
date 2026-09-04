from __future__ import annotations

import datetime
import json
import os
import re
import tempfile
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from meeting_agent.meetings.ingest_lock import IngestLock

MAX_OVERRIDE_BYTES = 2 * 1024 * 1024
MAX_OVERRIDE_EVENTS = 10_000
MAX_SEGMENTS_PER_EVENT = 500

_SEGMENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$")
_SPEAKER_LABEL_RE = re.compile(r"^SPEAKER_(?:UNKNOWN|\d{1,4})$")
_ACTOR_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9@._:-]{0,159}$")


class SpeakerOverrideError(ValueError):
    """Invalid or unavailable speaker override document."""


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _validate_event(event: Any) -> None:
    if not isinstance(event, dict) or set(event) != {
        "event_id", "created_at", "actor_id", "corrections"
    }:
        raise SpeakerOverrideError("speaker override event is invalid")
    if not isinstance(event["event_id"], str) or not re.fullmatch(
        r"evt_[0-9a-f]{32}", event["event_id"]
    ):
        raise SpeakerOverrideError("speaker override event id is invalid")
    if not isinstance(event["created_at"], str) or len(event["created_at"]) > 80:
        raise SpeakerOverrideError("speaker override timestamp is invalid")
    try:
        datetime.datetime.fromisoformat(event["created_at"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise SpeakerOverrideError("speaker override timestamp is invalid") from exc
    if not isinstance(event["actor_id"], str) or not _ACTOR_ID_RE.fullmatch(event["actor_id"]):
        raise SpeakerOverrideError("speaker override actor is invalid")
    corrections = event["corrections"]
    if not isinstance(corrections, list) or not 1 <= len(corrections) <= MAX_SEGMENTS_PER_EVENT:
        raise SpeakerOverrideError("speaker override corrections are invalid")
    seen: set[str] = set()
    for correction in corrections:
        if not isinstance(correction, dict) or set(correction) != {
            "segment_id", "old_speaker_label", "new_speaker_label"
        }:
            raise SpeakerOverrideError("speaker override correction is invalid")
        segment_id = correction["segment_id"]
        if not isinstance(segment_id, str) or not _SEGMENT_ID_RE.fullmatch(segment_id):
            raise SpeakerOverrideError("speaker override segment id is invalid")
        if segment_id in seen:
            raise SpeakerOverrideError("speaker override event contains duplicate segments")
        seen.add(segment_id)
        for key in ("old_speaker_label", "new_speaker_label"):
            value = correction[key]
            if value is not None and (
                not isinstance(value, str) or not _SPEAKER_LABEL_RE.fullmatch(value)
            ):
                raise SpeakerOverrideError("speaker override label is invalid")


def _read_document(path: Path, meeting_id: str) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": 1, "meeting_id": meeting_id, "events": []}
    try:
        if path.stat().st_size > MAX_OVERRIDE_BYTES:
            raise SpeakerOverrideError("speaker override document is too large")
        raw = path.read_bytes()
        if len(raw) > MAX_OVERRIDE_BYTES:
            raise SpeakerOverrideError("speaker override document is too large")
        data = json.loads(raw.decode("utf-8"))
    except SpeakerOverrideError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SpeakerOverrideError("speaker override document is unreadable") from exc
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise SpeakerOverrideError("speaker override document has an invalid schema")
    if data.get("meeting_id") != meeting_id or not isinstance(data.get("events"), list):
        raise SpeakerOverrideError("speaker override document has an invalid meeting identity")
    if len(data["events"]) > MAX_OVERRIDE_EVENTS:
        raise SpeakerOverrideError("speaker override event limit exceeded")
    for event in data["events"]:
        _validate_event(event)
    return data


def _write_document(path: Path, data: Mapping[str, Any]) -> None:
    payload = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if len(payload) > MAX_OVERRIDE_BYTES:
        raise SpeakerOverrideError("speaker override document is too large")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".speaker-overrides.", suffix=".tmp", dir=path.parent)
    temp_path = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


class SpeakerOverrideStore:
    """Audited, atomic corrections layered over immutable diarization output."""

    def __init__(self, path: Path, meeting_id: str) -> None:
        self.path = path
        self.meeting_id = meeting_id
        self.lock_path = path.with_suffix(path.suffix + ".lock")

    def snapshot(self) -> dict[str, Any]:
        document = _read_document(self.path, self.meeting_id)
        current = self._current(document["events"])
        return {
            "meeting_id": self.meeting_id,
            "overrides": list(current.values()),
            "events_count": len(document["events"]),
        }

    def current(self) -> dict[str, dict[str, Any]]:
        return self._current(_read_document(self.path, self.meeting_id)["events"])

    def set(
        self,
        segment_ids: Sequence[str],
        new_speaker_label: str,
        automatic_labels: Mapping[str, str],
        actor_id: str,
    ) -> dict[str, Any]:
        if not isinstance(new_speaker_label, str) or not _SPEAKER_LABEL_RE.fullmatch(new_speaker_label):
            raise SpeakerOverrideError("new speaker label is invalid")
        ids = self._normalize_segment_ids(segment_ids, automatic_labels)
        actor = self._normalize_actor(actor_id)
        with IngestLock(self.lock_path, timeout_seconds=10):
            document = _read_document(self.path, self.meeting_id)
            if len(document["events"]) >= MAX_OVERRIDE_EVENTS:
                raise SpeakerOverrideError("speaker override event limit exceeded")
            current = self._current(document["events"])
            corrections = []
            for segment_id in ids:
                old = current.get(segment_id, {}).get("speaker_label") or automatic_labels[segment_id]
                corrections.append({
                    "segment_id": segment_id,
                    "old_speaker_label": old,
                    "new_speaker_label": new_speaker_label,
                })
            document["events"].append(self._event(actor, corrections))
            _write_document(self.path, document)
        return self.snapshot()

    def reset(
        self,
        segment_ids: Sequence[str],
        automatic_labels: Mapping[str, str],
        actor_id: str,
    ) -> dict[str, Any]:
        ids = self._normalize_segment_ids(segment_ids, automatic_labels)
        actor = self._normalize_actor(actor_id)
        with IngestLock(self.lock_path, timeout_seconds=10):
            document = _read_document(self.path, self.meeting_id)
            current = self._current(document["events"])
            corrections = []
            for segment_id in ids:
                if segment_id in current:
                    corrections.append({
                        "segment_id": segment_id,
                        "old_speaker_label": current[segment_id]["speaker_label"],
                        "new_speaker_label": None,
                    })
            if corrections:
                if len(document["events"]) >= MAX_OVERRIDE_EVENTS:
                    raise SpeakerOverrideError("speaker override event limit exceeded")
                document["events"].append(self._event(actor, corrections))
                _write_document(self.path, document)
        return self.snapshot()

    @staticmethod
    def _current(events: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
        current: dict[str, dict[str, Any]] = {}
        for event in events:
            for correction in event["corrections"]:
                segment_id = correction["segment_id"]
                new_label = correction["new_speaker_label"]
                if new_label is None:
                    current.pop(segment_id, None)
                else:
                    current[segment_id] = {
                        "segment_id": segment_id,
                        "speaker_label": new_label,
                        "actor_id": event["actor_id"],
                        "updated_at": event["created_at"],
                        "event_id": event["event_id"],
                    }
        return current

    @staticmethod
    def _normalize_segment_ids(values: Sequence[str], automatic_labels: Mapping[str, str]) -> list[str]:
        if isinstance(values, (str, bytes)) or not 1 <= len(values) <= MAX_SEGMENTS_PER_EVENT:
            raise SpeakerOverrideError("segment_ids must contain 1 to 500 items")
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            if not isinstance(value, str) or not _SEGMENT_ID_RE.fullmatch(value):
                raise SpeakerOverrideError("segment id is invalid")
            if value not in automatic_labels:
                raise SpeakerOverrideError("segment id does not exist")
            if value not in seen:
                seen.add(value)
                result.append(value)
        return result

    @staticmethod
    def _normalize_actor(actor_id: str) -> str:
        if not isinstance(actor_id, str) or not _ACTOR_ID_RE.fullmatch(actor_id):
            raise SpeakerOverrideError("actor id is invalid")
        return actor_id

    @staticmethod
    def _event(actor_id: str, corrections: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "event_id": f"evt_{uuid.uuid4().hex}",
            "created_at": _now_iso(),
            "actor_id": actor_id,
            "corrections": corrections,
        }
