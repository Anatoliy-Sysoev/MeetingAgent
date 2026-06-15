from __future__ import annotations

import asyncio
import json
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[3]

STAGE_COMMANDS: dict[str, dict[str, Any]] = {
    "transcribe": {
        "script": _ROOT / "scripts" / "22_transcribe_meeting.py",
        "base_args": ["--engine", "faster-whisper"],
        "supports_dry_run": True,
    },
    "diarize": {
        "script": _ROOT / "scripts" / "23_diarize_meeting.py",
        "base_args": [],
        "supports_dry_run": True,
    },
    "merge": {
        "script": _ROOT / "scripts" / "24_merge_transcript_speakers.py",
        "base_args": [],
        "supports_dry_run": False,
    },
}

# UI-facing metadata for each runnable stage. Keys MUST be a subset of
# STAGE_COMMANDS — only stages the runner can actually execute are surfaced,
# so the workspace never offers a button for an unimplemented stage.
# No filesystem paths are described here; `requires`/`outputs` are abstract
# capability tokens, not paths.
STAGE_METADATA: dict[str, dict[str, Any]] = {
    "transcribe": {
        "label": "Transcribe",
        "description": "Offline ASR of the meeting audio into transcript segments.",
        "requires": ["source_media"],
        "outputs": ["transcript_segments"],
    },
    "diarize": {
        "label": "Diarize",
        "description": "Detect and label distinct speakers in the audio.",
        "requires": ["source_media"],
        "outputs": ["speaker_segments"],
    },
    "merge": {
        "label": "Merge transcript and speakers",
        "description": "Combine transcript segments with speaker labels.",
        "requires": ["transcript_segments", "speaker_segments"],
        "outputs": ["merged_transcript"],
    },
}


def stage_catalog() -> list[dict[str, Any]]:
    """Return the ordered, UI-safe list of runnable pipeline stages.

    Only stages present in both STAGE_COMMANDS and STAGE_METADATA are
    returned, in STAGE_COMMANDS insertion order. Each entry carries the
    permissions a caller needs to start/cancel the stage. Contains no
    filesystem paths or command details.
    """
    catalog: list[dict[str, Any]] = []
    for stage in STAGE_COMMANDS:
        meta = STAGE_METADATA.get(stage)
        if meta is None:
            continue
        catalog.append({
            "stage": stage,
            "label": meta["label"],
            "description": meta["description"],
            "start_permission": "jobs.start",
            "cancel_permission": "jobs.cancel",
            "requires": list(meta["requires"]),
            "outputs": list(meta["outputs"]),
        })
    return catalog


_STDERR_TAIL = 20
_HISTORY_MAX = 20


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


class JobError(RuntimeError):
    pass


class JobAlreadyRunning(JobError):
    pass


class JobNotFound(JobError):
    pass


class JobNotRunning(JobError):
    pass


