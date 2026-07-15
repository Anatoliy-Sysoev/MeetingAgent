from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from meeting_agent.api.auth import require_action_permission, require_permission
from meeting_agent.api.dependencies import get_app_state
from meeting_agent.auth.models import Principal
from meeting_agent.jobs.runner import (
    PIPELINE_PROFILES,
    STAGE_COMMANDS,
    read_last_error,
    JobAlreadyRunning,
    JobNotFound,
    JobNotRunning,
    JobRunner,
    JobStateUnavailable,
    PreflightFailed,
    _read_meeting_status,
    stage_catalog,
)
from pydantic import BaseModel, Field

from meeting_agent.jobs.readiness import pipeline_readiness
from meeting_agent.meetings.service import MeetingsService, _safe_meeting_id

router = APIRouter(tags=["jobs"])


def _job_error(status_code: int, exc: JobAlreadyRunning | JobStateUnavailable) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "code": str(getattr(exc, "code", "job_state_unavailable"))[:80],
            "message": str(getattr(exc, "public_message", str(exc)))[:240],
        },
    )


def _get_runner(request: Request) -> JobRunner:
    return get_app_state(request).job_runner


def _get_meetings_service(request: Request) -> MeetingsService:
    state = get_app_state(request)
    svc = getattr(state, "meetings_service", None)
    return svc if svc is not None else MeetingsService()


# ------------------------------------------------------------------
# GET /meetings/{meeting_id}/jobs/stages  — available pipeline stages (read)
# ------------------------------------------------------------------

@router.get("/meetings/{meeting_id}/jobs/stages")
async def list_job_stages(
    meeting_id: str,
    _principal: Annotated[Principal, Depends(require_permission("jobs.read"))],
    service: MeetingsService = Depends(_get_meetings_service),
) -> JSONResponse:
    if not _safe_meeting_id(meeting_id):
        raise HTTPException(status_code=404, detail=f"Meeting not found: {meeting_id!r}")
    if not (service.root / meeting_id / "meeting.json").exists():
        raise HTTPException(status_code=404, detail=f"Meeting not found: {meeting_id!r}")
    return JSONResponse(content={"meeting_id": meeting_id, "stages": stage_catalog()})


# ------------------------------------------------------------------
# GET /meetings/{meeting_id}/pipeline/readiness  — stage readiness map (read)
# ------------------------------------------------------------------

@router.get("/meetings/{meeting_id}/pipeline/readiness")
async def pipeline_readiness_map(
    meeting_id: str,
    _principal: Annotated[Principal, Depends(require_permission("jobs.read"))],
    asr_engine: Literal["faster-whisper", "gigaam"] = "faster-whisper",
    runner: JobRunner = Depends(_get_runner),
    service: MeetingsService = Depends(_get_meetings_service),
) -> JSONResponse:
    if not _safe_meeting_id(meeting_id):
        raise HTTPException(status_code=404, detail=f"Meeting not found: {meeting_id!r}")
    meeting_dir = service.root / meeting_id
    if not (meeting_dir / "meeting.json").exists():
        raise HTTPException(status_code=404, detail=f"Meeting not found: {meeting_id!r}")
    try:
        live_session_active = runner.live_session_active(meeting_id)
    except JobStateUnavailable as exc:
        raise _job_error(503, exc) from exc
    payload = pipeline_readiness(
        meeting_id,
        meeting_dir,
        live_session_active=live_session_active,
        worker_runtime_errors={
            stage: runner.worker_runtime_error(
                stage,
                {"asr_engine": asr_engine} if stage == "transcribe" else None,
            )
            for stage in STAGE_COMMANDS
        },
    )
    payload["job_recovery"] = runner.recovery_summary(meeting_id)
    return JSONResponse(content=payload)


# ------------------------------------------------------------------
# POST /meetings/{meeting_id}/jobs/pipeline  — run-all pipeline job (#115)
# Declared BEFORE the generic /jobs/{stage} route so "pipeline" is never
# captured as a stage name.
# ------------------------------------------------------------------

