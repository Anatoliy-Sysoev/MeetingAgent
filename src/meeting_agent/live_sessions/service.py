from __future__ import annotations

import json
import math
import os
import re
import tempfile
import threading
import time
import uuid
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from meeting_agent.meetings.ingest_lock import IngestLock, IngestLockTimeoutError
from meeting_agent.meeting_work import (
    MeetingWorkConflict,
    MeetingWorkCoordinator,
    MeetingWorkStateError,
)
from meeting_agent.live_transcription import (
    AudioSourcePreflight,
    LiveMixError,
    LiveSessionReport,
    build_derived_mix_artifacts,
    preflight_audio_source,
    read_derived_mix_timeline,
    write_live_artifacts,
)
from meeting_agent.live_transcription.audio_archive import (
    DEFAULT_ARCHIVE_MAX_BYTES,
    DEFAULT_ARCHIVE_MIN_FREE_BYTES,
)
from meeting_agent.live_transcription.diart_client import (
    DiartSpeakerTurn,
    assign_diart_speakers,
    write_diart_turns_atomic,
)
from meeting_agent.live_transcription.schema import SOURCE_ARTIFACT_KEYS
from meeting_agent.live_transcription.vad import SileroVadConfig
from meeting_agent.live_transcription.vosk_backend import (
    VoskLiveConfig,
    VoskLiveResult,
    transcribe_vosk_live,
)

from .store import (
    ACTIVE_STATUSES,
    LiveSessionStore,
    LiveSessionStoreConflict,
    LiveSessionStoreError,
    now_iso,
)


_MEETING_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,159}$")
_ABSOLUTE_PATH_RE = re.compile(
    r"(?:[A-Za-z]:[\\/]|\\\\[^\\/]+[\\/]|/(?:home|Users|mnt|app|tmp)/)",
    re.IGNORECASE,
)
_PUBLIC_TEXT_MAX = 4_000
_DEVICE_LABEL_MAX = 160
_EVENT_LIMIT_MAX = 200
_ARTIFACT_KEYS = frozenset(
    artifact_key
    for source_keys in SOURCE_ARTIFACT_KEYS.values()
    for artifact_key in source_keys.values()
)
_PREFLIGHT_REASONS = frozenset(
    {
        "unsupported_source",
        "sys_loopback_windows_only",
        "sys_loopback_backend_missing",
        "sys_loopback_discovery_failed",
        "sys_loopback_device_missing",
        "sys_loopback_device_not_found",
        "sys_loopback_default_missing",
        "sounddevice_missing",
        "mic_input_device_missing",
        "mic_input_device_not_found",
        "mic_capture_format_unsupported",
        "mix_loopback_windows_only",
        "mix_source_device_missing",
        "mix_capture_not_implemented",
    }
)


class LiveSessionError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.public_message = message


class LiveSessionConflict(LiveSessionError):
    pass


class LiveSessionNotFound(LiveSessionError):
    pass


class LiveSessionNotRunning(LiveSessionError):
    pass


class LiveSessionPreflightFailed(LiveSessionError):
    pass


@dataclass
class _Worker:
    thread: threading.Thread
    stop_event: threading.Event


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


def _bounded_text(value: Any, *, maximum: int = _PUBLIC_TEXT_MAX) -> str:
    text = " ".join(str(value or "").split())
    return text[:maximum]


def _safe_device_label(value: Any, index: int) -> str:
    label = _bounded_text(value, maximum=_DEVICE_LABEL_MAX)
    if not label or _ABSOLUTE_PATH_RE.search(label):
        return f"Audio device {index}"
    return label


def _safe_number(value: Any, *, default: float = 0.0) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return default
    result = float(value)
    return result if math.isfinite(result) and result >= 0 else default


def _vosk_model_ready(path: Path) -> bool:
    return (
        path.is_dir()
        and (path / "am" / "final.mdl").is_file()
        and (path / "conf" / "model.conf").is_file()
        and any(
            candidate.is_file()
            for candidate in (
                path / "graph" / "HCLG.fst",
                path / "graph" / "Gr.fst",
            )
        )
    )


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    fd, raw_tmp = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    tmp = Path(raw_tmp)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


