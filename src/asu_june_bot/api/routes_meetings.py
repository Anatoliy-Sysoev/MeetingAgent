from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import FileResponse

from asu_june_bot.api.auth import require_action_permission, require_permission
from asu_june_bot.api.dependencies import get_meeting_qa_service
from asu_june_bot.auth.models import Principal
from asu_june_bot.core.limits import MAX_QUERY_CHARS
from asu_june_bot.meetings.manifest import build_artifact_manifest
from asu_june_bot.meetings.qa import MeetingQAService
from asu_june_bot.meetings.service import (
    ArtifactTooLargeError,
    MeetingCardError,
    MeetingsService,
    _safe_meeting_id,
)

router = APIRouter(prefix="/meetings", tags=["meetings"])

_require_read = require_permission("meetings.read")


def get_meetings_service(request: Request) -> MeetingsService:
    state = request.app.state.asu_june_bot
    return getattr(state, "meetings_service", None) or MeetingsService()


def _not_found(meeting_id: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"Meeting not found: {meeting_id!r}")


def _invalid_card(exc: MeetingCardError) -> HTTPException:
    return HTTPException(status_code=422, detail=f"Invalid meeting card: {exc}")


def _too_large(exc: ArtifactTooLargeError) -> HTTPException:
    return HTTPException(
        status_code=413,
        detail={
            "error": "artifact_too_large",
            "artifact": exc.artifact,
            "size_bytes": exc.size_bytes,
            "max_bytes": exc.max_bytes,
        },
    )


class SpeakerMappingEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="", max_length=120)
    role: str = Field(default="", max_length=120)


class SpeakerMappingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mapping: dict[str, SpeakerMappingEntry] = Field(default_factory=dict)


@router.get("")
def list_meetings(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    service: MeetingsService = Depends(get_meetings_service),
    _principal: Annotated[Principal, Depends(_require_read)] = ...,
) -> dict:
    return service.list_meetings(offset=offset, limit=limit)


@router.get("/{meeting_id}")
def get_meeting(
    meeting_id: str,
    service: MeetingsService = Depends(get_meetings_service),
    _principal: Annotated[Principal, Depends(_require_read)] = ...,
) -> dict:
    try:
        data = service.get_meeting(meeting_id)
    except MeetingCardError as exc:
        raise _invalid_card(exc) from exc
    if data is None:
        raise _not_found(meeting_id)
    return data


@router.get("/{meeting_id}/transcript")
def get_transcript(
    meeting_id: str,
    service: MeetingsService = Depends(get_meetings_service),
    _principal: Annotated[Principal, Depends(require_permission("transcripts.read"))] = ...,
) -> dict:
    try:
        card = service.get_meeting(meeting_id)
    except MeetingCardError as exc:
        raise _invalid_card(exc) from exc
    if card is None:
        raise _not_found(meeting_id)
    try:
        result = service.get_transcript(meeting_id)
    except ArtifactTooLargeError as exc:
        raise _too_large(exc) from exc
    if result is None:
        raise _not_found(meeting_id)
    return result


@router.get("/{meeting_id}/artifacts")
def list_artifacts(
    meeting_id: str,
    service: MeetingsService = Depends(get_meetings_service),
    _principal: Annotated[Principal, Depends(require_permission("artifacts.read"))] = ...,
) -> dict:
    try:
        artifacts = service.list_artifacts(meeting_id)
    except MeetingCardError as exc:
        raise _invalid_card(exc) from exc
    if artifacts is None:
        raise _not_found(meeting_id)
    return {"meeting_id": meeting_id, "artifacts": artifacts}


@router.get("/{meeting_id}/speakers")
def get_speakers(
    meeting_id: str,
    service: MeetingsService = Depends(get_meetings_service),
    _principal: Annotated[Principal, Depends(require_permission("transcripts.read"))] = ...,
) -> dict:
    try:
        result = service.get_speakers(meeting_id)
    except ArtifactTooLargeError as exc:
        raise _too_large(exc) from exc
    except MeetingCardError as exc:
        raise _invalid_card(exc) from exc
    if result is None:
        raise _not_found(meeting_id)
    return result


@router.put("/{meeting_id}/speakers/mapping")
def update_speaker_mapping(
    meeting_id: str,
    payload: SpeakerMappingRequest,
    service: MeetingsService = Depends(get_meetings_service),
    _principal: Annotated[Principal, Depends(require_action_permission("meetings.edit"))] = ...,
) -> dict:
    try:
        raw_mapping = {label: entry.model_dump() for label, entry in payload.mapping.items()}
        result = service.update_speaker_mapping(meeting_id, raw_mapping)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ArtifactTooLargeError as exc:
        raise _too_large(exc) from exc
    except MeetingCardError as exc:
        raise _invalid_card(exc) from exc
    if result is None:
        raise _not_found(meeting_id)
    return result


