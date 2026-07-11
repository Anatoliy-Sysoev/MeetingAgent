from __future__ import annotations

import datetime
import hashlib
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import jsonschema
from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from asu_june_bot.api.auth import require_write_access
from asu_june_bot.auth.models import Principal
from asu_june_bot.meetings.service import (
    MAX_MEETING_TITLE_CHARS,
    MAX_ORIGINAL_FILENAME_CHARS,
    SUPPORTED_MEDIA_EXTENSIONS,
    MeetingsService,
    _slugify,
)
from asu_june_bot.meetings.ingest_lock import IngestLockTimeoutError

router = APIRouter(prefix="/meetings", tags=["ingest"])

_CHUNK_SIZE = 256 * 1024  # 256 KB
_UNSAFE_FILENAME_CHARS = frozenset('<>:"|?*\x00')

_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "configs" / "schemas" / "meeting.schema.json"
)


def _get_meetings_service(request: Request) -> MeetingsService:
    state = request.app.state.asu_june_bot
    svc = getattr(state, "meetings_service", None)
    return svc if svc is not None else MeetingsService()


class UploadTooLargeError(ValueError):
    pass


class UploadBufferError(OSError):
    pass


@dataclass(frozen=True, slots=True)
class BufferedUpload:
    path: Path
    size_bytes: int
    sha256: str


def _error(status_code: int, code: str, message: str, **fields: object) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"error": code, "message": message, **fields},
    )


def _safe_upload_filename(raw_name: str | None) -> str:
    normalized = str(raw_name or "").replace("\\", "/")
    basename = normalized.rsplit("/", 1)[-1].strip()
    if (
        not basename
        or basename in {".", ".."}
        or len(basename) > MAX_ORIGINAL_FILENAME_CHARS
        or any(char in _UNSAFE_FILENAME_CHARS for char in basename)
        or any(ord(char) < 32 for char in basename)
    ):
        raise ValueError("invalid upload filename")
    return basename


def _meeting_title(title: str | None, filename: str) -> str:
    candidate = title if title is not None else Path(filename).stem
    normalized = " ".join(str(candidate).split())
    if not normalized or len(normalized) > MAX_MEETING_TITLE_CHARS:
        raise ValueError("invalid meeting title")
    return normalized


def _unlink_temp(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _buffer_upload(file: UploadFile, *, suffix: str, max_bytes: int) -> BufferedUpload:
    digest = hashlib.sha256()
    total_bytes = 0
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            delete=False,
            prefix="meetingagent-ingest-",
            suffix=suffix,
        ) as tmp_fh:
            tmp_path = Path(tmp_fh.name)
            while True:
                try:
                    chunk = file.file.read(_CHUNK_SIZE)
                except Exception as exc:
                    raise UploadBufferError("upload stream read failed") from exc
                if not chunk:
                    break
                if not isinstance(chunk, bytes):
                    raise UploadBufferError("upload stream returned non-bytes")
                if total_bytes + len(chunk) > max_bytes:
                    raise UploadTooLargeError("upload exceeds configured limit")
                total_bytes += len(chunk)
                digest.update(chunk)
                tmp_fh.write(chunk)
        return BufferedUpload(
            path=tmp_path,
            size_bytes=total_bytes,
            sha256=digest.hexdigest(),
        )
    except UploadTooLargeError:
        _unlink_temp(tmp_path)
        raise
    except Exception as exc:
        _unlink_temp(tmp_path)
        if isinstance(exc, UploadBufferError):
            raise
        raise UploadBufferError("upload buffering failed") from exc
    except BaseException:
        _unlink_temp(tmp_path)
        raise


@router.post("/ingest", status_code=201)
def ingest_meeting(
    _principal: Annotated[Principal, Depends(require_write_access)],
    file: UploadFile,
    title: Annotated[str | None, Form(max_length=MAX_MEETING_TITLE_CHARS)] = None,
    date: Annotated[str | None, Form()] = None,
    service: MeetingsService = Depends(_get_meetings_service),
) -> JSONResponse:
    """Upload a media file and create a meeting card with sha256 dedup."""
    try:
        safe_filename = _safe_upload_filename(file.filename)
        effective_title = _meeting_title(title, safe_filename)
    except ValueError as exc:
        raise _error(422, "invalid_upload_metadata", "Upload metadata is invalid") from exc

    suffix = Path(safe_filename).suffix.lower()
    if suffix not in SUPPORTED_MEDIA_EXTENSIONS:
        raise _error(
            422,
            "unsupported_media_type",
            "Uploaded media type is not supported",
            supported=sorted(SUPPORTED_MEDIA_EXTENSIONS),
        )

    if date is not None:
        try:
            meeting_date = datetime.date.fromisoformat(date).isoformat()
        except ValueError as exc:
            raise _error(422, "invalid_meeting_date", "Meeting date must be YYYY-MM-DD") from exc
    else:
        meeting_date = datetime.date.today().isoformat()

    if file.size is not None and file.size > service.max_upload_bytes:
        raise _error(
            413,
            "upload_too_large",
            "Uploaded file exceeds the configured size limit",
            max_bytes=service.max_upload_bytes,
        )

    buffered: BufferedUpload | None = None
    try:
        buffered = _buffer_upload(
            file,
            suffix=suffix,
            max_bytes=service.max_upload_bytes,
        )
        if buffered.size_bytes == 0:
            raise _error(422, "upload_empty", "Uploaded file is empty")

        slug = _slugify(effective_title) or buffered.sha256[:8]
        try:
            result = service.create_deduplicated_meeting(
                title=effective_title,
                meeting_date=meeting_date,
                slug=slug,
                source_temp_path=buffered.path,
                original_filename=safe_filename,
                sha256=buffered.sha256,
                schema_path=_SCHEMA_PATH,
            )
        except IngestLockTimeoutError as exc:
            raise _error(503, "ingest_busy", "Another ingest transaction is still active") from exc
        except jsonschema.ValidationError as exc:
            raise _error(
                422,
                "meeting_card_validation_failed",
                "Meeting metadata did not pass validation",
            ) from exc
        except ValueError as exc:
            raise _error(422, "invalid_meeting_metadata", "Meeting metadata is invalid") from exc
        except (OSError, RuntimeError) as exc:
            raise _error(500, "meeting_create_failed", "Meeting could not be created") from exc

        if result.duplicate:
            return JSONResponse(
                status_code=409,
                content={
                    "duplicate": True,
                    "existing_meeting_id": result.meeting_id,
                    "sha256": buffered.sha256,
                },
            )
        card = result.card
        assert card is not None

        return JSONResponse(
            status_code=201,
            content={
                "meeting_id": result.meeting_id,
                "title": card["title"],
                "date": card["date"],
                "media_id": "0",
                "media_url": f"/meetings/{result.meeting_id}/media/0",
                "sha256": buffered.sha256,
            },
        )
    except UploadTooLargeError as exc:
        raise _error(
            413,
            "upload_too_large",
            "Uploaded file exceeds the configured size limit",
            max_bytes=service.max_upload_bytes,
        ) from exc
    except UploadBufferError as exc:
        raise _error(500, "upload_buffer_failed", "Uploaded file could not be buffered") from exc
    finally:
        _unlink_temp(buffered.path if buffered is not None else None)