class LiveSessionService:
    def __init__(
        self,
        *,
        meetings_root: Path | str,
        state_path: Path | str,
        model_path: Path | str,
        vad: str = "silero",
        sample_rate: int = 16_000,
        block_ms: int = 300,
        mic_queue_max_blocks: int = 32,
        partials_max: int = 1_000,
        events_max: int = 500,
        sessions_max: int = 50,
        active_sessions_max: int = 2,
        max_state_bytes: int = 4 * 1024 * 1024,
        stop_timeout_seconds: float = 15.0,
        audio_archive_max_bytes: int = DEFAULT_ARCHIVE_MAX_BYTES,
        audio_archive_min_free_bytes: int = DEFAULT_ARCHIVE_MIN_FREE_BYTES,
        transcriber: Callable[[VoskLiveConfig], VoskLiveResult] = transcribe_vosk_live,
        source_preflight: Callable[..., AudioSourcePreflight] = preflight_audio_source,
        diarizer: Callable[[str, str], list[DiartSpeakerTurn]] | None = None,
        store: LiveSessionStore | None = None,
        coordinator: MeetingWorkCoordinator | None = None,
    ) -> None:
        if vad not in {"none", "silero"}:
            raise ValueError("live.vad must be none or silero")
        if sample_rate != 16_000:
            raise ValueError("live.sample_rate must be 16000")
        if not 50 <= block_ms <= 2_000:
            raise ValueError("live.block_ms must be in the range 50..2000")
        if not 1 <= mic_queue_max_blocks <= 1_024:
            raise ValueError("live.mic_queue_max_blocks must be in the range 1..1024")
        if not 1 <= partials_max <= 10_000:
            raise ValueError("live.partials_max must be in the range 1..10000")
        if not 10 <= events_max <= 5_000:
            raise ValueError("live.events_max must be in the range 10..5000")
        if not 1.0 <= stop_timeout_seconds <= 60.0:
            raise ValueError("live.stop_timeout_seconds must be in the range 1..60")
        if not 1 <= audio_archive_max_bytes <= 4_000_000_000:
            raise ValueError("live.audio_archive_max_bytes must be in the range 1..4000000000")
        if not 0 <= audio_archive_min_free_bytes <= 1_000_000_000_000:
            raise ValueError(
                "live.audio_archive_min_free_bytes must be in the range 0..1000000000000"
            )
        self.meetings_root = Path(meetings_root)
        self.model_path = Path(model_path)
        self.vad = vad
        self.sample_rate = sample_rate
        self.block_ms = block_ms
        self.mic_queue_max_blocks = mic_queue_max_blocks
        self.partials_max = partials_max
        self.events_max = events_max
        self.stop_timeout_seconds = stop_timeout_seconds
        self.audio_archive_max_bytes = audio_archive_max_bytes
        self.audio_archive_min_free_bytes = audio_archive_min_free_bytes
        self.transcriber = transcriber
        self.source_preflight = source_preflight
        self.diarizer = diarizer
        if store is not None and Path(state_path).resolve() != store.path.resolve():
            raise ValueError("state_path does not match the supplied live store")
        self.store = store or LiveSessionStore(
            state_path,
            sessions_max=sessions_max,
            active_sessions_max=active_sessions_max,
            events_max=events_max,
            max_state_bytes=max_state_bytes,
        )
        if (
            coordinator is not None
            and Path(coordinator.live_store.path).resolve() != self.store.path.resolve()
        ):
            raise ValueError("Meeting work coordinator uses a different live store")
        self.coordinator = coordinator
        self._runtime_lock = IngestLock(
            self.store.path.with_suffix(self.store.path.suffix + ".runtime.lock"),
            timeout_seconds=0.25,
            poll_seconds=0.05,
        )
        try:
            self._runtime_lock.__enter__()
        except IngestLockTimeoutError as exc:
            raise LiveSessionStoreError(
                "Another live session API process already owns this state file"
            ) from exc
        self._runtime_lock_held = True
        self._lock = threading.RLock()
        self._workers: dict[str, _Worker] = {}
        self._closing = False
        try:
            recovered = self.store.recover_active()
            state = self.store.load()
            self._records: dict[str, dict[str, Any]] = {
                str(record["session_id"]): record for record in state["sessions"]
            }
            for record in recovered:
                self._mark_meeting_stale(record)
        except BaseException:
            self._release_runtime_lock()
            raise

    def preflight(
        self,
        source: str,
        *,
        audio_device_index: int | None = None,
    ) -> dict[str, Any]:
        normalized = str(source or "").upper()
        try:
            result = self.source_preflight(
                normalized,
                audio_device_index=audio_device_index,
            )
        except Exception:  # noqa: BLE001 - hardware details stay private
            return {
                "source": normalized,
                "available": False,
                "reason": "source_preflight_failed",
                "model_ready": _vosk_model_ready(self.model_path),
                "devices": [],
                "devices_truncated": False,
            }
        devices = [
            {
                "device_index": device.index,
                "label": _safe_device_label(device.name, device.index),
            }
            for device in result.devices[:64]
        ]
        model_ready = _vosk_model_ready(self.model_path)
        reason = result.reason if result.reason in _PREFLIGHT_REASONS else None
        if result.available and not model_ready:
            reason = "model_missing"
        elif not result.available and reason is None:
            reason = "source_preflight_failed"
        return {
            "source": normalized,
            "available": bool(result.available and model_ready),
            "reason": reason,
            "model_ready": model_ready,
            "devices": devices,
            "devices_truncated": len(result.devices) > len(devices),
        }

    def ensure_meeting(self, meeting_id: str) -> None:
        self._meeting_dir(meeting_id)

    def timeline(
        self,
        meeting_id: str,
        *,
        after: int = 0,
        limit: int = 200,
    ) -> dict[str, Any]:
        meeting_dir = self._meeting_dir(meeting_id)
        try:
            return read_derived_mix_timeline(
                meeting_dir / "transcript" / "live",
                after=after,
                limit=limit,
            )
        except (LiveMixError, OSError, UnicodeError, ValueError) as exc:
            raise LiveSessionError(
                "live_timeline_unavailable",
                "Live conversation timeline is unavailable",
            ) from exc

    def start(
        self,
        meeting_id: str,
        *,
        source: str,
        audio_device_index: int | None = None,
        duration_sec: float | None = None,
        vad: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        if self._closing:
            raise LiveSessionConflict("service_stopping", "Live session service is stopping")
        normalized = str(source or "").upper()
        if normalized not in SOURCE_ARTIFACT_KEYS:
            raise LiveSessionPreflightFailed("unsupported_source", "Unsupported live source")
        selected_vad = self.vad if vad is None else vad
        if selected_vad not in {"none", "silero"}:
            raise LiveSessionPreflightFailed("invalid_vad", "Unsupported live VAD mode")
        if audio_device_index is not None and not 0 <= audio_device_index <= 65_535:
            raise LiveSessionPreflightFailed("invalid_device", "Invalid audio device")
        if duration_sec is not None and not 1.0 <= duration_sec <= 43_200.0:
            raise LiveSessionPreflightFailed(
                "invalid_duration", "Live duration must be between 1 and 43200 seconds"
            )
        if (
            duration_sec is not None
            and int(duration_sec * self.sample_rate * 2)
            > self.audio_archive_max_bytes
        ):
            raise LiveSessionPreflightFailed(
                "audio_archive_limit",
                "Live duration exceeds the recording size limit",
            )
        meeting_dir = self._meeting_dir(meeting_id)
        self._read_card(meeting_dir)
        preflight = self.preflight(
            normalized,
            audio_device_index=audio_device_index,
        )
        if not preflight["available"]:
            raise LiveSessionPreflightFailed(
                str(preflight.get("reason") or "source_unavailable"),
                "Live audio source is not ready",
            )
        output = (
            meeting_dir
            / "transcript"
            / "live"
            / f"live_segments.{normalized}.jsonl"
        )
        audio_output = meeting_dir / "source" / f"live_audio.{normalized}.wav"
        if (output.exists() or audio_output.exists()) and not force:
            raise LiveSessionConflict(
                "live_artifact_exists",
                "A finalized live recording already exists for this source",
            )

        timestamp = now_iso()
        session_id = str(uuid.uuid4())
        record: dict[str, Any] = {
            "session_id": session_id,
            "meeting_id": meeting_id,
            "source": normalized,
            "status": "starting",
            "engine": "vosk",
            "model": self.model_path.name,
            "vad": selected_vad,
            "created_at": timestamp,
            "started_at": timestamp,
            "updated_at": timestamp,
            "finished_at": None,
            "last_event_id": 1,
            "events": [
                {
                    "event_id": 1,
                    "type": "status",
                    "timestamp": timestamp,
                    "status": "starting",
                }
            ],
            "warnings": [],
            "error": None,
            "artifact_keys": [],
        }
        try:
            if self.coordinator is not None:
                self.coordinator.reserve_live(record)
            else:
                self.store.reserve(record)
        except MeetingWorkConflict as exc:
            raise LiveSessionConflict(exc.code, exc.public_message) from exc
        except MeetingWorkStateError as exc:
            raise LiveSessionError(exc.code, exc.public_message) from exc
        except LiveSessionStoreConflict as exc:
            if "capacity" in str(exc).lower():
                raise LiveSessionConflict(
                    "live_session_capacity",
                    "Live session capacity is reached",
                ) from exc
            raise LiveSessionConflict(
                "live_session_active",
                "A live session is already active for this meeting and source",
            ) from exc
        with self._lock:
            self._records[session_id] = record
        try:
            self._mark_meeting_started(meeting_dir, source=normalized)
        except Exception as exc:  # noqa: BLE001 - never expose card path/raw error
            self._fail_session(
                session_id,
                code="meeting_card_unwritable",
                message="Meeting card could not be updated",
            )
            raise LiveSessionError(
                "meeting_card_unwritable", "Meeting card could not be updated"
            ) from exc

        stop_event = threading.Event()
        config = VoskLiveConfig(
            model_path=self.model_path,
            source=normalized,
            sample_rate=self.sample_rate,
            block_ms=self.block_ms,
            duration_sec=duration_sec,
            audio_device_index=audio_device_index,
            mic_queue_max_blocks=self.mic_queue_max_blocks,
            partials_max=self.partials_max,
            save_partials=True,
            vad=selected_vad,
            silero_vad=SileroVadConfig(),
            stop_event=stop_event,
            event_callback=lambda event_type, payload: self._backend_event(
                session_id, event_type, payload
            ),
            audio_archive_path=audio_output,
            audio_archive_max_bytes=self.audio_archive_max_bytes,
            audio_archive_min_free_bytes=self.audio_archive_min_free_bytes,
        )
        thread = threading.Thread(
            target=self._run_worker,
            args=(session_id, meeting_dir, config),
            name=f"meetingagent-live-{session_id[:8]}",
            daemon=True,
        )
        with self._lock:
            self._workers[session_id] = _Worker(thread=thread, stop_event=stop_event)
        try:
            thread.start()
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self._workers.pop(session_id, None)
            self._fail_session(
                session_id,
                code="worker_start_failed",
                message="Live session worker could not start",
            )
            self._mark_meeting_failed(
                meeting_dir,
                session_id=session_id,
                code="worker_start_failed",
            )
            raise LiveSessionError(
                "worker_start_failed", "Live session worker could not start"
            ) from exc
        return self.get(meeting_id, session_id)

    def get(self, meeting_id: str, session_id: str) -> dict[str, Any]:
        record = self._record_for(meeting_id, session_id)
        return self._public_record(record)

    def active(self, meeting_id: str, *, source: str | None = None) -> dict[str, Any] | None:
        normalized = str(source).upper() if source is not None else None
        with self._lock:
            candidates = [
                record
                for record in self._records.values()
                if record.get("meeting_id") == meeting_id
                and record.get("status") in ACTIVE_STATUSES
                and (normalized is None or record.get("source") == normalized)
            ]
            if not candidates:
                return None
            return self._public_record(candidates[-1])

    def offline_work_active(self, meeting_id: str) -> bool:
        if self.coordinator is None:
            return False
        try:
            return self.coordinator.offline_active(meeting_id)
        except MeetingWorkStateError as exc:
            raise LiveSessionError(exc.code, exc.public_message) from exc

    def events(
        self,
        meeting_id: str,
        session_id: str,
        *,
        after: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        if after < 0 or not 1 <= limit <= _EVENT_LIMIT_MAX:
            raise LiveSessionError("invalid_event_cursor", "Invalid live event cursor")
        record = self._record_for(meeting_id, session_id)
        available = list(record.get("events") or [])
        oldest = int(available[0]["event_id"]) if available else int(record["last_event_id"])
        newest = int(record["last_event_id"])
        selected = [event for event in available if int(event["event_id"]) > after][:limit]
        return {
            "session_id": session_id,
            "meeting_id": meeting_id,
            "source": record["source"],
            "status": record["status"],
            "events": deepcopy(selected),
            "oldest_event_id": oldest,
            "newest_event_id": newest,
            "next_after": int(selected[-1]["event_id"]) if selected else after,
            "truncated": bool(available and after < oldest - 1),
            "partial_events_durable": False,
        }

    def stop(self, meeting_id: str, session_id: str) -> dict[str, Any]:
        record = self._record_for(meeting_id, session_id)
        if record["status"] not in ACTIVE_STATUSES:
            return self._public_record(record)
        with self._lock:
            worker = self._workers.get(session_id)
        if worker is None:
            latest = self.get(meeting_id, session_id)
            if not latest["is_active"]:
                return latest
            raise LiveSessionNotRunning(
                "live_session_not_running", "Live session worker is not running"
            )
        self._set_status(
            session_id,
            "stopping",
            expected=frozenset({"starting", "running"}),
        )
        worker.stop_event.set()
        worker.thread.join(timeout=self.stop_timeout_seconds)
        return self.get(meeting_id, session_id)

    def shutdown(self) -> None:
        with self._lock:
            if self._closing and not self._runtime_lock_held:
                return
            self._closing = True
        with self._lock:
            workers = list(self._workers.items())
        for session_id, worker in workers:
            try:
                self._set_status(
                    session_id,
                    "stopping",
                    expected=frozenset({"starting", "running"}),
                )
            except LiveSessionError:
                pass
            worker.stop_event.set()
        deadline = time.monotonic() + self.stop_timeout_seconds
        for _session_id, worker in workers:
            remaining = max(0.0, deadline - time.monotonic())
            worker.thread.join(timeout=remaining)
        self._release_runtime_lock_if_idle()

    def _release_runtime_lock_if_idle(self) -> None:
        with self._lock:
            if self._workers or not self._closing:
                return
            self._release_runtime_lock()

    def _release_runtime_lock(self) -> None:
        if not getattr(self, "_runtime_lock_held", False):
            return
        self._runtime_lock.__exit__(None, None, None)
        self._runtime_lock_held = False

    def _meeting_dir(self, meeting_id: str) -> Path:
        if not _MEETING_ID_RE.fullmatch(str(meeting_id or "")):
            raise LiveSessionNotFound("meeting_not_found", "Meeting not found")
        root = self.meetings_root.resolve()
        meeting_dir = (root / meeting_id).resolve()
        if root not in meeting_dir.parents or not (meeting_dir / "meeting.json").is_file():
            raise LiveSessionNotFound("meeting_not_found", "Meeting not found")
        return meeting_dir

    @staticmethod
    def _read_card(meeting_dir: Path) -> dict[str, Any]:
        try:
            card = json.loads((meeting_dir / "meeting.json").read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise LiveSessionError("meeting_card_invalid", "Meeting card is invalid") from exc
        if not isinstance(card, dict):
            raise LiveSessionError("meeting_card_invalid", "Meeting card is invalid")
        if card.get("meeting_id") != meeting_dir.name:
            raise LiveSessionError("meeting_card_invalid", "Meeting card is invalid")
        return card

    def _record_for(self, meeting_id: str, session_id: str) -> dict[str, Any]:
        with self._lock:
            record = self._records.get(session_id)
            if record is None or record.get("meeting_id") != meeting_id:
                raise LiveSessionNotFound("live_session_not_found", "Live session not found")
            return deepcopy(record)

    def _persist(self, record: dict[str, Any]) -> None:
        durable = deepcopy(record)
        durable["events"] = [
            event for event in durable.get("events") or [] if event.get("type") != "partial"
        ][-self.events_max :]
        self.store.update(durable)

    def _append_event(
        self,
        session_id: str,
        event_type: str,
        payload: dict[str, Any],
        *,
        persist: bool,
    ) -> dict[str, Any]:
        with self._lock:
            record = self._records.get(session_id)
            if record is None:
                raise LiveSessionNotFound("live_session_not_found", "Live session not found")
            event_id = int(record.get("last_event_id") or 0) + 1
            event: dict[str, Any] = {
                "event_id": event_id,
                "type": event_type,
                "timestamp": _utc_now(),
            }
            event.update(payload)
            record["last_event_id"] = event_id
            record["updated_at"] = event["timestamp"]
            record.setdefault("events", []).append(event)
            record["events"] = record["events"][-self.events_max :]
            snapshot = deepcopy(record)
            if persist:
                self._persist(snapshot)
            return event

    def _backend_event(
        self,
        session_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        with self._lock:
            record = self._records.get(session_id)
            if record is None:
                raise LiveSessionNotFound("live_session_not_found", "Live session not found")
            source = str(record["source"])
        if event_type == "partial":
            safe = {
                "source": source,
                "text": _bounded_text(payload.get("text")),
                "start": round(_safe_number(payload.get("start")), 3),
                "end": round(_safe_number(payload.get("end")), 3),
                "is_final": False,
            }
            if safe["text"]:
                self._append_event(session_id, "partial", safe, persist=False)
            return
        if event_type == "final":
            start = _safe_number(payload.get("start"))
            end = max(_safe_number(payload.get("end")), start + 0.01)
            safe = {
                "source": source,
                "segment_id": _bounded_text(payload.get("segment_id"), maximum=120),
                "text": _bounded_text(payload.get("text")),
                "start": round(start, 3),
                "end": round(end, 3),
                "is_final": True,
            }
            confidence = payload.get("confidence")
            if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
                numeric_confidence = float(confidence)
                if math.isfinite(numeric_confidence):
                    safe["confidence"] = round(
                        max(0.0, min(numeric_confidence, 1.0)),
                        4,
                    )
            if safe["text"]:
                self._append_event(session_id, "final", safe, persist=True)

    def _set_status(
        self,
        session_id: str,
        status: str,
        *,
        reason: str | None = None,
        expected: frozenset[str] | None = None,
    ) -> bool:
        with self._lock:
            record = self._records.get(session_id)
            if record is None:
                raise LiveSessionNotFound("live_session_not_found", "Live session not found")
            if expected is not None and record.get("status") not in expected:
                return False
            record["status"] = status
            timestamp = now_iso()
            record["updated_at"] = timestamp
            if status in {"completed", "failed", "stale"}:
                record["finished_at"] = timestamp
            payload: dict[str, Any] = {"status": status}
            if reason:
                payload["reason"] = reason
            self._append_event(session_id, "status", payload, persist=True)
        return True

    def _fail_session(self, session_id: str, *, code: str, message: str) -> None:
        try:
            with self._lock:
                record = self._records.get(session_id)
                if record is None:
                    return
                record["error"] = {"code": code, "message": message}
            self._set_status(session_id, "failed", reason=code)
        except (LiveSessionError, LiveSessionStoreError):
            return

    def _run_worker(
        self,
        session_id: str,
        meeting_dir: Path,
        config: VoskLiveConfig,
    ) -> None:
        try:
            self._set_status(
                session_id,
                "running",
                expected=frozenset({"starting"}),
            )
            result = self.transcriber(config)
            expected_audio = config.audio_archive_path
            audio_archive = result.audio_archive_path
            if (
                expected_audio is None
                or audio_archive is None
                or audio_archive.resolve() != expected_audio.resolve()
                or not audio_archive.is_file()
            ):
                raise LiveSessionError(
                    "live_audio_missing",
                    "Live audio archive was not finalized",
                )
            warnings = self._result_warnings(result)
            diart_path: Path | None = None
            if config.source == "SYS" and self.diarizer is not None:
                try:
                    turns = self.diarizer(meeting_dir.name, config.source)
                    result = replace(
                        result,
                        segments=assign_diart_speakers(result.segments, turns),
                    )
                    diart_path = (
                        meeting_dir
                        / "transcript"
                        / "live"
                        / "live_diarization.SYS.json"
                    )
                    write_diart_turns_atomic(
                        diart_path,
                        meeting_id=meeting_dir.name,
                        source=config.source,
                        turns=turns,
                    )
                    if not turns:
                        warnings.append("live_diarization_no_turns")
                except Exception:  # noqa: BLE001 - optional sidecar must not fail capture
                    warnings.append("live_diarization_unavailable")
            with self._lock:
                record = self._records[session_id]
                started_at = str(record["started_at"])
            report = LiveSessionReport(
                engine="vosk",
                model=self.model_path.name,
                source=config.source,
                sample_rate=config.sample_rate,
                block_ms=config.block_ms,
                duration_seconds=float(result.metrics.get("duration") or 0.0),
                segments_count=len(result.segments),
                partials_count=len(result.partials),
                chars_count=sum(len(segment.text) for segment in result.segments),
                started_at=started_at,
                finished_at=now_iso(),
                elapsed_seconds=float(result.metrics.get("elapsed_seconds") or 0.0),
                warnings=warnings,
                backend_metrics=result.metrics,
            )
            written = write_live_artifacts(
                meeting_dir / "transcript" / "live",
                result.segments,
                result.partials,
                report,
                source=config.source,
            )
            written["live_audio"] = audio_archive
            if diart_path is not None:
                written["live_diarization"] = diart_path
            with self._lock:
                record = self._records[session_id]
                record["warnings"] = warnings[:50]
                record["artifact_keys"] = sorted(
                    SOURCE_ARTIFACT_KEYS[config.source][key]
                    for key in written
                    if key in SOURCE_ARTIFACT_KEYS[config.source]
                )
            self._mark_meeting_completed(
                meeting_dir,
                source=config.source,
                written=written,
                session_id=session_id,
                duration_seconds=report.duration_seconds,
            )
            mix_warning, mix_artifact_keys = self._refresh_derived_mix(meeting_dir)
            if mix_warning and mix_warning not in warnings:
                warnings.append(mix_warning)
            with self._lock:
                record = self._records[session_id]
                record["warnings"] = warnings[:50]
                record["artifact_keys"] = sorted(
                    set(record.get("artifact_keys") or []) | set(mix_artifact_keys)
                )
            self._set_status(
                session_id,
                "completed",
                expected=ACTIVE_STATUSES,
            )
        except Exception:  # noqa: BLE001 - public session state stays path-free
            self._mark_meeting_failed(
                meeting_dir,
                session_id=session_id,
                code="live_session_failed",
            )
            self._fail_session(
                session_id,
                code="live_session_failed",
                message="Live transcription failed",
            )
        finally:
            with self._lock:
                self._workers.pop(session_id, None)
            self._release_runtime_lock_if_idle()

    @staticmethod
    def _result_warnings(result: VoskLiveResult) -> list[str]:
        warnings: list[str] = [] if result.segments else ["no_final_segments"]
        for warning in result.metrics.get("vad_warnings") or []:
            if isinstance(warning, str) and warning and warning not in warnings:
                warnings.append(_bounded_text(warning, maximum=80))
        warning_metrics = {
            "mic_audio_dropped": "mic_queue_dropped_frames",
            "mic_input_status_events": "input_status_events",
            "live_partials_dropped": "partials_dropped",
        }
        for warning, metric in warning_metrics.items():
            if int(result.metrics.get(metric) or 0) > 0 and warning not in warnings:
                warnings.append(warning)
        return warnings[:50]

    def _has_other_active(self, meeting_id: str, session_id: str) -> bool:
        with self._lock:
            return any(
                record.get("meeting_id") == meeting_id
                and record.get("session_id") != session_id
                and record.get("status") in ACTIVE_STATUSES
                for record in self._records.values()
            )

    def _can_clear_live_error(self, card: dict[str, Any], *, source: str) -> bool:
        last_error = card.get("last_error")
        if not isinstance(last_error, dict):
            return True
        if last_error.get("stage") != "live_transcription":
            return False
        failed_session_id = last_error.get("job_id")
        if not isinstance(failed_session_id, str) or not failed_session_id:
            return True
        with self._lock:
            failed_record = self._records.get(failed_session_id)
            if failed_record is None:
                return True
            return failed_record.get("source") == source

    def _mark_meeting_started(self, meeting_dir: Path, *, source: str) -> None:
        with IngestLock(meeting_dir / ".live_session.lock", timeout_seconds=30):
            current = self._read_card(meeting_dir)
            current["processing_status"] = "transcribing"
            current["updated_at"] = now_iso()
            if self._can_clear_live_error(current, source=source):
                current.pop("last_error", None)
            _write_json_atomic(meeting_dir / "meeting.json", current)

    def _mark_meeting_completed(
        self,
        meeting_dir: Path,
        *,
        source: str,
        written: dict[str, Path],
        session_id: str,
        duration_seconds: float,
    ) -> None:
        with IngestLock(meeting_dir / ".live_session.lock", timeout_seconds=30):
            card = self._read_card(meeting_dir)
            artifacts = card.get("artifacts")
            if not isinstance(artifacts, dict):
                artifacts = {}
            source_keys = SOURCE_ARTIFACT_KEYS[source]
            for key, path in written.items():
                artifact_key = source_keys.get(key)
                if artifact_key:
                    artifacts[artifact_key] = path.resolve().relative_to(
                        meeting_dir.resolve()
                    ).as_posix()
            refinement_rel = None
            if source in {"MIC", "SYS"}:
                artifacts.pop(f"live_refinement_{source.lower()}", None)
                refinement_rel = f"transcript/live/refinement.{source}.json"
            card["artifacts"] = artifacts
            refinements = card.get("live_refinements")
            if source in {"MIC", "SYS"} and isinstance(refinements, dict):
                refinements = dict(refinements)
                refinements.pop(source, None)
                if refinements:
                    card["live_refinements"] = refinements
                else:
                    card.pop("live_refinements", None)
            source_data = card.get("source")
            if not isinstance(source_data, dict):
                source_data = {"kind": "live_session"}
            track_key = "derived_tracks" if source == "MIX" else "audio_tracks"
            tracks = source_data.get(track_key)
            tracks = list(tracks) if isinstance(tracks, list) else []
            if source not in tracks:
                tracks.append(source)
            source_data[track_key] = tracks
            audio_path = written.get("live_audio")
            if audio_path is not None:
                audio_rel = audio_path.resolve().relative_to(
                    meeting_dir.resolve()
                ).as_posix()
                raw_media = source_data.get("media_files")
                media_files = [
                    dict(item)
                    for item in raw_media
                    if isinstance(item, dict)
                ] if isinstance(raw_media, list) else []
                media_entry = {
                    "path": audio_rel,
                    "media_type": "audio",
                    "duration_seconds": round(max(0.0, duration_seconds), 3),
                }
                replaced = False
                for index, item in enumerate(media_files):
                    if item.get("path") == audio_rel:
                        media_files[index] = media_entry
                        replaced = True
                        break
                if not replaced:
                    media_files.append(media_entry)
                source_data["media_files"] = media_files
            card["source"] = source_data
            rag = card.get("rag")
            if not isinstance(rag, dict):
                rag = {"index_policy": "structured_artifacts_and_final_transcript"}
            no_index = rag.get("no_index_artifacts")
            no_index = list(no_index) if isinstance(no_index, list) else []
            if refinement_rel is not None:
                no_index = [value for value in no_index if value != refinement_rel]
            for key in written:
                artifact_key = source_keys.get(key)
                if artifact_key is None:
                    continue
                value = artifacts.get(artifact_key)
                if isinstance(value, str) and value not in no_index:
                    no_index.append(value)
            rag["no_index_artifacts"] = no_index
            card["rag"] = rag
            has_other_active = self._has_other_active(
                str(card.get("meeting_id") or ""),
                session_id,
            )
            clear_error = self._can_clear_live_error(card, source=source)
            card["processing_status"] = (
                "transcribing"
                if has_other_active
                else "processing" if clear_error else "failed"
            )
            card["updated_at"] = now_iso()
            if clear_error:
                card.pop("last_error", None)
            if refinement_rel is not None:
                (meeting_dir / refinement_rel).unlink(missing_ok=True)
            _write_json_atomic(meeting_dir / "meeting.json", card)

    def _refresh_derived_mix(
        self,
        meeting_dir: Path,
    ) -> tuple[str | None, list[str]]:
        try:
            with IngestLock(meeting_dir / ".live_session.lock", timeout_seconds=30):
                result = build_derived_mix_artifacts(
                    meeting_dir / "transcript" / "live",
                    generated_at=now_iso(),
                )
                if result is None:
                    return None, []

                card = self._read_card(meeting_dir)
                artifacts = card.get("artifacts")
                if not isinstance(artifacts, dict):
                    artifacts = {}
                source_keys = SOURCE_ARTIFACT_KEYS["MIX"]
                artifact_keys: list[str] = []
                for key, path in result.written.items():
                    artifact_key = source_keys.get(key)
                    if artifact_key is None:
                        continue
                    artifacts[artifact_key] = path.resolve().relative_to(
                        meeting_dir.resolve()
                    ).as_posix()
                    artifact_keys.append(artifact_key)
                card["artifacts"] = artifacts

                source_data = card.get("source")
                if not isinstance(source_data, dict):
                    source_data = {"kind": "live_session"}
                derived_tracks = source_data.get("derived_tracks")
                derived_tracks = (
                    list(derived_tracks) if isinstance(derived_tracks, list) else []
                )
                if "MIX" not in derived_tracks:
                    derived_tracks.append("MIX")
                source_data["derived_tracks"] = derived_tracks
                card["source"] = source_data

                rag = card.get("rag")
                if not isinstance(rag, dict):
                    rag = {
                        "index_policy": "structured_artifacts_and_final_transcript"
                    }
                no_index = rag.get("no_index_artifacts")
                no_index = list(no_index) if isinstance(no_index, list) else []
                for artifact_key in artifact_keys:
                    value = artifacts.get(artifact_key)
                    if isinstance(value, str) and value not in no_index:
                        no_index.append(value)
                rag["no_index_artifacts"] = no_index
                card["rag"] = rag
                card["updated_at"] = now_iso()
                _write_json_atomic(meeting_dir / "meeting.json", card)
                return None, sorted(artifact_keys)
        except (
            IngestLockTimeoutError,
            LiveMixError,
            LiveSessionError,
            OSError,
            UnicodeError,
            ValueError,
        ):
            return "live_mix_derivation_failed", []

    def _mark_meeting_failed(
        self,
        meeting_dir: Path,
        *,
        session_id: str,
        code: str,
    ) -> None:
        try:
            with IngestLock(meeting_dir / ".live_session.lock", timeout_seconds=30):
                card = self._read_card(meeting_dir)
                meeting_id = str(card.get("meeting_id") or "")
                card["processing_status"] = (
                    "transcribing"
                    if self._has_other_active(meeting_id, session_id)
                    else "failed"
                )
                card["updated_at"] = now_iso()
                card["last_error"] = {
                    "stage": "live_transcription",
                    "code": code,
                    "message": "Live transcription failed",
                    "timestamp": now_iso(),
                    "job_id": session_id,
                }
                _write_json_atomic(meeting_dir / "meeting.json", card)
        except Exception:  # noqa: BLE001
            return

    def _mark_meeting_stale(self, record: dict[str, Any]) -> None:
        try:
            meeting_dir = self._meeting_dir(str(record.get("meeting_id") or ""))
            with IngestLock(meeting_dir / ".live_session.lock", timeout_seconds=30):
                card = self._read_card(meeting_dir)
                card["processing_status"] = "processing"
                card["updated_at"] = now_iso()
                card["last_error"] = {
                    "stage": "live_transcription",
                    "code": "api_restart",
                    "message": "Live session stopped after API restart",
                    "timestamp": now_iso(),
                    "job_id": str(record.get("session_id") or "unknown"),
                }
                _write_json_atomic(meeting_dir / "meeting.json", card)
        except Exception:  # noqa: BLE001
            return

    @staticmethod
    def _public_record(record: dict[str, Any]) -> dict[str, Any]:
        model = _bounded_text(record.get("model"), maximum=160)
        if not model or _ABSOLUTE_PATH_RE.search(model):
            model = None
        warnings = []
        for value in record.get("warnings") or []:
            warning = _bounded_text(value, maximum=120)
            if warning and not _ABSOLUTE_PATH_RE.search(warning):
                warnings.append(warning)
            if len(warnings) >= 50:
                break
        error = record.get("error")
        safe_error = None
        if isinstance(error, dict):
            code = _bounded_text(error.get("code"), maximum=80)
            message = _bounded_text(error.get("message"), maximum=240)
            if not re.fullmatch(r"[a-z0-9_]+", code):
                code = "live_session_failed"
            if not message or _ABSOLUTE_PATH_RE.search(message):
                message = "Live transcription failed"
            safe_error = {"code": code, "message": message}
        return {
            "session_id": record["session_id"],
            "meeting_id": record["meeting_id"],
            "source": record["source"],
            "status": record["status"],
            "engine": "vosk" if record.get("engine") == "vosk" else None,
            "model": model,
            "vad": record.get("vad") if record.get("vad") in {"none", "silero"} else None,
            "created_at": record["created_at"],
            "started_at": record.get("started_at"),
            "updated_at": record["updated_at"],
            "finished_at": record.get("finished_at"),
            "last_event_id": int(record.get("last_event_id") or 0),
            "warnings": warnings,
            "error": safe_error,
            "artifact_keys": [
                key
                for key in record.get("artifact_keys") or []
                if key in _ARTIFACT_KEYS
            ][:20],
            "is_active": record["status"] in ACTIVE_STATUSES,
        }