class PipelineRequest(BaseModel):
    profile: str = Field("default", max_length=32)
    force: bool = False
    asr_engine: Literal["faster-whisper", "gigaam"] = "faster-whisper"
    # resume=true explicitly continues after a failure: done stages are
    # skipped and execution starts at the first not-yet-done stage.  This is
    # also the default behavior; force=true overrides the skip.
    resume: bool = False
    stages: list[str] | None = Field(None, max_length=16)


class RetryRequest(BaseModel):
    force: bool = False


class StageStartRequest(BaseModel):
    asr_engine: Literal["faster-whisper", "gigaam"] = "faster-whisper"


@router.post("/meetings/{meeting_id}/jobs/pipeline", status_code=202)
async def start_pipeline(
    meeting_id: str,
    body: PipelineRequest,
    _principal: Annotated[Principal, Depends(require_action_permission("jobs.start"))],
    runner: JobRunner = Depends(_get_runner),
    service: MeetingsService = Depends(_get_meetings_service),
) -> JSONResponse:
    if not _safe_meeting_id(meeting_id):
        raise HTTPException(status_code=404, detail=f"Meeting not found: {meeting_id!r}")
    meeting_dir = service.root / meeting_id
    if not (meeting_dir / "meeting.json").exists():
        raise HTTPException(status_code=404, detail=f"Meeting not found: {meeting_id!r}")
    if body.stages is not None:
        unknown = [s for s in body.stages if s not in STAGE_COMMANDS]
        if unknown or not body.stages:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown stages: {unknown!r}. Allowed: {sorted(STAGE_COMMANDS)}",
            )
    elif body.profile not in PIPELINE_PROFILES:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown profile {body.profile!r}. Allowed: {sorted(PIPELINE_PROFILES)}",
        )
    try:
        pipeline = await runner.submit_pipeline(
            meeting_id=meeting_id,
            meeting_dir=meeting_dir,
            profile=body.profile,
            force=body.force,
            resume=body.resume,
            stages=body.stages,
            stage_options={"transcribe": {"asr_engine": body.asr_engine}},
        )
    except JobAlreadyRunning as exc:
        raise _job_error(409, exc) from exc
    except JobStateUnavailable as exc:
        raise _job_error(503, exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return JSONResponse(status_code=202, content=pipeline.as_dict())


# ------------------------------------------------------------------
# POST /meetings/{meeting_id}/jobs/{stage}/retry  — retry one stage (#120)
# ------------------------------------------------------------------

@router.post("/meetings/{meeting_id}/jobs/{stage}/retry", status_code=202)
async def retry_stage(
    meeting_id: str,
    stage: str,
    _principal: Annotated[Principal, Depends(require_action_permission("jobs.retry"))],
    body: RetryRequest | None = None,
    runner: JobRunner = Depends(_get_runner),
    service: MeetingsService = Depends(_get_meetings_service),
) -> JSONResponse:
    if not _safe_meeting_id(meeting_id):
        raise HTTPException(status_code=404, detail=f"Meeting not found: {meeting_id!r}")
    if stage not in STAGE_COMMANDS:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown stage {stage!r}. Allowed: {sorted(STAGE_COMMANDS)}",
        )
    meeting_dir = service.root / meeting_id
    if not (meeting_dir / "meeting.json").exists():
        raise HTTPException(status_code=404, detail=f"Meeting not found: {meeting_id!r}")

    force = bool(body.force) if body is not None else False
    # A stage whose output already exists needs an explicit force to re-run.
    from meeting_agent.jobs.readiness import _read_card, _stage_done

    if not force and _stage_done(stage, meeting_dir, _read_card(meeting_dir)):
        raise HTTPException(
            status_code=409,
            detail=f"Stage {stage!r} is already done; pass {{\"force\": true}} to re-run.",
        )
    try:
        job = await runner.submit(
            meeting_id=meeting_id, stage=stage, meeting_dir=meeting_dir
        )
    except JobAlreadyRunning as exc:
        raise _job_error(409, exc) from exc
    except JobStateUnavailable as exc:
        raise _job_error(503, exc) from exc
    except PreflightFailed as exc:
        raise HTTPException(status_code=422, detail=f"Preflight failed: {exc.detail}") from exc
    return JSONResponse(status_code=202, content=job.as_dict())


