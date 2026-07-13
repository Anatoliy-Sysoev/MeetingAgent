from __future__ import annotations

import json
import math
import os
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from asu_june_bot.meetings.ingest_lock import IngestLock


ACTIVE_STATUSES = frozenset({"starting", "running", "stopping"})
TERMINAL_STATUSES = frozenset({"completed", "failed", "stale"})
_SOURCES = frozenset({"MIC", "SYS", "MIX"})
_STATUS_EVENT_KEYS = frozenset(
    {"event_id", "type", "timestamp", "status", "reason"}
)
_FINAL_EVENT_KEYS = frozenset(
    {
        "event_id",
        "type",
        "timestamp",
        "source",
        "segment_id",
        "text",
        "start",
        "end",
        "is_final",
        "confidence",
    }
)
_HARD_SESSIONS_MAX = 1_000
_HARD_EVENTS_MAX = 5_000


class LiveSessionStoreError(RuntimeError):
    pass


class LiveSessionStoreConflict(LiveSessionStoreError):
    pass


def now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


def _empty_state() -> dict[str, Any]:
    return {"schema_version": 1, "updated_at": now_iso(), "sessions": []}


def _validate_record(record: object, *, events_max: int) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise LiveSessionStoreError("Live session state contains an invalid record")
    required_strings = (
        "session_id",
        "meeting_id",
        "source",
        "status",
        "created_at",
        "updated_at",
    )
    if any(not isinstance(record.get(key), str) or not record[key] for key in required_strings):
        raise LiveSessionStoreError("Live session state contains an invalid record")
    if record["status"] not in ACTIVE_STATUSES | TERMINAL_STATUSES:
        raise LiveSessionStoreError("Live session state contains an invalid status")
    if record["source"] not in _SOURCES:
        raise LiveSessionStoreError("Live session state contains an invalid source")
    if len(record["session_id"]) > 160 or len(record["meeting_id"]) > 160:
        raise LiveSessionStoreError("Live session state contains an invalid identifier")
    events = record.get("events")
    if not isinstance(events, list) or not events or len(events) > events_max:
        raise LiveSessionStoreError("Live session state contains invalid events")
    last_event_id = record.get("last_event_id")
    if not isinstance(last_event_id, int) or isinstance(last_event_id, bool) or last_event_id < 0:
        raise LiveSessionStoreError("Live session state contains an invalid event cursor")
    previous_id = 0
    for event in events:
        if not isinstance(event, dict):
            raise LiveSessionStoreError("Live session state contains invalid events")
        event_id = event.get("event_id")
        if (
            not isinstance(event_id, int)
            or isinstance(event_id, bool)
            or event_id <= previous_id
            or event_id > last_event_id
        ):
            raise LiveSessionStoreError("Live session state contains invalid events")
        event_type = event.get("type")
        allowed_keys = (
            _STATUS_EVENT_KEYS
            if event_type == "status"
            else _FINAL_EVENT_KEYS if event_type == "final" else None
        )
        if allowed_keys is None or not set(event).issubset(allowed_keys):
            raise LiveSessionStoreError("Live session state contains invalid events")
        if not isinstance(event.get("timestamp"), str) or not event["timestamp"]:
            raise LiveSessionStoreError("Live session state contains invalid events")
        if event_type == "status" and event.get("status") not in (
            ACTIVE_STATUSES | TERMINAL_STATUSES
        ):
            raise LiveSessionStoreError("Live session state contains invalid events")
        if event_type == "status" and "reason" in event:
            reason = event["reason"]
            if not isinstance(reason, str) or not reason or len(reason) > 120:
                raise LiveSessionStoreError("Live session state contains invalid events")
        if event_type == "final":
            if event.get("source") not in _SOURCES or event.get("is_final") is not True:
                raise LiveSessionStoreError("Live session state contains invalid events")
            if not isinstance(event.get("text"), str) or len(event["text"]) > 4_000:
                raise LiveSessionStoreError("Live session state contains invalid events")
            segment_id = event.get("segment_id")
            if not isinstance(segment_id, str) or not segment_id or len(segment_id) > 120:
                raise LiveSessionStoreError("Live session state contains invalid events")
            start = event.get("start")
            end = event.get("end")
            if (
                not isinstance(start, (int, float))
                or isinstance(start, bool)
                or not isinstance(end, (int, float))
                or isinstance(end, bool)
                or not math.isfinite(float(start))
                or not math.isfinite(float(end))
                or float(start) < 0
                or float(end) <= float(start)
            ):
                raise LiveSessionStoreError("Live session state contains invalid events")
            if "confidence" in event:
                confidence = event["confidence"]
                if (
                    not isinstance(confidence, (int, float))
                    or isinstance(confidence, bool)
                    or not math.isfinite(float(confidence))
                    or not 0 <= float(confidence) <= 1
                ):
                    raise LiveSessionStoreError("Live session state contains invalid events")
        previous_id = event_id
    return record


