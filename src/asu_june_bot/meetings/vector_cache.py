"""Concurrency-safe JSONL storage for meeting chunk embeddings."""
from __future__ import annotations

import json
import math
import os
import tempfile
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from asu_june_bot.meetings.ingest_lock import IngestLock


EmbedFn = Callable[[str], list[float]]
CacheIdentity = tuple[str, str, str, str]
MAX_ID_CHARS = 512
MAX_MODEL_CHARS = 200


@dataclass(frozen=True)
class CacheEmbeddingRequest:
    meeting_id: str
    chunk_id: str
    text_sha256: str
    text: str

    @property
    def key(self) -> str:
        return f"{self.meeting_id}\x00{self.chunk_id}\x00{self.text_sha256.lower()}"


@dataclass(frozen=True)
class CacheScanReport:
    rows_read: int = 0
    malformed_rows: int = 0
    invalid_rows: int = 0
    duplicate_rows: int = 0

    @property
    def needs_rebuild(self) -> bool:
        return bool(self.malformed_rows or self.invalid_rows or self.duplicate_rows)


@dataclass(frozen=True)
class CacheRebuildReport:
    cache_path: str
    file_existed: bool
    rows_read: int
    rows_written: int
    malformed_rows: int
    invalid_rows: int
    duplicate_rows: int
    rewritten: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _identity(row: dict[str, Any]) -> CacheIdentity | None:
    meeting_id = row.get("meeting_id")
    chunk_id = row.get("chunk_id")
    text_sha = row.get("text_sha256")
    model = row.get("embedding_model")
    if not all(isinstance(value, str) and value for value in (meeting_id, chunk_id, model)):
        return None
    if len(meeting_id) > MAX_ID_CHARS or len(chunk_id) > MAX_ID_CHARS:
        return None
    if len(model) > MAX_MODEL_CHARS:
        return None
    if not isinstance(text_sha, str) or len(text_sha) != 64:
        return None
    try:
        int(text_sha, 16)
    except ValueError:
        return None
    return meeting_id, chunk_id, text_sha.lower(), model


def _embedding(row: dict[str, Any]) -> list[float] | None:
    raw = row.get("embedding")
    if not isinstance(raw, list) or not raw:
        return None
    values: list[float] = []
    for value in raw:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        converted = float(value)
        if not math.isfinite(converted):
            return None
        values.append(converted)
    if math.sqrt(sum(value * value for value in values)) <= 0:
        return None
    return values


def _canonical_row(identity: CacheIdentity, embedding: list[float]) -> dict[str, Any]:
    meeting_id, chunk_id, text_sha, model = identity
    return {
        "meeting_id": meeting_id,
        "chunk_id": chunk_id,
        "text_sha256": text_sha,
        "embedding_model": model,
        "embedding": embedding,
    }


