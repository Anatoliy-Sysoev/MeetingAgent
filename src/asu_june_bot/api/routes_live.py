from __future__ import annotations

import asyncio
from typing import Annotated, Literal

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


router = APIRouter(tags=["live-transcription"])


class LiveSessionStartRequest(BaseModel):
    source: Literal["MIC", "SYS", "MIX"] = "MIC"
    audio_device_index: int | None = Field(None, ge=0, le=65_535)
    duration_sec: float | None = Field(None, ge=1.0, le=43_200.0)
    vad: Literal["none", "silero"] | None = None
    force: bool = False


def _get_service(request: Request) -> LiveSessionService:
    return request.app.state.asu_june_bot.live_session_service


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
