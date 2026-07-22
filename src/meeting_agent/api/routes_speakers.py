from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from meeting_agent.api.auth import require_action_permission, require_permission
from meeting_agent.api.dependencies import get_app_state
from meeting_agent.auth.models import Principal
from meeting_agent.meetings.service import MeetingsService
from meeting_agent.speakers import (
    DuplicateSpeakerProfileError,
    SpeakerProfileNotFoundError,
)


router = APIRouter(prefix="/speakers", tags=["speakers"])
_SPEAKER_ID_RE = re.compile(r"^spk_[0-9a-f]{32}$")


def _service(request: Request) -> MeetingsService:
    state = get_app_state(request)
    return getattr(state, "meetings_service", None) or MeetingsService()


class SpeakerProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    role: str = Field(default="", max_length=120)
    company: str = Field(default="", max_length=120)
    aliases: list[str] = Field(default_factory=list, max_length=20)
    notes: str = Field(default="", max_length=500)


def _safe_id(speaker_id: str) -> str:
    if not _SPEAKER_ID_RE.fullmatch(speaker_id):
        raise HTTPException(status_code=404, detail={"error": "speaker_profile_not_found"})
    return speaker_id


def _write_error(exc: Exception) -> HTTPException:
    if isinstance(exc, DuplicateSpeakerProfileError):
        return HTTPException(
            status_code=409,
            detail={"error": "speaker_profile_duplicate", "message": "Speaker profile already exists"},
        )
    if isinstance(exc, SpeakerProfileNotFoundError):
        return HTTPException(status_code=404, detail={"error": "speaker_profile_not_found"})
    return HTTPException(
        status_code=422,
        detail={"error": "invalid_speaker_profile", "message": "Speaker profile is invalid"},
    )


@router.get("")
def list_speaker_profiles(
    query: str = Query(default="", max_length=120),
    service: MeetingsService = Depends(_service),
    _principal: Annotated[Principal, Depends(require_permission("meetings.edit"))] = ...,
) -> dict:
    try:
        profiles = service.list_speaker_profiles(query=query)
    except ValueError as exc:
        raise HTTPException(
            status_code=503,
            detail={"error": "speaker_directory_unavailable", "message": "Speaker directory is unavailable"},
        ) from exc
    return {"profiles": profiles, "count": len(profiles)}


@router.post("", status_code=201)
def create_speaker_profile(
    payload: SpeakerProfileRequest,
    service: MeetingsService = Depends(_service),
    _principal: Annotated[Principal, Depends(require_action_permission("meetings.edit"))] = ...,
) -> dict:
    try:
        return service.create_speaker_profile(payload.model_dump())
    except (DuplicateSpeakerProfileError, ValueError) as exc:
        raise _write_error(exc) from exc


@router.put("/{speaker_id}")
def update_speaker_profile(
    speaker_id: str,
    payload: SpeakerProfileRequest,
    service: MeetingsService = Depends(_service),
    _principal: Annotated[Principal, Depends(require_action_permission("meetings.edit"))] = ...,
) -> dict:
    try:
        return service.update_speaker_profile(_safe_id(speaker_id), payload.model_dump())
    except (DuplicateSpeakerProfileError, SpeakerProfileNotFoundError, ValueError) as exc:
        raise _write_error(exc) from exc


@router.delete("/{speaker_id}", status_code=204)
def delete_speaker_profile(
    speaker_id: str,
    service: MeetingsService = Depends(_service),
    _principal: Annotated[Principal, Depends(require_action_permission("meetings.edit"))] = ...,
) -> Response:
    try:
        service.delete_speaker_profile(_safe_id(speaker_id))
    except (SpeakerProfileNotFoundError, ValueError) as exc:
        raise _write_error(exc) from exc
    return Response(status_code=204)