# ------------------------------------------------------------------
# POST /meetings/{meeting_id}/jobs/{stage}  — start a pipeline job
# ------------------------------------------------------------------

@router.post("/meetings/{meeting_id}/jobs/{stage}", status_code=202)
async def start_job(
    meeting_id: str,
    stage: str,
    _principal: Annotated[Principal, Depends(require_action_permission("jobs.start"))],
    body: StageStartRequest | None = None,
    runner: JobRunner = Depends(_get_runner),
    service: MeetingsService = Depends(_get_meetings_service),
) -> JSONResponse:
    if not _safe_meeting_id(meeting_id):
        raise HTTPException(status_code=404, detail=f"Meeting not found: {meeting_id!r}")
    if stage not in STAGE_COMMANDS:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown stage {stage!r}. Allowed: {sorted(STAGE_COMMANDS)}",
        )
    meeting_dir = service.root / meeting_id
    if not (meeting_dir / "meeting.json").exists():
        raise HTTPException(status_code=404, detail=f"Meeting not found: {meeting_id!r}")

    try:
        job = await runner.submit(
            meeting_id=meeting_id,
            stage=stage,
            meeting_dir=meeting_dir,
            stage_options={"asr_engine": body.asr_engine} if body and stage == "transcribe" else None,
        )
    except JobAlreadyRunning as exc:
        raise _job_error(409, exc) from exc
    except JobStateUnavailable as exc:
        raise _job_error(503, exc) from exc
    except PreflightFailed as exc:
        raise HTTPException(status_code=422, detail=f"Preflight failed: {exc.detail}") from exc

    return JSONResponse(status_code=202, content=job.as_dict())


# ------------------------------------------------------------------
# GET /meetings/{meeting_id}/jobs/{job_id}  — job status (read)
# ------------------------------------------------------------------

@router.get("/meetings/{meeting_id}/jobs/{job_id}")
async def get_job(
    meeting_id: str,
    job_id: str,
    _principal: Annotated[Principal, Depends(require_permission("jobs.read"))],
    runner: JobRunner = Depends(_get_runner),
    service: MeetingsService = Depends(_get_meetings_service),
) -> JSONResponse:
    try:
        job = runner.get_job_or_pipeline(job_id)
    except JobNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if job.meeting_id != meeting_id:
        raise HTTPException(
            status_code=404,
            detail=f"Job {job_id!r} does not belong to meeting {meeting_id!r}",
        )
    meeting_dir = service.root / meeting_id
    payload = job.as_dict(meeting_status=_read_meeting_status(meeting_dir))
    payload["is_active"] = runner.is_active(job_id)
    payload["last_error"] = read_last_error(meeting_dir)
    return JSONResponse(content=payload)


# ------------------------------------------------------------------
# POST /meetings/{meeting_id}/jobs/{job_id}/cancel
# ------------------------------------------------------------------

@router.post("/meetings/{meeting_id}/jobs/{job_id}/cancel")
async def cancel_job(
    meeting_id: str,
    job_id: str,
    _principal: Annotated[Principal, Depends(require_action_permission("jobs.cancel"))],
    runner: JobRunner = Depends(_get_runner),
) -> JSONResponse:
    try:
        job = runner.get_job_or_pipeline(job_id)
    except JobNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if job.meeting_id != meeting_id:
        raise HTTPException(
            status_code=404,
            detail=f"Job {job_id!r} does not belong to meeting {meeting_id!r}",
        )
    try:
        job = await runner.cancel(job_id)
    except JobNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except JobNotRunning as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return JSONResponse(content=job.as_dict())


# ------------------------------------------------------------------
# GET /jobs/active  — current active job (read)
# ------------------------------------------------------------------

@router.get("/jobs/active")
async def get_active_job(
    _principal: Annotated[Principal, Depends(require_permission("jobs.read"))],
    runner: JobRunner = Depends(_get_runner),
) -> JSONResponse:
    job = runner.get_active()
    if job is None:
        return JSONResponse(content={})
    payload = job.as_dict()
    payload["is_active"] = True
    return JSONResponse(content=payload)
