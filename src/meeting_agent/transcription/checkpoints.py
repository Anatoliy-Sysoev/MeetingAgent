from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

from meeting_agent.meetings.ingest_lock import IngestLock

VERSION = 1
MAX_BLOCK_BYTES = 8 * 1024 * 1024


class CheckpointError(ValueError):
    """A checkpoint cannot safely be reused."""


def digest(value: Any) -> str:
    return hashlib.sha256(_encode(value)).hexdigest()


def _encode(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                       separators=(",", ":")) + "\n").encode("utf-8")


def file_sha256(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        fd, name = tempfile.mkstemp(prefix=".checkpoint-", suffix=".tmp", dir=path.parent)
        temporary = Path(name)
        with os.fdopen(fd, "wb") as handle:
            handle.write(_encode(value))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _read(path: Path, limit: int) -> dict[str, Any]:
    with path.open("rb") as handle:
        raw = handle.read(limit + 1)
    if len(raw) > limit:
        raise CheckpointError("Checkpoint exceeds size limit")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise CheckpointError("Invalid checkpoint document")
    return value


def _integer(value: Any) -> bool:
    return type(value) is int and value > 0


class CheckpointStore:
    """One active generation; committed blocks are authoritative after a crash."""

    def __init__(self, meeting_dir: Path):
        self.meeting_dir = meeting_dir.resolve()
        self.root = self.path("transcript/_whisper")
        self.current = self.path("transcript/_whisper/manifest.json")

    def path(self, relative: str) -> Path:
        target = (self.meeting_dir / relative).resolve()
        if not target.is_relative_to(self.meeting_dir):
            raise CheckpointError("Checkpoint path must stay inside the meeting")
        return target

    def lock(self) -> IngestLock:
        return IngestLock(self.path("transcript/_whisper/worker.lock"), timeout_seconds=1)

    def header(self) -> dict[str, Any] | None:
        if not self.current.exists():
            return None
        try:
            value = _read(self.current, 64 * 1024)
            generation = value.get("generation")
            if (value.get("version") != VERSION or not isinstance(generation, str)
                    or uuid.UUID(generation).hex != generation
                    or not isinstance(value.get("identity"), dict)
                    or value.get("fingerprint") != digest(value["identity"])
                    or not all(_integer(value.get(k)) for k in
                               ("total_frames", "sample_rate", "block_frames"))
                    or value["total_frames"] > value["block_frames"] * 100_000):
                raise CheckpointError("Invalid checkpoint manifest")
            return value
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise CheckpointError("Checkpoint is unreadable; start a new run explicitly") from exc

    def begin(self, identity: dict[str, Any], *, total_frames: int, sample_rate: int,
              block_frames: int, resume: bool) -> dict[str, Any]:
        if not all(_integer(v) for v in (total_frames, sample_rate, block_frames)):
            raise CheckpointError("Invalid audio frame bounds")
        existing = self.header() if resume else None
        expected = dict(version=VERSION, identity=identity, fingerprint=digest(identity),
                        total_frames=total_frames, sample_rate=sample_rate,
                        block_frames=block_frames)
        if existing is not None:
            if any(existing.get(k) != v for k, v in expected.items()):
                raise CheckpointError("Audio or recognition settings changed; start a new run explicitly")
            return existing
        header = {**expected, "generation": uuid.uuid4().hex}
        atomic_json(self.current, header)
        return header

    def block_path(self, header: dict[str, Any], index: int) -> Path:
        return self.path(f"transcript/_whisper/{header['generation']}/{index:06d}.json")

    @staticmethod
    def bounds(header: dict[str, Any], index: int) -> tuple[int, int]:
        start = index * header["block_frames"]
        return start, min(start + header["block_frames"], header["total_frames"])

    def _valid_rows(self, rows: Any, start: float, end: float) -> bool:
        if not isinstance(rows, list):
            return False
        previous_start = start - 0.002
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("text"), str):
                return False
            a, b = row.get("start"), row.get("end")
            if (type(a) not in (int, float) or type(b) not in (int, float)
                    or not math.isfinite(a) or not math.isfinite(b)
                    or not previous_start <= a < b <= end + 0.002):
                return False
            previous_start = a
        return True

    def commit(self, header: dict[str, Any], index: int, rows: list[dict[str, Any]]) -> None:
        a, b = self.bounds(header, index)
        if (type(index) is not int or index < 0 or a >= b
                or not self._valid_rows(rows, a / header["sample_rate"], b / header["sample_rate"])):
            raise CheckpointError("Invalid checkpoint block")
        payload = dict(fingerprint=header["fingerprint"], index=index,
                       start_frame=a, end_frame=b, segments=rows)
        envelope = {"payload": payload, "sha256": digest(payload)}
        if len(_encode(envelope)) > MAX_BLOCK_BYTES:
            raise CheckpointError("Checkpoint block exceeds size limit")
        atomic_json(self.block_path(header, index), envelope)
        header["saved_blocks"] = index + 1
        atomic_json(self.current, header)

    def prefix(self, header: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
        rows: list[dict[str, Any]] = []
        count = math.ceil(header["total_frames"] / header["block_frames"])
        for index in range(count):
            try:
                envelope = _read(self.block_path(header, index), MAX_BLOCK_BYTES)
                payload = envelope["payload"]
                a, b = self.bounds(header, index)
                if (envelope["sha256"] != digest(payload)
                        or payload["fingerprint"] != header["fingerprint"]
                        or payload["index"] != index
                        or (payload["start_frame"], payload["end_frame"]) != (a, b)
                        or not self._valid_rows(payload["segments"],
                                                a / header["sample_rate"], b / header["sample_rate"])):
                    break
                rows.extend(payload["segments"])
            except (OSError, ValueError, TypeError, KeyError):
                break
        else:
            return rows, count
        return rows, index
