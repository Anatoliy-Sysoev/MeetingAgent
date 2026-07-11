from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from types import TracebackType


class IngestLockTimeoutError(TimeoutError):
    """Raised when another ingest transaction holds the root lock too long."""


_THREAD_LOCKS_GUARD = threading.Lock()
_THREAD_LOCKS: dict[str, threading.Lock] = {}


def _thread_lock(path: Path) -> threading.Lock:
    key = os.path.normcase(str(path.resolve()))
    with _THREAD_LOCKS_GUARD:
        return _THREAD_LOCKS.setdefault(key, threading.Lock())


def _try_file_lock(handle) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_file(handle) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class IngestLock:
    """Thread- and process-safe advisory lock for one meetings root."""

    def __init__(
        self,
        path: Path,
        *,
        timeout_seconds: float = 300.0,
        poll_seconds: float = 0.05,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.path = path
        self.timeout_seconds = timeout_seconds
        self.poll_seconds = poll_seconds
        self._thread_lock = _thread_lock(path)
        self._handle = None

    def __enter__(self) -> IngestLock:
        deadline = time.monotonic() + self.timeout_seconds
        if not self._thread_lock.acquire(timeout=self.timeout_seconds):
            raise IngestLockTimeoutError("ingest transaction lock timed out")

        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            handle = self.path.open("a+b")
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()

            while True:
                try:
                    _try_file_lock(handle)
                    self._handle = handle
                    return self
                except OSError as exc:
                    if time.monotonic() >= deadline:
                        handle.close()
                        raise IngestLockTimeoutError(
                            "ingest transaction lock timed out"
                        ) from exc
                    time.sleep(self.poll_seconds)
        except BaseException:
            self._thread_lock.release()
            raise

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            if self._handle is not None:
                try:
                    _unlock_file(self._handle)
                finally:
                    self._handle.close()
                    self._handle = None
        finally:
            self._thread_lock.release()
