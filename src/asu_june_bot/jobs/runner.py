from __future__ import annotations

import asyncio
import json
import re
import shutil
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[3]

# ---------------------------------------------------------------------------
# Preflight helpers — pure filesystem checks, no subprocess
# ---------------------------------------------------------------------------

def _artifact_map(card: dict[str, Any]) -> dict[str, Any]:
    artifacts = card.get("artifacts")
    return artifacts if isinstance(artifacts, dict) else {}


def _runner_media_files(card: dict[str, Any]) -> list[dict[str, Any]]:
    source = card.get("source")
    source_dict = source if isinstance(source, dict) else {}
    raw = source_dict.get("media_files")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _safe_resolve(meeting_dir: Path, rel_value: str) -> Path | None:
    """Resolve a meeting-relative path safely.

    Returns the resolved Path if it stays within meeting_dir, or None when the
    value is absolute, contains '..' traversal components, or resolves outside
    the meeting directory.  Never raises — callers treat None as 'path absent'.
    """
    rel = str(rel_value).replace("\\", "/")
    rel_path = Path(rel)
    if rel_path.is_absolute() or ".." in rel_path.parts:
        return None
    base = meeting_dir.resolve()
    target = (base / rel_path).resolve()
    try:
        target.relative_to(base)
        return target
    except ValueError:
        return None


def _read_card(meeting_dir: Path) -> tuple[str | None, dict[str, Any] | None]:
    """Return (error_str, data) for meeting.json. error_str is None on success."""
    card = meeting_dir / "meeting.json"
    if not meeting_dir.exists():
        return "meeting directory does not exist", None
    if not card.exists():
        return "meeting.json not found", None
    try:
        data = json.loads(card.read_text(encoding="utf-8"))
        return None, data
    except Exception as exc:
        return f"meeting.json unreadable: {exc}", None


def _extract_audio_preflight(meeting_dir: Path) -> str | None:
    if not shutil.which("ffmpeg"):
        return "ffmpeg not found in PATH; install ffmpeg to use extract_audio"
    err, data = _read_card(meeting_dir)
    if err:
        return err
    media_files = _runner_media_files(data or {})
    if not media_files:
        return "no source.media_files in meeting.json; upload a media file first"
    for media in media_files:
        path_val = media.get("path")
        if not path_val or path_val == "source/audio_16k_mono.wav":
            continue
        resolved = _safe_resolve(meeting_dir, path_val)
        if resolved is not None and resolved.exists():
            return None
    return "no existing source media file found; upload a media file first"


def _merge_preflight(meeting_dir: Path) -> str | None:
    """Return error string if merge preconditions are not met, else None."""
    err, data = _read_card(meeting_dir)
    if err:
        return err
    artifacts = _artifact_map(data or {})
    segments_rel = artifacts.get("segments")
    if segments_rel:
        resolved = _safe_resolve(meeting_dir, segments_rel)
        if resolved is not None and resolved.exists():
            return None
    if (meeting_dir / "transcript" / "segments.jsonl").exists():
        return None
    return "segments.jsonl not found; run transcribe first"


def _chunk_preflight(meeting_dir: Path) -> str | None:
    err, data = _read_card(meeting_dir)
    if err:
        return err
    artifacts = _artifact_map(data or {})
    speaker_rel = artifacts.get("speaker_transcript", "transcript/speaker_transcript.jsonl")
    resolved = _safe_resolve(meeting_dir, speaker_rel)
    if resolved is not None and resolved.exists():
        return None
    return "speaker_transcript.jsonl not found; run transcribe, diarize, and merge first"


def _enrich_preflight(meeting_dir: Path) -> str | None:
    err, data = _read_card(meeting_dir)
    if err:
        return err
    artifacts = _artifact_map(data or {})
    chunks_rel = artifacts.get("chunks", "transcript/chunks.jsonl")
    resolved = _safe_resolve(meeting_dir, chunks_rel)
    if resolved is not None and resolved.exists():
        return None
    return "chunks.jsonl not found; run chunk first"


def _index_preflight(meeting_dir: Path) -> str | None:
    err, data = _read_card(meeting_dir)
    if err:
        return err
    artifacts = _artifact_map(data or {})
    enriched_rel = artifacts.get("enriched_chunks", "artifacts/enriched_chunks.jsonl")
    resolved = _safe_resolve(meeting_dir, enriched_rel)
    if resolved is not None and resolved.exists():
        return None
    return "enriched_chunks.jsonl not found; run enrich first"


