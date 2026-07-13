from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from asu_june_bot.api.auth import require_action_permission, require_permission
from asu_june_bot.auth.models import Principal
from asu_june_bot.live_sessions import (
    LiveSessionConflict,
    LiveSessionError,
    LiveSessionNotFound,
    LiveSessionNotRunning,
    LiveSessionPreflightFailed,
    LiveSessionService,
)
from asu_june_bot.live_sessions.store import LiveSessionStoreError
from asu_june_bot.jobs.runner import (
    JobAlreadyRunning,
    JobRunner,
    PreflightFailed,
)
from asu_june_bot.meetings.service import MeetingCardError, MeetingsService
from meeting_agent.transcription import (
    expected_live_audio_relative_path,
    live_refinement_status,
)


router = APIRouter(tags=["live-transcription"])


class LiveSessionStartRequest(BaseModel):
    source: Literal["MIC", "SYS", "MIX"] = "MIC"
    audio_device_index: int | None = Field(None, ge=0, le=65_535)
    duration_sec: float | None = Field(None, ge=1.0, le=43_200.0)
    vad: Literal["none", "silero"] | None = None
    force: bool = False


class LiveRefinementRequest(BaseModel):
    source: Literal["MIC", "SYS"] = "MIC"
    asr_engine: Literal["faster-whisper", "gigaam"] = "faster-whisper"
    force: bool = False
    resume: bool = False


def _get_service(request: Request) -> LiveSessionService:
    return request.app.state.asu_june_bot.live_session_service


def _get_runner(request: Request) -> JobRunner:
    return request.app.state.asu_june_bot.job_runner


def _get_meetings_service(request: Request) -> MeetingsService:
    state = request.app.state.asu_june_bot
    service = getattr(state, "meetings_service", None)
    return service if service is not None else MeetingsService()


def _http_error(exc: LiveSessionError | LiveSessionStoreError) -> HTTPException:
    if isinstance(exc, LiveSessionNotFound):
        status_code = 404
    elif isinstance(exc, (LiveSessionConflict, LiveSessionNotRunning)):
        status_code = 409
    elif isinstance(exc, LiveSessionPreflightFailed):
        status_code = 422
    else:
        status_code = 503
    code = getattr(exc, "code", "live_state_unavailable")
    message = getattr(exc, "public_message", "Live session state is unavailable")
    return HTTPException(
        status_code=status_code,
        detail={"code": str(code), "message": str(message)},
    )


def _refinement_error(
    status_code: int,
    code: str,
    message: str,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message[:240]},
    )


def _meeting_card(
    service: MeetingsService,
    meeting_id: str,
) -> tuple[dict[str, Any], Path]:
    try:
        meeting = service.get_meeting(meeting_id)
    except (MeetingCardError, OSError, ValueError, UnicodeError):
        raise _refinement_error(
            409,
            "meeting_card_invalid",
            "Meeting metadata is unavailable or invalid",
        ) from None
    if meeting is None:
        raise _refinement_error(404, "meeting_not_found", "Meeting not found")
    return meeting, service.root / meeting_id


def _active_job_for_meeting(runner: JobRunner, meeting_id: str) -> dict | None:
    job = runner.get_active()
    if job is None or job.meeting_id != meeting_id:
        return None
    return job.as_dict()


@router.get("/meetings/{meeting_id}/live/preflight")
async def live_preflight(
    meeting_id: str,
    source: Literal["MIC", "SYS", "MIX"] = Query("MIC"),
    audio_device_index: int | None = Query(None, ge=0, le=65_535),
    _principal: Annotated[Principal, Depends(require_permission("jobs.read"))] = None,
    service: LiveSessionService = Depends(_get_service),
) -> JSONResponse:
    try:
        await asyncio.to_thread(service.ensure_meeting, meeting_id)
        payload = await asyncio.to_thread(
            service.preflight,
            source,
            audio_device_index=audio_device_index,
        )
    except (LiveSessionError, LiveSessionStoreError) as exc:
        raise _http_error(exc) from exc
    return JSONResponse(content=payload)


@router.get("/meetings/{meeting_id}/live/refinement")
async def get_live_refinement(
    meeting_id: str,
    source: Literal["MIC", "SYS"] = Query("MIC"),
    _principal: Annotated[Principal, Depends(require_permission("jobs.read"))] = None,
    runner: JobRunner = Depends(_get_runner),
    service: MeetingsService = Depends(_get_meetings_service),
) -> JSONResponse:
    meeting, meeting_dir = _meeting_card(service, meeting_id)
    payload = live_refinement_status(
        meeting_dir,
        meeting,
        source=source,
        active_job=_active_job_for_meeting(runner, meeting_id),
    )
    payload["meeting_id"] = meeting_id
    return JSONResponse(content=payload)