class LiveSessionStore:
    """Atomic bounded state for local live sessions.

    Partials are intentionally not durable. Status and final transcript events
    are stored so restart recovery remains deterministic without turning a
    high-frequency draft stream into continuous whole-file rewrites.
    """

    def __init__(
        self,
        path: Path | str,
        *,
        sessions_max: int = 50,
        active_sessions_max: int = 2,
        events_max: int = 200,
        max_state_bytes: int = 4 * 1024 * 1024,
    ) -> None:
        if not 1 <= sessions_max <= _HARD_SESSIONS_MAX:
            raise ValueError("sessions_max must be in the range 1..1000")
        if not 1 <= active_sessions_max <= sessions_max:
            raise ValueError("active_sessions_max must be in the range 1..sessions_max")
        if not 1 <= events_max <= _HARD_EVENTS_MAX:
            raise ValueError("events_max must be in the range 1..5000")
        if not 64 * 1024 <= max_state_bytes <= 64 * 1024 * 1024:
            raise ValueError("max_state_bytes must be in the range 65536..67108864")
        self.path = Path(path)
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        self.sessions_max = sessions_max
        self.active_sessions_max = active_sessions_max
        self.events_max = events_max
        self.max_state_bytes = max_state_bytes

    def _read_unlocked(self) -> dict[str, Any]:
        if not self.path.exists():
            return _empty_state()
        try:
            if self.path.stat().st_size > self.max_state_bytes:
                raise LiveSessionStoreError("Live session state exceeds its size limit")
            raw = self.path.read_bytes()
            if len(raw) > self.max_state_bytes:
                raise LiveSessionStoreError("Live session state exceeds its size limit")
            state = json.loads(raw.decode("utf-8"))
        except LiveSessionStoreError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise LiveSessionStoreError("Live session state is unreadable") from exc
        if not isinstance(state, dict) or state.get("schema_version") != 1:
            raise LiveSessionStoreError("Live session state has an unsupported schema")
        sessions = state.get("sessions")
        if not isinstance(sessions, list) or len(sessions) > _HARD_SESSIONS_MAX:
            raise LiveSessionStoreError("Live session state has an invalid session list")
        for record in sessions:
            _validate_record(record, events_max=_HARD_EVENTS_MAX)
        return state

    def _write_unlocked(self, state: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        state["schema_version"] = 1
        state["updated_at"] = now_iso()
        sessions = list(state.get("sessions") or [])[-self.sessions_max :]
        for record in sessions:
            record["events"] = list(record.get("events") or [])[-self.events_max :]
        state["sessions"] = sessions
        payload = self._encode(state)
        while len(payload) > self.max_state_bytes:
            candidates = [
                record
                for record in state["sessions"]
                if record.get("status") not in ACTIVE_STATUSES
                and len(record.get("events") or []) > 1
            ]
            if not candidates:
                candidates = [
                    record
                    for record in state["sessions"]
                    if len(record.get("events") or []) > 1
                ]
            if candidates:
                target = max(candidates, key=lambda record: len(record["events"]))
                drop_count = max(1, len(target["events"]) // 4)
                del target["events"][:drop_count]
                payload = self._encode(state)
                continue
            terminal = [
                record
                for record in state["sessions"]
                if record.get("status") not in ACTIVE_STATUSES
            ]
            if terminal:
                oldest_id = terminal[0].get("session_id")
                state["sessions"] = [
                    record
                    for record in state["sessions"]
                    if record.get("session_id") != oldest_id
                ]
                payload = self._encode(state)
                continue
            break
        if len(payload) > self.max_state_bytes:
            raise LiveSessionStoreError("Live session state exceeds its size limit")
        fd, raw_tmp = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            dir=str(self.path.parent),
        )
        tmp = Path(raw_tmp)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self.path)
            try:
                self.path.chmod(0o600)
            except OSError:
                pass
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise

    @staticmethod
    def _encode(state: dict[str, Any]) -> bytes:
        return (json.dumps(state, ensure_ascii=False, indent=2) + "\n").encode("utf-8")

    def _mutate(self, callback: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
        with IngestLock(self.lock_path, timeout_seconds=30):
            state = self._read_unlocked()
            callback(state)
            self._write_unlocked(state)
            return deepcopy(state)

    @staticmethod
    def _upsert(records: list[dict[str, Any]], record: dict[str, Any]) -> None:
        session_id = record.get("session_id")
        records[:] = [item for item in records if item.get("session_id") != session_id]
        records.append(deepcopy(record))

    def load(self) -> dict[str, Any]:
        with IngestLock(self.lock_path, timeout_seconds=30):
            return deepcopy(self._read_unlocked())

    def reserve(self, record: dict[str, Any]) -> None:
        _validate_record(record, events_max=self.events_max)

        def mutate(state: dict[str, Any]) -> None:
            sessions = state["sessions"]
            duplicate = next(
                (
                    item
                    for item in sessions
                    if item.get("meeting_id") == record.get("meeting_id")
                    and item.get("source") == record.get("source")
                    and item.get("status") in ACTIVE_STATUSES
                ),
                None,
            )
            if duplicate is not None:
                raise LiveSessionStoreConflict(
                    "A live session is already active for this meeting and source"
                )
            if sum(
                1 for item in sessions if item.get("status") in ACTIVE_STATUSES
            ) >= self.active_sessions_max:
                raise LiveSessionStoreConflict("Active live session capacity is reached")
            self._upsert(sessions, record)
            if len(sessions) > self.sessions_max:
                active = [item for item in sessions if item.get("status") in ACTIVE_STATUSES]
                terminal = [item for item in sessions if item.get("status") not in ACTIVE_STATUSES]
                available = self.sessions_max - len(active)
                if available < 0:
                    raise LiveSessionStoreConflict("Too many active live sessions")
                state["sessions"] = [*terminal[-available:], *active] if available else active

        self._mutate(mutate)

    def update(self, record: dict[str, Any]) -> None:
        _validate_record(record, events_max=self.events_max)

        def mutate(state: dict[str, Any]) -> None:
            if not any(
                item.get("session_id") == record.get("session_id")
                for item in state["sessions"]
            ):
                raise LiveSessionStoreError("Live session record does not exist")
            self._upsert(state["sessions"], record)

        self._mutate(mutate)

    def recover_active(self) -> list[dict[str, Any]]:
        recovered: list[dict[str, Any]] = []

        def mutate(state: dict[str, Any]) -> None:
            timestamp = now_iso()
            for record in state["sessions"]:
                if record.get("status") not in ACTIVE_STATUSES:
                    continue
                record["status"] = "stale"
                record["updated_at"] = timestamp
                record["finished_at"] = timestamp
                record["error"] = {
                    "code": "api_restart",
                    "message": "Live session stopped after API restart",
                }
                next_id = int(record.get("last_event_id") or 0) + 1
                record["last_event_id"] = next_id
                record["events"].append(
                    {
                        "event_id": next_id,
                        "type": "status",
                        "timestamp": timestamp,
                        "status": "stale",
                        "reason": "api_restart",
                    }
                )
                record["events"] = record["events"][-self.events_max :]
                recovered.append(deepcopy(record))

        self._mutate(mutate)
        return recovered