def _analyze_preflight(meeting_dir: Path) -> str | None:
    err, data = _read_card(meeting_dir)
    if err:
        return err
    artifacts = _artifact_map(data or {})
    enriched_rel = artifacts.get("enriched_chunks", "artifacts/enriched_chunks.jsonl")
    resolved = _safe_resolve(meeting_dir, enriched_rel)
    if resolved is not None and resolved.exists():
        return None
    return "enriched_chunks.jsonl not found; run enrich first"


# ---------------------------------------------------------------------------
# Stage command registry
# ---------------------------------------------------------------------------

STAGE_COMMANDS: dict[str, dict[str, Any]] = {
    "extract_audio": {
        "script": _ROOT / "scripts" / "21_extract_audio.py",
        "base_args": [],
        "supports_dry_run": False,
        "preflight": _extract_audio_preflight,
    },
    "transcribe": {
        # Pin the product offline ASR model explicitly. Without --model, the
        # script falls back to "small" when local config omits
        # transcription.model, which would silently downgrade UI-launched
        # transcription to draft quality. "small" remains available only via
        # an explicit CLI --model for drafts.
        "script": _ROOT / "scripts" / "22_transcribe_meeting.py",
        "base_args": ["--engine", "faster-whisper", "--model", "large-v3-turbo"],
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
        "preflight": _merge_preflight,
    },
    "chunk": {
        "script": _ROOT / "scripts" / "26_chunk_meeting.py",
        "base_args": ["--force"],
        "supports_dry_run": False,
        "preflight": _chunk_preflight,
    },
    "enrich": {
        "script": _ROOT / "scripts" / "27_enrich_meeting_chunks.py",
        "base_args": ["--force"],
        "supports_dry_run": False,
        "preflight": _enrich_preflight,
    },
    "index": {
        "script": _ROOT / "scripts" / "28_index_meeting_chunks.py",
        "base_args": [],
        "supports_dry_run": False,
        "preflight": _index_preflight,
    },
    "analyze": {
        "script": _ROOT / "scripts" / "29_analyze_meeting.py",
        "base_args": ["--mode", "extractive", "--force"],
        "supports_dry_run": False,
        "preflight": _analyze_preflight,
    },
}

# UI-facing metadata for each runnable stage. Keys MUST be a subset of
# STAGE_COMMANDS — only stages the runner can actually execute are surfaced,
# so the workspace never offers a button for an unimplemented stage.
# No filesystem paths are described here; `requires`/`outputs` are abstract
# capability tokens. `order` controls display order in the Pipeline panel.
STAGE_METADATA: dict[str, dict[str, Any]] = {
    "extract_audio": {
        "label": "Extract audio",
        "description": "Extract normalized 16 kHz mono WAV audio from source media.",
        "requires": ["source_media"],
        "outputs": ["normalized_audio"],
        "order": 10,
    },
    "transcribe": {
        "label": "Transcribe",
        "description": "Offline ASR of the meeting audio into transcript segments.",
        "requires": ["source_media"],
        "outputs": ["transcript_segments"],
        "order": 20,
    },
    "diarize": {
        "label": "Diarize",
        "description": "Detect and label distinct speakers in the audio.",
        "requires": ["source_media"],
        "outputs": ["speaker_segments"],
        "order": 30,
    },
    "merge": {
        "label": "Merge transcript and speakers",
        "description": "Combine transcript segments with speaker labels.",
        "requires": ["transcript_segments", "speaker_segments"],
        "outputs": ["merged_transcript"],
        "order": 40,
    },
    "chunk": {
        "label": "Chunk transcript",
        "description": "Produce time-window chunks from merged transcript for retrieval.",
        "requires": ["merged_transcript"],
        "outputs": ["meeting_chunks"],
        "order": 50,
    },
    "enrich": {
        "label": "Enrich chunks",
        "description": "Add semantic metadata (topics, decisions, action items, risks) to chunks.",
        "requires": ["meeting_chunks"],
        "outputs": ["enriched_chunks"],
        "order": 60,
    },
    "index": {
        "label": "Index meeting",
        "description": "Write enriched chunks to the meeting search index for workspace Q&A.",
        "requires": ["enriched_chunks"],
        "outputs": ["meeting_search_index"],
        "order": 70,
    },
    "analyze": {
        "label": "Analyze meeting",
        "description": "Generate memo, protocol, decisions, action items, risks, and open questions.",
        "requires": ["enriched_chunks"],
        "outputs": ["meeting_artifacts"],
        "order": 80,
    },
}