class PreflightFailed(JobError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


# Backward-compat alias — remove once all callers updated
PrefightFailed = PreflightFailed


@dataclass
class JobState:
    job_id: str
    meeting_id: str
    stage: str
    status: str  # starting | running | completed | failed | cancelled
    started_at: str
    pid: int | None = None
    finished_at: str | None = None
    exit_code: int | None = None
    stderr_lines: list[str] = field(default_factory=list)
    _process: Any = field(default=None, repr=False, compare=False)

    def as_dict(self, meeting_status: str | None = None) -> dict[str, Any]:
        d: dict[str, Any] = {
            "job_id": self.job_id,
            "meeting_id": self.meeting_id,
            "stage": self.stage,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "exit_code": self.exit_code,
            "stderr_tail": self.stderr_lines[-_STDERR_TAIL:],
        }
        if meeting_status is not None:
            d["meeting_status"] = meeting_status
        return d


async def _create_subprocess(
    *args: str,
    stdout: int,
    stderr: int,
) -> Any:
    return await asyncio.create_subprocess_exec(*args, stdout=stdout, stderr=stderr)


def _read_meeting_status(meeting_dir: Path) -> str | None:
    card = meeting_dir / "meeting.json"
    if not card.exists():
        return None
    try:
        return json.loads(card.read_text(encoding="utf-8")).get("processing_status")
    except Exception:
        return None


def _merge_preflight(meeting_dir: Path) -> str | None:
    """Return error string if merge preconditions are not met, else None."""
    if not meeting_dir.exists():
        return "meeting directory does not exist"
    card = meeting_dir / "meeting.json"
    if not card.exists():
        return "meeting.json not found"
    try:
        data = json.loads(card.read_text(encoding="utf-8"))
    except Exception as exc:
        return f"meeting.json unreadable: {exc}"
    artifacts: dict[str, str] = data.get("artifacts") or {}
    segments_rel = artifacts.get("segments")
    if segments_rel:
        try:
            p = (meeting_dir / segments_rel).resolve()
            p.relative_to(meeting_dir.resolve())
            if p.exists():
                return None
        except ValueError:
            pass
    if (meeting_dir / "transcript" / "segments.jsonl").exists():
        return None
    return "segments.jsonl not found; run transcribe first"


class JobRunner:
    def __init__(self) -> None:
        self._lock: asyncio.Lock = asyncio.Lock()
        self.active_job: JobState | None = None
        self.history: list[JobState] = []

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _find_job(self, job_id: str) -> JobState:
        if self.active_job and self.active_job.job_id == job_id:
            return self.active_job
        for job in self.history:
            if job.job_id == job_id:
                return job
        raise JobNotFound(f"Job not found: {job_id!r}")

    def _add_history(self, job: JobState) -> None:
        self.history.append(job)
        if len(self.history) > _HISTORY_MAX:
            self.history = self.history[-_HISTORY_MAX:]

    async def _monitor(self, job: JobState) -> None:
        proc = job._process
        if proc is None:
            return
        try:
            _, stderr_bytes = await proc.communicate()
        except Exception:
            stderr_bytes = b""
        if stderr_bytes:
            job.stderr_lines = (
                stderr_bytes.decode("utf-8", errors="replace").splitlines()[-_STDERR_TAIL:]
            )
        job.finished_at = _now_iso()
        job.exit_code = proc.returncode
        if job.status not in ("cancelled",):
            job.status = "completed" if proc.returncode == 0 else "failed"
        async with self._lock:
            if self.active_job is job:
                self.active_job = None
        self._add_history(job)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def submit(self, *, meeting_id: str, stage: str, meeting_dir: Path) -> JobState:
        cfg = STAGE_COMMANDS[stage]
        script: Path = cfg["script"]
        base_args: list[str] = cfg["base_args"]
        supports_dry_run: bool = cfg["supports_dry_run"]

        cmd = [sys.executable, str(script), "--meeting-dir", str(meeting_dir), *base_args]

        # Reserve concurrency slot
        async with self._lock:
            if self.active_job is not None:
                raise JobAlreadyRunning("A job is already running. Cancel it first.")
            job = JobState(
                job_id=str(uuid.uuid4()),
                meeting_id=meeting_id,
                stage=stage,
                status="starting",
                started_at=_now_iso(),
            )
            self.active_job = job

        try:
            # Preflight
            if supports_dry_run:
                proc = await _create_subprocess(
                    *cmd, "--dry-run",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr_bytes = await proc.communicate()
                if proc.returncode != 0:
                    detail = (stderr_bytes or b"").decode("utf-8", errors="replace").strip()
                    raise PreflightFailed(detail or "dry-run failed")
            else:
                err = _merge_preflight(meeting_dir)
                if err:
                    raise PreflightFailed(err)

            # Launch real process
            proc = await _create_subprocess(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            job.pid = proc.pid
            job.status = "running"
            job._process = proc
            asyncio.create_task(self._monitor(job))
            return job

        except Exception:
            async with self._lock:
                if self.active_job is job:
                    self.active_job = None
            raise

    async def cancel(self, job_id: str) -> JobState:
        job = self._find_job(job_id)
        if job.status not in ("starting", "running"):
            raise JobNotRunning(
                f"Job {job_id!r} is not running (status={job.status!r})"
            )
        job.status = "cancelled"
        job.finished_at = _now_iso()
        if job._process is not None:
            job._process.terminate()
        # Do NOT clear active_job here — _monitor releases the slot after the
        # process actually exits, keeping concurrency=1 intact until then.
        return job

    def get_active(self) -> JobState | None:
        return self.active_job
