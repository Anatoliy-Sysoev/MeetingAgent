from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from asu_june_bot.api.auth import require_action_permission, require_permission
from asu_june_bot.auth.models import Principal
from asu_june_bot.jobs.runner import (
    PIPELINE_PROFILES,
    STAGE_COMMANDS,
    JobAlreadyRunning,
    JobNotFound,
    JobNotRunning,
    JobRunner,
    PreflightFailed,
    _read_meeting_status,
    stage_catalog,
)
from pydantic import BaseModel, Field

from asu_june_bot.jobs.readiness import pipeline_readiness
from asu_june_bot.meetings.service import MeetingsService, _safe_meeting_id

router = APIRouter(tags=["jobs"])


def _get_runner(request: Request) -> JobRunner:
    return request.app.state.asu_june_bot.job_runner


def _get_meetings_service(request: Request) -> MeetingsService:
    state = request.app.state.asu_june_bot
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
    service: MeetingsService = Depends(_get_meetings_service),
) -> JSONResponse:
    if not _safe_meeting_id(meeting_id):
        raise HTTPException(status_code=404, detail=f"Meeting not found: {meeting_id!r}")
    meeting_dir = service.root / meeting_id
    if not (meeting_dir / "meeting.json").exists():
        raise HTTPException(status_code=404, detail=f"Meeting not found: {meeting_id!r}")
    return JSONResponse(content=pipeline_readiness(meeting_id, meeting_dir))


# ------------------------------------------------------------------
# POST /meetings/{meeting_id}/jobs/pipeline  — run-all pipeline job (#115)
# Declared BEFORE the generic /jobs/{stage} route so "pipeline" is never
# captured as a stage name.
# ------------------------------------------------------------------

class PipelineRequest(BaseModel):
    profile: str = Field("default", max_length=32)
    force: bool = False
    stages: list[str] | None = Field(None, max_length=16)


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
            stages=body.stages,
        )
    except JobAlreadyRunning as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return JSONResponse(status_code=202, content=pipeline.as_dict())


# ------------------------------------------------------------------
# POST /meetings/{meeting_id}/jobs/{stage}  — start a pipeline job
# ------------------------------------------------------------------

@router.post("/meetings/{meeting_id}/jobs/{stage}", status_code=202)
async def start_job(
    meeting_id: str,
    stage: str,
    _principal: Annotated[Principal, Depends(require_action_permission("jobs.start"))],
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
            meeting_id=meeting_id, stage=stage, meeting_dir=meeting_dir
        )
    except JobAlreadyRunning as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
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
    return JSONResponse(content=job.as_dict(meeting_status=_read_meeting_status(meeting_dir)))


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
    return JSONResponse(content=job.as_dict() if job else {})