class MeetingEmbeddingCache:
    """Atomic cache shared safely by threads and local API processes."""

    def __init__(self, path: Path | str, *, lock_timeout_seconds: float = 300.0) -> None:
        if lock_timeout_seconds <= 0:
            raise ValueError("lock_timeout_seconds must be positive")
        self.path = Path(path)
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        self.lock_timeout_seconds = lock_timeout_seconds
        self._mutex = threading.RLock()
        self._records: dict[CacheIdentity, dict[str, Any]] | None = None
        self._fingerprint: tuple[int, int, int] | None = None
        self._last_scan = CacheScanReport()

    def _file_fingerprint(self) -> tuple[int, int, int] | None:
        try:
            stat = self.path.stat()
        except FileNotFoundError:
            return None
        return stat.st_mtime_ns, stat.st_size, stat.st_ino

    def _read_unlocked(self) -> tuple[dict[CacheIdentity, dict[str, Any]], CacheScanReport]:
        records: dict[CacheIdentity, dict[str, Any]] = {}
        rows_read = malformed_rows = invalid_rows = duplicate_rows = 0
        if not self.path.exists():
            return records, CacheScanReport()
        with self.path.open("rb") as handle:
            for raw_line in handle:
                if not raw_line.strip():
                    continue
                rows_read += 1
                try:
                    row = json.loads(raw_line.decode("utf-8"))
                except (UnicodeError, json.JSONDecodeError):
                    malformed_rows += 1
                    continue
                if not isinstance(row, dict):
                    invalid_rows += 1
                    continue
                identity = _identity(row)
                embedding = _embedding(row)
                if identity is None or embedding is None:
                    invalid_rows += 1
                    continue
                if identity in records:
                    duplicate_rows += 1
                records[identity] = _canonical_row(identity, embedding)
        return records, CacheScanReport(
            rows_read=rows_read,
            malformed_rows=malformed_rows,
            invalid_rows=invalid_rows,
            duplicate_rows=duplicate_rows,
        )

    def _refresh_unlocked(self, *, force: bool = False) -> CacheScanReport:
        fingerprint = self._file_fingerprint()
        if not force and self._records is not None and fingerprint == self._fingerprint:
            return self._last_scan
        records, report = self._read_unlocked()
        self._records = records
        self._fingerprint = fingerprint
        self._last_scan = report
        return report

    def _write_unlocked(self) -> None:
        records = self._records or {}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, raw_tmp = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            dir=str(self.path.parent),
        )
        tmp = Path(raw_tmp)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                for identity in sorted(records):
                    handle.write(json.dumps(records[identity], ensure_ascii=False) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self.path)
            try:
                self.path.chmod(0o600)
            except OSError:
                pass
            self._fingerprint = self._file_fingerprint()
            self._last_scan = CacheScanReport(rows_read=len(records))
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise

    def ensure_embeddings(
        self,
        embedding_model: str,
        requests: list[CacheEmbeddingRequest],
        embed_fn: EmbedFn,
        *,
        expected_dimensions: int | None = None,
    ) -> dict[str, list[float]]:
        """Return normalized vectors, embedding and committing missing rows once."""
        if not embedding_model or len(embedding_model) > MAX_MODEL_CHARS:
            raise ValueError("embedding_model is invalid")
        if expected_dimensions is not None and expected_dimensions <= 0:
            raise ValueError("expected_dimensions must be positive")
        unique = {request.key: request for request in requests}
        with self._mutex:
            with IngestLock(self.lock_path, timeout_seconds=self.lock_timeout_seconds):
                scan = self._refresh_unlocked()
                records = self._records or {}
                result: dict[str, list[float]] = {}
                pending: dict[CacheIdentity, dict[str, Any]] = {}
                for key, request in unique.items():
                    identity = _identity(
                        {
                            "meeting_id": request.meeting_id,
                            "chunk_id": request.chunk_id,
                            "text_sha256": request.text_sha256,
                            "embedding_model": embedding_model,
                        }
                    )
                    if identity is None:
                        continue
                    row = records.get(identity)
                    raw_embedding = _embedding(row) if row is not None else None
                    if (
                        raw_embedding is not None
                        and expected_dimensions is not None
                        and len(raw_embedding) != expected_dimensions
                    ):
                        raw_embedding = None
                    if raw_embedding is None:
                        raw_embedding = _embedding({"embedding": embed_fn(request.text)})
                        if raw_embedding is None:
                            continue
                        if (
                            expected_dimensions is not None
                            and len(raw_embedding) != expected_dimensions
                        ):
                            continue
                        pending[identity] = _canonical_row(identity, raw_embedding)
                    norm = math.sqrt(sum(value * value for value in raw_embedding))
                    result[key] = [value / norm for value in raw_embedding]
                if pending:
                    records.update(pending)
                if pending or scan.needs_rebuild:
                    self._records = records
                    self._write_unlocked()
                return result

    def rebuild(self, *, dry_run: bool = False) -> CacheRebuildReport:
        """Remove malformed, invalid and duplicate rows through an atomic rewrite."""
        with self._mutex:
            with IngestLock(self.lock_path, timeout_seconds=self.lock_timeout_seconds):
                file_existed = self.path.exists()
                scan = self._refresh_unlocked(force=True)
                records = self._records or {}
                rewritten = not dry_run and (file_existed or bool(records))
                if rewritten:
                    self._write_unlocked()
                return CacheRebuildReport(
                    cache_path=str(self.path),
                    file_existed=file_existed,
                    rows_read=scan.rows_read,
                    rows_written=len(records),
                    malformed_rows=scan.malformed_rows,
                    invalid_rows=scan.invalid_rows,
                    duplicate_rows=scan.duplicate_rows,
                    rewritten=rewritten,
                )


def rebuild_meeting_embedding_cache(
    path: Path | str,
    *,
    dry_run: bool = False,
    lock_timeout_seconds: float = 300.0,
) -> CacheRebuildReport:
    return MeetingEmbeddingCache(
        path,
        lock_timeout_seconds=lock_timeout_seconds,
    ).rebuild(dry_run=dry_run)