def stage_catalog() -> list[dict[str, Any]]:
    """Return the ordered, UI-safe list of runnable pipeline stages.

    Only stages present in both STAGE_COMMANDS and STAGE_METADATA are
    returned, sorted by `order`. Each entry carries the permissions a caller
    needs to start/cancel the stage. Contains no filesystem paths or command
    details.
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
            "order": meta["order"],
        })
    catalog.sort(key=lambda e: e["order"])
    return catalog


_STDERR_TAIL = 20
_HISTORY_MAX = 20

# Repo root is used as an additional redaction root for all jobs.
_REPO_ROOT = _ROOT.resolve()


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


def _path_variants(path: Path) -> set[str]:
    """Return all string forms of a path that may appear in subprocess output."""
    variants: set[str] = set()
    for p in (path, path.resolve()):
        s = str(p)
        variants.add(s)
        variants.add(s.replace("\\", "/"))
        variants.add(s.replace("/", "\\"))
        variants.add(s.lower())
        variants.add(s.replace("\\", "/").lower())
        variants.add(s.replace("/", "\\").lower())
    return {v for v in variants if v and v != "/"}


def _redact_paths(line: str, roots: list[Path]) -> str:
    """Replace occurrences of known server filesystem roots with '<path>'."""
    for root in roots:
        for variant in _path_variants(root):
            line = re.sub(re.escape(variant), "<path>", line, flags=re.IGNORECASE)
    return line


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
    _meeting_dir: Path | None = field(default=None, repr=False, compare=False)

    def as_dict(self, meeting_status: str | None = None) -> dict[str, Any]:
        roots: list[Path] = [_REPO_ROOT]
        if self._meeting_dir is not None:
            roots.append(self._meeting_dir)
        stderr_tail = [
            _redact_paths(line, roots)
            for line in self.stderr_lines[-_STDERR_TAIL:]
        ]
        d: dict[str, Any] = {
            "job_id": self.job_id,
            "meeting_id": self.meeting_id,
            "stage": self.stage,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "exit_code": self.exit_code,
            "stderr_tail": stderr_tail,
        }
        if meeting_status is not None:
            d["meeting_status"] = meeting_status
        return d


# ---------------------------------------------------------------------------
# Pipeline (run-all) — MA-MEETING-PIPELINE-RUN-ALL (#115)
# ---------------------------------------------------------------------------

# Stage sequences per profile. Only stages from STAGE_COMMANDS are allowed.
PIPELINE_PROFILES: dict[str, list[str]] = {
    "default": ["extract_audio", "transcribe", "merge", "chunk", "enrich", "index"],
    "full": [
        "extract_audio", "transcribe", "diarize", "merge",
        "chunk", "enrich", "index", "analyze",
    ],
    "transcript_only": ["extract_audio", "transcribe"],
    "qa_ready": ["extract_audio", "transcribe", "merge", "chunk", "enrich", "index"],
}

_PIPELINE_POLL_SEC = 0.2


@dataclass
class PipelineJobState:
    """Aggregate job that runs pipeline stages sequentially."""

    job_id: str
    meeting_id: str
    profile: str
    force: bool
    status: str  # running | completed | failed | cancelled
    started_at: str
    stages: list[dict[str, Any]] = field(default_factory=list)
    # per item: {stage, status: pending|skipped|running|completed|failed|cancelled,
    #            job_id, exit_code, reason}
    resume: bool = False
    current_stage: str | None = None
    finished_at: str | None = None
    _meeting_dir: Path | None = field(default=None, repr=False, compare=False)

    def as_dict(self, meeting_status: str | None = None) -> dict[str, Any]:
        d: dict[str, Any] = {
            "job_id": self.job_id,
            "meeting_id": self.meeting_id,
            "kind": "pipeline",
            "profile": self.profile,
            "force": self.force,
            "resume": self.resume,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "current_stage": self.current_stage,
            "stages": [dict(item) for item in self.stages],
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


def _write_last_error(
    meeting_dir: Path, *, stage: str, job_id: str, exit_code: int | None
) -> None:
    """Record a normalized, public-safe last_error in meeting.json (#120).

    Never stores stderr/stack traces/paths — the full redacted stderr tail
    stays only in the runtime job state.  Failures to update the card are
    swallowed: error reporting must never break job bookkeeping.
    """
    card_path = meeting_dir / "meeting.json"
    try:
        card = json.loads(card_path.read_text(encoding="utf-8"))
        if not isinstance(card, dict):
            return
        card["last_error"] = {
            "stage": stage,
            "code": "stage_failed",
            "message": f"Stage '{stage}' failed (exit code {exit_code})",
            "timestamp": _now_iso(),
            "job_id": job_id,
        }
        card_path.write_text(
            json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:  # noqa: BLE001
        return


def _clear_last_error(meeting_dir: Path, *, stage: str) -> None:
    """Remove last_error from meeting.json after the same stage succeeds."""
    card_path = meeting_dir / "meeting.json"
    try:
        card = json.loads(card_path.read_text(encoding="utf-8"))
        if not isinstance(card, dict):
            return
        last = card.get("last_error")
        if isinstance(last, dict) and last.get("stage") == stage:
            card.pop("last_error", None)
            card_path.write_text(
                json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8"
            )
    except Exception:  # noqa: BLE001
        return


def read_last_error(meeting_dir: Path) -> dict[str, Any] | None:
    """Return the normalized last_error from meeting.json, or None."""
    card_path = meeting_dir / "meeting.json"
    try:
        card = json.loads(card_path.read_text(encoding="utf-8"))
        last = card.get("last_error") if isinstance(card, dict) else None
        return last if isinstance(last, dict) else None
    except Exception:  # noqa: BLE001
        return None


def _read_meeting_status(meeting_dir: Path) -> str | None:
    card = meeting_dir / "meeting.json"
    if not card.exists():
        return None
    try:
        return json.loads(card.read_text(encoding="utf-8")).get("processing_status")
    except Exception:
        return None


class JobRunner:
    def __init__(self) -> None:
        self._lock: asyncio.Lock = asyncio.Lock()
        self.active_job: JobState | None = None
        self.history: list[JobState] = []
        self.active_pipeline: PipelineJobState | None = None
        self.pipeline_history: list[PipelineJobState] = []

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

    def _find_pipeline(self, job_id: str) -> PipelineJobState | None:
        if self.active_pipeline and self.active_pipeline.job_id == job_id:
            return self.active_pipeline
        for job in self.pipeline_history:
            if job.job_id == job_id:
                return job
        return None

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
        # Normalized last_error bookkeeping (#120): failures record a
        # public-safe error in meeting.json; a later success of the same
        # stage clears it.  Cancellations do not touch last_error.
        if job._meeting_dir is not None:
            if job.status == "failed":
                _write_last_error(
                    job._meeting_dir,
                    stage=job.stage,
                    job_id=job.job_id,
                    exit_code=job.exit_code,
                )
            elif job.status == "completed":
                _clear_last_error(job._meeting_dir, stage=job.stage)
        async with self._lock:
            if self.active_job is job:
                self.active_job = None
        self._add_history(job)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def submit(
        self,
        *,
        meeting_id: str,
        stage: str,
        meeting_dir: Path,
        _from_pipeline: bool = False,
    ) -> JobState:
        if self.active_pipeline is not None and not _from_pipeline:
            raise JobAlreadyRunning("A pipeline job is already running. Cancel it first.")
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
                _meeting_dir=meeting_dir.resolve(),
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
                preflight_fn = cfg.get("preflight")
                if preflight_fn is not None:
                    err = preflight_fn(meeting_dir)
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

    async def cancel(self, job_id: str) -> JobState | PipelineJobState:
        pipeline = self._find_pipeline(job_id)
        if pipeline is not None:
            return await self._cancel_pipeline(pipeline)
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

    # ------------------------------------------------------------------
    # Pipeline (run-all)
    # ------------------------------------------------------------------

    def get_job_or_pipeline(self, job_id: str) -> JobState | PipelineJobState:
        pipeline = self._find_pipeline(job_id)
        if pipeline is not None:
            return pipeline
        return self._find_job(job_id)

    async def submit_pipeline(
        self,
        *,
        meeting_id: str,
        meeting_dir: Path,
        profile: str = "default",
        force: bool = False,
        resume: bool = False,
        stages: list[str] | None = None,
    ) -> PipelineJobState:
        """Start a sequential pipeline job. Returns its aggregate state.

        Stage plan comes from PIPELINE_PROFILES[profile] unless an explicit
        ``stages`` subset is given (each must be a known runnable stage).
        Already-done stages are skipped unless ``force``.
        """
        plan = list(stages) if stages else PIPELINE_PROFILES.get(profile) or []
        if not plan:
            raise ValueError(f"Unknown pipeline profile: {profile!r}")
        unknown = [s for s in plan if s not in STAGE_COMMANDS]
        if unknown:
            raise ValueError(f"Unknown stages: {unknown!r}")

        async with self._lock:
            if self.active_job is not None or self.active_pipeline is not None:
                raise JobAlreadyRunning("A job is already running. Cancel it first.")
            pstate = PipelineJobState(
                job_id=str(uuid.uuid4()),
                meeting_id=meeting_id,
                profile=profile if not stages else "custom",
                force=force,
                resume=resume,
                status="running",
                started_at=_now_iso(),
                stages=[
                    {"stage": s, "status": "pending", "job_id": None,
                     "exit_code": None, "reason": None}
                    for s in plan
                ],
                _meeting_dir=meeting_dir.resolve(),
            )
            self.active_pipeline = pstate
        asyncio.create_task(self._run_pipeline(pstate, meeting_dir))
        return pstate

    async def _cancel_pipeline(self, pipeline: PipelineJobState) -> PipelineJobState:
        if pipeline.status != "running":
            raise JobNotRunning(
                f"Job {pipeline.job_id!r} is not running (status={pipeline.status!r})"
            )
        pipeline.status = "cancelled"
        # Cancel the currently running child stage, if any.
        child = self.active_job
        if child is not None and child.status in ("starting", "running"):
            try:
                await self.cancel(child.job_id)
            except JobNotRunning:
                pass
        return pipeline

    async def _run_pipeline(self, pstate: PipelineJobState, meeting_dir: Path) -> None:
        # Local import avoids a cycle: readiness imports runner constants.
        from asu_june_bot.jobs.readiness import _read_card, _stage_done

        try:
            for item in pstate.stages:
                if pstate.status == "cancelled":
                    item["status"] = "cancelled"
                    continue
                stage = item["stage"]
                card = _read_card(meeting_dir)
                if not pstate.force and _stage_done(stage, meeting_dir, card):
                    item["status"] = "skipped"
                    item["reason"] = "already_done"
                    continue
                pstate.current_stage = stage
                item["status"] = "running"
                try:
                    child = await self.submit(
                        meeting_id=pstate.meeting_id,
                        stage=stage,
                        meeting_dir=meeting_dir,
                        _from_pipeline=True,
                    )
                except PreflightFailed as exc:
                    item["status"] = "failed"
                    item["reason"] = str(exc)
                    pstate.status = "failed"
                    break
                except JobAlreadyRunning:
                    item["status"] = "failed"
                    item["reason"] = "another job occupied the runner"
                    pstate.status = "failed"
                    break
                item["job_id"] = child.job_id
                while child.status in ("starting", "running"):
                    await asyncio.sleep(_PIPELINE_POLL_SEC)
                item["exit_code"] = child.exit_code
                if child.status == "completed":
                    item["status"] = "completed"
                    continue
                # failed or cancelled child stops the pipeline
                item["status"] = child.status
                if pstate.status != "cancelled":
                    pstate.status = "failed" if child.status == "failed" else "cancelled"
                break
            else:
                if pstate.status == "running":
                    pstate.status = "completed"
            # Mark any untouched stages after an early stop.
            stop_label = "cancelled" if pstate.status == "cancelled" else "skipped"
            for item in pstate.stages:
                if item["status"] == "pending":
                    item["status"] = stop_label
                    if stop_label == "skipped":
                        item["reason"] = "pipeline stopped on earlier failure"
        finally:
            pstate.current_stage = None
            pstate.finished_at = _now_iso()
            if pstate.status == "running":
                pstate.status = "completed"
            async with self._lock:
                if self.active_pipeline is pstate:
                    self.active_pipeline = None
            self.pipeline_history.append(pstate)
            if len(self.pipeline_history) > _HISTORY_MAX:
                self.pipeline_history = self.pipeline_history[-_HISTORY_MAX:]
