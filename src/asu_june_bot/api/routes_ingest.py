from __future__ import annotations

import datetime
import hashlib
import re
import tempfile
from pathlib import Path
from typing import Annotated

import jsonschema
from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from asu_june_bot.api.auth import require_token
from asu_june_bot.meetings.service import (
    SUPPORTED_MEDIA_EXTENSIONS,
    MeetingsService,
    _slugify,
)

router = APIRouter(prefix="/meetings", tags=["ingest"])

_CHUNK_SIZE = 256 * 1024  # 256 KB

_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "configs" / "schemas" / "meeting.schema.json"
)


def _get_meetings_service(request: Request) -> MeetingsService:
    state = request.app.state.asu_june_bot
    svc = getattr(state, "meetings_service", None)
    return svc if svc is not None else MeetingsService()


@router.post("/ingest", status_code=201)
def ingest_meeting(
    _token: Annotated[str, Depends(require_token)],
    file: UploadFile,
    title: Annotated[str | None, Form()] = None,
    date: Annotated[str | None, Form()] = None,
    service: MeetingsService = Depends(_get_meetings_service),
) -> JSONResponse:
    """Upload a media file and create a meeting card with sha256 dedup."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED_MEDIA_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_MEDIA_EXTENSIONS))
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type {suffix!r}. Supported: {supported}",
        )

    if date is not None:
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
            raise HTTPException(status_code=422, detail="date must be YYYY-MM-DD")
        meeting_date = date
    else:
        meeting_date = datetime.date.today().isoformat()

    # Stream upload to temp file, compute sha256 incrementally
    digest = hashlib.sha256()
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_fh:
            tmp_path = Path(tmp_fh.name)
            while True:
                chunk = file.file.read(_CHUNK_SIZE)
                if not chunk:
                    break
                digest.update(chunk)
                tmp_fh.write(chunk)
    except Exception as exc:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Failed to buffer upload: {exc}") from exc

    sha256_hex = digest.hexdigest()

    try:
        existing_id = service.find_by_sha256(sha256_hex)
        if existing_id:
            return JSONResponse(
                status_code=409,
                content={
                    "duplicate": True,
                    "existing_meeting_id": existing_id,
                    "sha256": sha256_hex,
                },
            )

        raw_name = title or Path(file.filename or "").stem or sha256_hex[:8]
        slug = _slugify(raw_name) or sha256_hex[:8]
        effective_title = title or Path(file.filename or "").stem or sha256_hex[:8]

        try:
            meeting_id = service.unique_meeting_id(meeting_date, slug)
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        try:
            card = service.create_meeting(
                meeting_id=meeting_id,
                title=effective_title,
                meeting_date=meeting_date,
                source_temp_path=tmp_path,
                original_filename=file.filename or f"upload{suffix}",
                sha256=sha256_hex,
                schema_path=_SCHEMA_PATH,
            )
        except jsonschema.ValidationError as exc:
            raise HTTPException(status_code=422, detail=f"meeting.json validation failed: {exc.message}") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        source_path = card["source"]["media_files"][0]["path"]
        return JSONResponse(
            status_code=201,
            content={
                "meeting_id": meeting_id,
                "title": card["title"],
                "date": card["date"],
                "source_path": source_path,
                "sha256": sha256_hex,
            },
        )
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
