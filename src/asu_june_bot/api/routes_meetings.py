from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from asu_june_bot.meetings.service import MeetingCardError, MeetingsService

router = APIRouter(prefix="/meetings", tags=["meetings"])


def get_meetings_service(request: Request) -> MeetingsService:
    state = request.app.state.asu_june_bot
    return getattr(state, "meetings_service", None) or MeetingsService()


def _not_found(meeting_id: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"Meeting not found: {meeting_id!r}")


def _invalid_card(exc: MeetingCardError) -> HTTPException:
    return HTTPException(status_code=422, detail=f"Invalid meeting card: {exc}")


# ------------------------------------------------------------------
# GET /meetings
# ------------------------------------------------------------------

@router.get("")
def list_meetings(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    service: MeetingsService = Depends(get_meetings_service),
) -> dict:
    return service.list_meetings(offset=offset, limit=limit)


# ------------------------------------------------------------------
# GET /meetings/{meeting_id}
# ------------------------------------------------------------------

@router.get("/{meeting_id}")
def get_meeting(
    meeting_id: str,
    service: MeetingsService = Depends(get_meetings_service),
) -> dict:
    try:
        data = service.get_meeting(meeting_id)
    except MeetingCardError as exc:
        raise _invalid_card(exc) from exc
    if data is None:
        raise _not_found(meeting_id)
    return data


# ------------------------------------------------------------------
# GET /meetings/{meeting_id}/transcript
# ------------------------------------------------------------------

@router.get("/{meeting_id}/transcript")
def get_transcript(
    meeting_id: str,
    service: MeetingsService = Depends(get_meetings_service),
) -> dict:
    try:
        card = service.get_meeting(meeting_id)
    except MeetingCardError as exc:
        raise _invalid_card(exc) from exc
    if card is None:
        raise _not_found(meeting_id)
    result = service.get_transcript(meeting_id)
    if result is None:
        raise _not_found(meeting_id)
    return result


# ------------------------------------------------------------------
# GET /meetings/{meeting_id}/artifacts
# ------------------------------------------------------------------

@router.get("/{meeting_id}/artifacts")
def list_artifacts(
    meeting_id: str,
    service: MeetingsService = Depends(get_meetings_service),
) -> dict:
    try:
        artifacts = service.list_artifacts(meeting_id)
    except MeetingCardError as exc:
        raise _invalid_card(exc) from exc
    if artifacts is None:
        raise _not_found(meeting_id)
    return {"meeting_id": meeting_id, "artifacts": artifacts}


# ------------------------------------------------------------------
# GET /meetings/{meeting_id}/artifacts/{artifact_name}
# ------------------------------------------------------------------

@router.get("/{meeting_id}/artifacts/{artifact_name}")
def get_artifact_content(
    meeting_id: str,
    artifact_name: str,
    service: MeetingsService = Depends(get_meetings_service),
) -> dict:
    try:
        card = service.get_meeting(meeting_id)
    except MeetingCardError as exc:
        raise _invalid_card(exc) from exc
    if card is None:
        raise _not_found(meeting_id)
    result = service.get_artifact_content(meeting_id, artifact_name)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Artifact not found: {artifact_name!r}")
    if result.get("error") == "binary_artifact":
        raise HTTPException(status_code=415, detail="Binary artifacts cannot be served as text")
    return result
