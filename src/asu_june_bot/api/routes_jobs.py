from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from asu_june_bot.api.auth import require_action_permission, require_permission
from asu_june_bot.auth.models import Principal
from asu_june_bot.jobs.runner import (
    STAGE_COMMANDS,
    JobAlreadyRunning,
    JobNotFound,
    JobNotRunning,
    JobRunner,
    PreflightFailed,
    _read_meeting_status,
    stage_catalog,
)
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
        job = runner._find_job(job_id)
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
        job = runner._find_job(job_id)
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