@router.post("/meetings/{meeting_id}/live/refinement", status_code=202)
async def start_live_refinement(
    meeting_id: str,
    body: LiveRefinementRequest,
    _principal: Annotated[
        Principal,
        Depends(require_action_permission("jobs.start")),
    ],
    runner: JobRunner = Depends(_get_runner),
    live_service: LiveSessionService = Depends(_get_service),
    meetings_service: MeetingsService = Depends(_get_meetings_service),
) -> JSONResponse:
    if body.force and body.resume:
        raise _refinement_error(
            422,
            "refinement_retry_mode_invalid",
            "force and resume are mutually exclusive",
        )
    meeting, meeting_dir = _meeting_card(meetings_service, meeting_id)
    try:
        active_live = await asyncio.to_thread(live_service.active, meeting_id)
    except (LiveSessionError, LiveSessionStoreError) as exc:
        raise _http_error(exc) from exc
    if active_live is not None:
        raise _refinement_error(
            409,
            "live_session_active",
            "Stop live capture before offline refinement",
        )

    status = live_refinement_status(
        meeting_dir,
        meeting,
        source=body.source,
        active_job=_active_job_for_meeting(runner, meeting_id),
    )
    state = status["state"]
    if state == "unavailable":
        raise _refinement_error(
            409,
            str(status.get("reason") or "live_draft_missing"),
            "A complete saved live draft is required",
        )
    if state == "refining":
        raise _refinement_error(409, "refinement_active", "Offline refinement is already running")
    if state == "final" and not body.force:
        raise _refinement_error(
            409,
            "refinement_already_final",
            "Offline refinement is already final; use force to run it again",
        )
    if state == "failed" and not (body.resume or body.force):
        raise _refinement_error(
            409,
            "refinement_resume_required",
            "Resume or force is required after a failed refinement",
        )
    if state == "draft" and body.resume:
        raise _refinement_error(
            409,
            "refinement_not_failed",
            "Resume is available only after a failed refinement",
        )

    try:
        job = await runner.submit(
            meeting_id=meeting_id,
            stage="transcribe",
            meeting_dir=meeting_dir,
            stage_options={
                "asr_engine": body.asr_engine,
                "media_path": expected_live_audio_relative_path(body.source),
                "live_refinement_source": body.source,
                "force": body.force,
                "resume": body.resume,
            },
        )
    except JobAlreadyRunning as exc:
        raise _refinement_error(409, "job_already_running", str(exc)) from exc
    except PreflightFailed as exc:
        raise _refinement_error(
            422,
            "refinement_preflight_failed",
            "Offline refinement preflight failed",
        ) from exc

    return JSONResponse(
        status_code=202,
        content={
            "meeting_id": meeting_id,
            "source": body.source,
            "state": "refining",
            "job": job.as_dict(),
        },
    )


@router.get("/meetings/{meeting_id}/live/sessions/active")
async def active_live_session(
    meeting_id: str,
    source: Literal["MIC", "SYS", "MIX"] | None = Query(None),
    _principal: Annotated[Principal, Depends(require_permission("jobs.read"))] = None,
    service: LiveSessionService = Depends(_get_service),
) -> JSONResponse:
    try:
        await asyncio.to_thread(service.ensure_meeting, meeting_id)
        session = await asyncio.to_thread(service.active, meeting_id, source=source)
    except (LiveSessionError, LiveSessionStoreError) as exc:
        raise _http_error(exc) from exc
    return JSONResponse(content={"meeting_id": meeting_id, "session": session})


@router.post("/meetings/{meeting_id}/live/sessions", status_code=202)
async def start_live_session(
    meeting_id: str,
    body: LiveSessionStartRequest,
    _principal: Annotated[
        Principal,
        Depends(require_action_permission("jobs.start")),
    ],
    service: LiveSessionService = Depends(_get_service),
) -> JSONResponse:
    try:
        session = await asyncio.to_thread(
            service.start,
            meeting_id,
            source=body.source,
            audio_device_index=body.audio_device_index,
            duration_sec=body.duration_sec,
            vad=body.vad,
            force=body.force,
        )
    except (LiveSessionError, LiveSessionStoreError) as exc:
        raise _http_error(exc) from exc
    return JSONResponse(status_code=202, content=session)


@router.get("/meetings/{meeting_id}/live/sessions/{session_id}")
async def get_live_session(
    meeting_id: str,
    session_id: str,
    _principal: Annotated[Principal, Depends(require_permission("jobs.read"))],
    service: LiveSessionService = Depends(_get_service),
) -> JSONResponse:
    try:
        session = await asyncio.to_thread(service.get, meeting_id, session_id)
    except (LiveSessionError, LiveSessionStoreError) as exc:
        raise _http_error(exc) from exc
    return JSONResponse(content=session)


@router.get("/meetings/{meeting_id}/live/sessions/{session_id}/events")
async def get_live_events(
    meeting_id: str,
    session_id: str,
    after: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    _principal: Annotated[Principal, Depends(require_permission("jobs.read"))] = None,
    service: LiveSessionService = Depends(_get_service),
) -> JSONResponse:
    try:
        payload = await asyncio.to_thread(
            service.events,
            meeting_id,
            session_id,
            after=after,
            limit=limit,
        )
    except (LiveSessionError, LiveSessionStoreError) as exc:
        raise _http_error(exc) from exc
    return JSONResponse(content=payload)


@router.post("/meetings/{meeting_id}/live/sessions/{session_id}/stop")
async def stop_live_session(
    meeting_id: str,
    session_id: str,
    _principal: Annotated[
        Principal,
        Depends(require_action_permission("jobs.cancel")),
    ],
    service: LiveSessionService = Depends(_get_service),
) -> JSONResponse:
    try:
        session = await asyncio.to_thread(service.stop, meeting_id, session_id)
    except (LiveSessionError, LiveSessionStoreError) as exc:
        raise _http_error(exc) from exc
    return JSONResponse(content=session)