# Declared BEFORE /{meeting_id}/artifacts/{artifact_name} so "manifest" is
# never captured as an artifact name.
@router.get("/{meeting_id}/artifacts/manifest")
def get_artifact_manifest(
    meeting_id: str,
    service: MeetingsService = Depends(get_meetings_service),
    _principal: Annotated[Principal, Depends(require_permission("artifacts.read"))] = ...,
) -> dict:
    if not _safe_meeting_id(meeting_id):
        raise _not_found(meeting_id)
    meeting_dir = service.root / meeting_id
    card_path = meeting_dir / "meeting.json"
    if not card_path.exists():
        raise _not_found(meeting_id)
    try:
        card = json.loads(card_path.read_text(encoding="utf-8"))
        if not isinstance(card, dict):
            card = {}
    except Exception:  # noqa: BLE001 — unreadable card: manifest of defaults
        card = {}
    return build_artifact_manifest(meeting_id, meeting_dir, card)


@router.get("/{meeting_id}/transcript/segments")
def get_transcript_segments(
    meeting_id: str,
    service: MeetingsService = Depends(get_meetings_service),
    _principal: Annotated[Principal, Depends(require_permission("transcripts.read"))] = ...,
) -> dict:
    try:
        result = service.get_transcript_segments(meeting_id)
    except ArtifactTooLargeError as exc:
        raise _too_large(exc) from exc
    if result is None:
        raise _not_found(meeting_id)
    return result


@router.get("/{meeting_id}/media")
def list_media(
    meeting_id: str,
    service: MeetingsService = Depends(get_meetings_service),
    _principal: Annotated[Principal, Depends(_require_read)] = ...,
) -> dict:
    try:
        media = service.list_media(meeting_id)
    except MeetingCardError as exc:
        raise _invalid_card(exc) from exc
    if media is None:
        raise _not_found(meeting_id)
    return {"meeting_id": meeting_id, "media": media}


@router.get("/{meeting_id}/media/{media_id}")
def get_media(
    meeting_id: str,
    media_id: str,
    service: MeetingsService = Depends(get_meetings_service),
    _principal: Annotated[Principal, Depends(_require_read)] = ...,
) -> FileResponse:
    try:
        result = service.get_media_path(meeting_id, media_id)
    except MeetingCardError as exc:
        raise _invalid_card(exc) from exc
    if result is None:
        # 404 for both missing meeting and missing/unsupported media file.
        raise HTTPException(
            status_code=404,
            detail=f"Media not found: meeting={meeting_id!r} media_id={media_id!r}",
        )
    abs_path, mime_type = result
    return FileResponse(str(abs_path), media_type=mime_type)


@router.get("/{meeting_id}/artifacts/{artifact_name}")
def get_artifact_content(
    meeting_id: str,
    artifact_name: str,
    service: MeetingsService = Depends(get_meetings_service),
    _principal: Annotated[Principal, Depends(require_permission("artifacts.read"))] = ...,
) -> dict:
    try:
        card = service.get_meeting(meeting_id)
    except MeetingCardError as exc:
        raise _invalid_card(exc) from exc
    if card is None:
        raise _not_found(meeting_id)
    try:
        result = service.get_artifact_content(meeting_id, artifact_name)
    except ArtifactTooLargeError as exc:
        raise _too_large(exc) from exc
    if result is None:
        raise HTTPException(status_code=404, detail=f"Artifact not found: {artifact_name!r}")
    if result.get("error") == "binary_artifact":
        raise HTTPException(status_code=415, detail="Binary artifacts cannot be served as text")
    return result


class MeetingQARequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, max_length=MAX_QUERY_CHARS, description="Meeting-scoped query")
    top_k: int = Field(default=5, ge=1, le=20)


@router.post("/{meeting_id}/search")
def meeting_search(
    meeting_id: str,
    payload: MeetingQARequest,
    service: MeetingQAService = Depends(get_meeting_qa_service),
    _principal: Annotated[Principal, Depends(require_permission("search.use"))] = ...,
) -> dict:
    try:
        result = service.search(meeting_id, payload.query, top_k=payload.top_k)
    except MeetingCardError as exc:
        raise _invalid_card(exc) from exc
    if result is None:
        raise _not_found(meeting_id)
    return result


@router.post("/{meeting_id}/chat")
def meeting_chat(
    meeting_id: str,
    payload: MeetingQARequest,
    service: MeetingQAService = Depends(get_meeting_qa_service),
    _principal: Annotated[Principal, Depends(require_action_permission("chat.use"))] = ...,
) -> dict:
    try:
        result = service.chat(meeting_id, payload.query, top_k=payload.top_k)
    except MeetingCardError as exc:
        raise _invalid_card(exc) from exc
    if result is None:
        raise _not_found(meeting_id)
    return result
