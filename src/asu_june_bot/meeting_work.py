from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from asu_june_bot.meetings.ingest_lock import IngestLock, IngestLockTimeoutError


class _JobStore(Protocol):
    path: Path

    def has_active_for_meeting(self, meeting_id: str) -> bool: ...

    def reserve_job(
        self,
        record: dict[str, Any],
        *,
        pipeline_id: str | None = None,
    ) -> None: ...

    def reserve_pipeline(self, record: dict[str, Any]) -> None: ...


class _LiveStore(Protocol):
    path: Path

    def has_active_for_meeting(self, meeting_id: str) -> bool: ...

    def reserve(self, record: dict[str, Any]) -> None: ...


class MeetingWorkError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.public_message = message


class MeetingWorkConflict(MeetingWorkError):
    pass


class MeetingWorkStateError(MeetingWorkError):
    pass


class MeetingWorkCoordinator:
    """Atomically arbitrate live capture and offline work for one meeting.

    The coordinator owns no durable state. It serializes the check of the
    opposing store and the reservation in the owning store under one
    cross-process lock. Terminal-state cleanup remains the responsibility of
    the existing job and live stores, so a process crash cannot leave a third
    reservation record behind.
    """

    def __init__(
        self,
        lock_path: Path | str,
        *,
        job_store: _JobStore,
        live_store: _LiveStore,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.lock_path = Path(lock_path)
        self.job_store = job_store
        self.live_store = live_store
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.timeout_seconds = timeout_seconds

    def _lock(self) -> IngestLock:
        return IngestLock(self.lock_path, timeout_seconds=self.timeout_seconds)

    @staticmethod
    def _state_error() -> MeetingWorkStateError:
        return MeetingWorkStateError(
            "meeting_work_state_unavailable",
            "Meeting work state is temporarily unavailable",
        )

    def _job_active(self, meeting_id: str) -> bool:
        try:
            return self.job_store.has_active_for_meeting(meeting_id)
        except Exception as exc:
            raise self._state_error() from exc

    def _live_active(self, meeting_id: str) -> bool:
        try:
            return self.live_store.has_active_for_meeting(meeting_id)
        except Exception as exc:
            raise self._state_error() from exc

    def reserve_live(self, record: dict[str, Any]) -> None:
        meeting_id = str(record.get("meeting_id") or "")
        try:
            with self._lock():
                if self._job_active(meeting_id):
                    raise MeetingWorkConflict(
                        "offline_job_active",
                        "Stop offline meeting processing before starting live capture",
                    )
                self.live_store.reserve(record)
        except MeetingWorkConflict:
            raise
        except IngestLockTimeoutError as exc:
            raise self._state_error() from exc

    def reserve_job(
        self,
        record: dict[str, Any],
        *,
        pipeline_id: str | None = None,
    ) -> None:
        meeting_id = str(record.get("meeting_id") or "")
        try:
            with self._lock():
                if self._live_active(meeting_id):
                    raise MeetingWorkConflict(
                        "live_session_active",
                        "Stop live capture before starting offline meeting processing",
                    )
                self.job_store.reserve_job(record, pipeline_id=pipeline_id)
        except MeetingWorkConflict:
            raise
        except IngestLockTimeoutError as exc:
            raise self._state_error() from exc

    def reserve_pipeline(self, record: dict[str, Any]) -> None:
        meeting_id = str(record.get("meeting_id") or "")
        try:
            with self._lock():
                if self._live_active(meeting_id):
                    raise MeetingWorkConflict(
                        "live_session_active",
                        "Stop live capture before starting offline meeting processing",
                    )
                self.job_store.reserve_pipeline(record)
        except MeetingWorkConflict:
            raise
        except IngestLockTimeoutError as exc:
            raise self._state_error() from exc

    def live_active(self, meeting_id: str) -> bool:
        try:
            with self._lock():
                return self._live_active(meeting_id)
        except IngestLockTimeoutError as exc:
            raise self._state_error() from exc

    def offline_active(self, meeting_id: str) -> bool:
        try:
            with self._lock():
                return self._job_active(meeting_id)
        except IngestLockTimeoutError as exc:
            raise self._state_error() from exc
