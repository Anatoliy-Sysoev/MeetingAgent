from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from asu_june_bot.meetings.ingest_lock import IngestLock


class JobStoreError(RuntimeError):
    pass


class JobStoreConflict(JobStoreError):
    pass


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


def _empty_state() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "updated_at": _now_iso(),
        "active_job": None,
        "active_pipeline": None,
        "history": [],
        "pipeline_history": [],
        "events": [],
    }


class JobStore:
    """Atomic durable job state shared by API processes on one host."""

    def __init__(
        self,
        path: Path | str,
        *,
        history_max: int = 20,
        events_max: int = 200,
        max_state_bytes: int = 4 * 1024 * 1024,
    ) -> None:
        self.path = Path(path)
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        self.history_max = history_max
        self.events_max = events_max
        self.max_state_bytes = max_state_bytes
        if history_max <= 0 or events_max <= 0 or max_state_bytes <= 0:
            raise ValueError("JobStore bounds must be positive")

    def _read_unlocked(self) -> dict[str, Any]:
        if not self.path.exists():
            return _empty_state()
        try:
            if self.path.stat().st_size > self.max_state_bytes:
                raise JobStoreError("Job state exceeds the configured size limit")
            raw = self.path.read_bytes()
            if len(raw) > self.max_state_bytes:
                raise JobStoreError("Job state exceeds the configured size limit")
            data = json.loads(raw.decode("utf-8"))
        except JobStoreError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise JobStoreError("Job state is unreadable") from exc
        if not isinstance(data, dict) or data.get("schema_version") != 1:
            raise JobStoreError("Job state has an unsupported schema")
        for key in ("history", "pipeline_history", "events"):
            if not isinstance(data.get(key), list):
                raise JobStoreError("Job state has an invalid collection")
            if any(not isinstance(item, dict) for item in data[key]):
                raise JobStoreError("Job state has an invalid collection record")
        for key in ("active_job", "active_pipeline"):
            if data.get(key) is not None and not isinstance(data.get(key), dict):
                raise JobStoreError("Job state has an invalid active record")
        return data

    def _write_unlocked(self, state: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        state["schema_version"] = 1
        state["updated_at"] = _now_iso()
        state["history"] = list(state.get("history") or [])[-self.history_max :]
        state["pipeline_history"] = list(state.get("pipeline_history") or [])[-self.history_max :]
        state["events"] = list(state.get("events") or [])[-self.events_max :]
        payload = (json.dumps(state, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        if len(payload) > self.max_state_bytes:
            raise JobStoreError("Job state exceeds the configured size limit")
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

    def _mutate(self, callback: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
        with IngestLock(self.lock_path, timeout_seconds=30):
            state = self._read_unlocked()
            callback(state)
            self._write_unlocked(state)
            return deepcopy(state)

    @staticmethod
    def _event(record: dict[str, Any], event_type: str) -> dict[str, Any]:
        return {
            "timestamp": _now_iso(),
            "event": event_type,
            "job_id": str(record.get("job_id") or "")[:80],
            "meeting_id": str(record.get("meeting_id") or "")[:160],
            "kind": str(record.get("kind") or "stage")[:20],
            "stage": str(record.get("stage") or "")[:40] or None,
            "status": str(record.get("status") or "")[:40],
        }

    @staticmethod
    def _upsert(records: list[dict[str, Any]], record: dict[str, Any]) -> None:
        job_id = record.get("job_id")
        records[:] = [item for item in records if item.get("job_id") != job_id]
        records.append(record)

    def load(self) -> dict[str, Any]:
        with IngestLock(self.lock_path, timeout_seconds=30):
            return deepcopy(self._read_unlocked())

    def has_active_for_meeting(self, meeting_id: str) -> bool:
        with IngestLock(self.lock_path, timeout_seconds=30):
            state = self._read_unlocked()
            return any(
                isinstance(record, dict) and record.get("meeting_id") == meeting_id
                for record in (state.get("active_job"), state.get("active_pipeline"))
            )

    def reserve_job(
        self,
        record: dict[str, Any],
        *,
        pipeline_id: str | None = None,
    ) -> None:
        def mutate(state: dict[str, Any]) -> None:
            if state.get("active_job") is not None:
                raise JobStoreConflict("A stage job is already active")
            active_pipeline = state.get("active_pipeline")
            if active_pipeline is not None and active_pipeline.get("job_id") != pipeline_id:
                raise JobStoreConflict("A pipeline job is already active")
            state["active_job"] = record
            state["events"].append(self._event(record, "reserved"))

        self._mutate(mutate)

    def update_job(self, record: dict[str, Any], event_type: str) -> None:
        def mutate(state: dict[str, Any]) -> None:
            active = state.get("active_job")
            if active is not None and active.get("job_id") == record.get("job_id"):
                state["active_job"] = record
            state["events"].append(self._event(record, event_type))

        self._mutate(mutate)

    def release_job(self, record: dict[str, Any], event_type: str) -> None:
        def mutate(state: dict[str, Any]) -> None:
            active = state.get("active_job")
            if active is not None and active.get("job_id") == record.get("job_id"):
                state["active_job"] = None
            state["events"].append(self._event(record, event_type))

        self._mutate(mutate)

    def finish_job(self, record: dict[str, Any], event_type: str) -> None:
        def mutate(state: dict[str, Any]) -> None:
            active = state.get("active_job")
            if active is not None and active.get("job_id") == record.get("job_id"):
                state["active_job"] = None
            self._upsert(state["history"], record)
            state["events"].append(self._event(record, event_type))

        self._mutate(mutate)

    def reserve_pipeline(self, record: dict[str, Any]) -> None:
        def mutate(state: dict[str, Any]) -> None:
            if state.get("active_job") is not None or state.get("active_pipeline") is not None:
                raise JobStoreConflict("A job is already active")
            state["active_pipeline"] = record
            state["events"].append(self._event(record, "reserved"))

        self._mutate(mutate)

    def update_pipeline(self, record: dict[str, Any], event_type: str) -> None:
        def mutate(state: dict[str, Any]) -> None:
            active = state.get("active_pipeline")
            if active is not None and active.get("job_id") == record.get("job_id"):
                state["active_pipeline"] = record
            state["events"].append(self._event(record, event_type))

        self._mutate(mutate)

    def finish_pipeline(self, record: dict[str, Any], event_type: str) -> None:
        def mutate(state: dict[str, Any]) -> None:
            active = state.get("active_pipeline")
            if active is not None and active.get("job_id") == record.get("job_id"):
                state["active_pipeline"] = None
            self._upsert(state["pipeline_history"], record)
            state["events"].append(self._event(record, event_type))

        self._mutate(mutate)

    def replace_recovered(self, state: dict[str, Any], event_records: list[dict[str, Any]]) -> None:
        def mutate(current: dict[str, Any]) -> None:
            current.clear()
            current.update(deepcopy(state))
            current.setdefault("events", [])
            for record in event_records:
                current["events"].append(self._event(record, "recovered"))

        self._mutate(mutate)
