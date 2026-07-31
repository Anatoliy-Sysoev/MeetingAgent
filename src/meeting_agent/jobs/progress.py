from __future__ import annotations

import json
import math
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from meeting_agent.meetings.ingest_lock import IngestLock

_MAX_PROGRESS_BYTES = 32 * 1024
_MAX_PHASE_LENGTH = 80
_MAX_UNIT_LENGTH = 32
_STALE_AFTER_SECONDS = 120.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _bounded_text(value: Any, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text[:limit] if text else None


def resolve_progress_path(meeting_dir: Path, value: str | Path | None) -> Path | None:
    if value is None or not str(value).strip():
        return None
    base = meeting_dir.resolve()
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = base / candidate
    target = candidate.resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise ValueError("progress path must stay inside the meeting directory") from exc
    return target


def normalize_progress_snapshot(
    value: Any,
    *,
    running: bool = False,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    phase = _bounded_text(value.get("phase"), _MAX_PHASE_LENGTH)
    unit = _bounded_text(value.get("unit"), _MAX_UNIT_LENGTH)
    current = _finite_number(value.get("current"))
    total = _finite_number(value.get("total"))
    elapsed = _finite_number(value.get("elapsed_seconds"))
    eta = _finite_number(value.get("eta_seconds"))
    updated_at = _bounded_text(value.get("updated_at"), 40)
    started_at = _bounded_text(value.get("started_at"), 40)
    confidence = value.get("eta_confidence")
    if confidence not in {None, "low", "medium", "high"}:
        confidence = None
    if phase is None or unit is None or current is None:
        return None
    if current < 0 or (total is not None and total <= 0):
        return None
    if total is not None:
        current = min(current, total)
        percent = round(100.0 * current / total, 1)
    else:
        percent = None
    if elapsed is not None:
        elapsed = max(0.0, round(elapsed, 1))
    if eta is not None:
        eta = max(0.0, round(eta, 1))
    stale = False
    if running and updated_at:
        try:
            updated = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            reference = now or datetime.now(timezone.utc)
            stale = (reference - updated.astimezone(timezone.utc)).total_seconds() > _STALE_AFTER_SECONDS
        except ValueError:
            stale = True
    return {
        "phase": phase,
        "current": round(current, 3),
        "total": round(total, 3) if total is not None else None,
        "unit": unit,
        "percent": percent,
        "elapsed_seconds": elapsed,
        "eta_seconds": eta,
        "eta_confidence": confidence,
        "started_at": started_at,
        "updated_at": updated_at,
        "stale": stale,
    }


def read_progress_snapshot(path: Path | None, *, running: bool = False) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    try:
        if path.stat().st_size > _MAX_PROGRESS_BYTES:
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return normalize_progress_snapshot(value, running=running)


class ProgressReporter:
    def __init__(self, path: Path, *, phase: str, unit: str) -> None:
        self.path = path.resolve()
        self.phase = phase
        self.unit = unit
        self._started_monotonic = time.monotonic()
        self._started_at = _now_iso()
        self._last_write_monotonic = 0.0

    def emit(
        self,
        current: float,
        total: float | None,
        *,
        force: bool = False,
        min_interval_seconds: float = 1.0,
    ) -> dict[str, Any]:
        now_monotonic = time.monotonic()
        if not force and now_monotonic - self._last_write_monotonic < min_interval_seconds:
            return {}
        elapsed = max(0.0, now_monotonic - self._started_monotonic)
        eta: float | None = None
        confidence: str | None = None
        if total is not None and total > 0 and current > 0:
            fraction = min(1.0, current / total)
            if elapsed >= 30.0 and fraction >= 0.02 and fraction < 1.0:
                eta = elapsed * (1.0 - fraction) / fraction
                confidence = "medium" if fraction >= 0.15 else "low"
            elif fraction >= 1.0:
                eta = 0.0
                confidence = "high"
        payload = {
            "phase": self.phase,
            "current": current,
            "total": total,
            "unit": self.unit,
            "elapsed_seconds": elapsed,
            "eta_seconds": eta,
            "eta_confidence": confidence,
            "started_at": self._started_at,
            "updated_at": _now_iso(),
        }
        normalized = normalize_progress_snapshot(payload)
        if normalized is None:
            raise ValueError("invalid progress snapshot")
        serialized = json.dumps(normalized, ensure_ascii=False, separators=(",", ":")) + "\n"
        encoded = serialized.encode("utf-8")
        if len(encoded) > _MAX_PROGRESS_BYTES:
            raise ValueError("progress snapshot exceeds size limit")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        tmp_path: Path | None = None
        try:
            with IngestLock(lock_path, timeout_seconds=5.0):
                fd, raw_tmp = tempfile.mkstemp(
                    prefix=f".{self.path.name}.",
                    suffix=".tmp",
                    dir=self.path.parent,
                )
                tmp_path = Path(raw_tmp)
                with os.fdopen(fd, "wb") as handle:
                    handle.write(encoded)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(tmp_path, self.path)
                tmp_path = None
        finally:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)
        self._last_write_monotonic = now_monotonic
        return normalized

    def emit_safely(
        self,
        current: float,
        total: float | None,
        *,
        force: bool = False,
        min_interval_seconds: float = 1.0,
    ) -> dict[str, Any] | None:
        try:
            return self.emit(
                current,
                total,
                force=force,
                min_interval_seconds=min_interval_seconds,
            )
        except (OSError, TimeoutError, ValueError):
            return None
