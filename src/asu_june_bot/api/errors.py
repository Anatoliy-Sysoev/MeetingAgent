from __future__ import annotations

import math
import re
from itertools import islice

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

_SENSITIVE_FIELD_NAMES = frozenset({"password", "token", "secret", "authorization", "api_key", "csrf"})
_UNSAFE_CTX_KEYS = frozenset({
    "actual",
    "cause",
    "error",
    "exception",
    "given",
    "input",
    "pattern",
    "traceback",
    "value",
})
_MAX_CTX_DEPTH = 5
_MAX_CTX_ITEMS = 32
_MAX_PUBLIC_TEXT_CHARS = 240
_DROP = object()


def _is_sensitive_loc(loc: tuple | list | None) -> bool:
    if not loc:
        return False
    for part in loc:
        if not isinstance(part, str):
            continue
        normalized = part.lower().replace("-", "_")
        if any(marker in normalized for marker in _SENSITIVE_FIELD_NAMES):
            return True
    return False


def _bounded_text(value: object, fallback: str) -> str:
    if not isinstance(value, str):
        return fallback
    return value[:_MAX_PUBLIC_TEXT_CHARS]


def _sanitize_loc(loc: object) -> tuple[str | int, ...]:
    if not isinstance(loc, (tuple, list)):
        return ()
    result: list[str | int] = []
    for part in loc[:16]:
        if isinstance(part, bool):
            continue
        if isinstance(part, int):
            result.append(part)
        elif isinstance(part, str):
            result.append(part[:120])
    return tuple(result)


def _ctx_key_is_unsafe(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    if normalized in _UNSAFE_CTX_KEYS:
        return True
    if any(marker in normalized for marker in _SENSITIVE_FIELD_NAMES):
        return True
    location_keys = ("path", "file", "filename", "directory", "url", "uri")
    return (
        normalized in location_keys
        or normalized.startswith(tuple(f"{marker}_" for marker in location_keys))
        or normalized.endswith(tuple(f"_{marker}" for marker in location_keys))
    )


def _looks_like_private_location(value: str) -> bool:
    normalized = value.strip().replace("\\", "/")
    lowered = normalized.lower()
    if normalized.startswith(("/", "../", "//")):
        return True
    if "file:" in lowered or "://" in normalized or " /" in normalized or " ../" in normalized:
        return True
    return re.search(r"(?:^|[^A-Za-z])[A-Za-z]:/", normalized) is not None


def _sanitize_ctx_value(
    value: object,
    *,
    depth: int,
    seen: set[int],
) -> object:
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else _DROP
    if isinstance(value, str):
        if _looks_like_private_location(value):
            return _DROP
        return value[:_MAX_PUBLIC_TEXT_CHARS]
    if isinstance(value, BaseException) or depth >= _MAX_CTX_DEPTH:
        return _DROP

    identity = id(value)
    if identity in seen:
        return _DROP
    if isinstance(value, dict):
        seen.add(identity)
        try:
            result: dict[str, object] = {}
            for key, item in islice(value.items(), _MAX_CTX_ITEMS):
                if not isinstance(key, str) or _ctx_key_is_unsafe(key):
                    continue
                sanitized = _sanitize_ctx_value(
                    item,
                    depth=depth + 1,
                    seen=seen,
                )
                if sanitized is not _DROP:
                    result[key[:80]] = sanitized
            return result if result else _DROP
        finally:
            seen.remove(identity)
    if isinstance(value, (list, tuple)):
        seen.add(identity)
        try:
            result = []
            for item in value[:_MAX_CTX_ITEMS]:
                sanitized = _sanitize_ctx_value(
                    item,
                    depth=depth + 1,
                    seen=seen,
                )
                if sanitized is not _DROP:
                    result.append(sanitized)
            return result if result else _DROP
        finally:
            seen.remove(identity)
    return _DROP


def _ctx_requires_generic_message(
    value: object,
    *,
    depth: int = 0,
    seen: set[int] | None = None,
) -> bool:
    if isinstance(value, BaseException):
        return True
    if isinstance(value, str):
        return _looks_like_private_location(value)
    if value is not None and not isinstance(
        value,
        (bool, int, float, dict, list, tuple, set, frozenset),
    ):
        return True
    if depth >= _MAX_CTX_DEPTH:
        return isinstance(value, (dict, list, tuple, set, frozenset)) and bool(value)
    if not isinstance(
        value,
        (dict, list, tuple, set, frozenset),
    ):
        return False
    seen = seen if seen is not None else set()
    identity = id(value)
    if identity in seen:
        return False
    seen.add(identity)
    try:
        if isinstance(value, dict):
            if len(value) > _MAX_CTX_ITEMS:
                return True
            for key, item in islice(value.items(), _MAX_CTX_ITEMS):
                if not isinstance(key, str):
                    return True
                normalized = key.lower().replace("-", "_")
                input_derived = normalized in {
                    "actual",
                    "cause",
                    "error",
                    "exception",
                    "given",
                    "input",
                    "traceback",
                    "value",
                }
                if input_derived or (
                    _ctx_key_is_unsafe(key) and normalized != "pattern"
                ):
                    return True
                if _ctx_requires_generic_message(
                    item,
                    depth=depth + 1,
                    seen=seen,
                ):
                    return True
            return False
        if len(value) > _MAX_CTX_ITEMS:
            return True
        return any(
            _ctx_requires_generic_message(item, depth=depth + 1, seen=seen)
            for item in islice(value, _MAX_CTX_ITEMS)
        )
    finally:
        seen.remove(identity)


def _sanitize_ctx(ctx: object) -> dict | None:
    if not isinstance(ctx, dict):
        return None
    sanitized = _sanitize_ctx_value(ctx, depth=0, seen=set())
    return sanitized if isinstance(sanitized, dict) else None


def _sanitize_validation_errors(errors: list[dict]) -> list[dict]:
    result = []
    for err in errors:
        raw_ctx = err.get("ctx")
        safe: dict = {
            "loc": _sanitize_loc(err.get("loc")),
            "type": _bounded_text(err.get("type"), "validation_error"),
        }
        if _is_sensitive_loc(err.get("loc")):
            safe["msg"] = "Field value redacted for security"
        elif _ctx_requires_generic_message(raw_ctx):
            safe["msg"] = "Value does not satisfy validation rules"
        else:
            message = _bounded_text(err.get("msg"), "Invalid field value")
            safe["msg"] = (
                "Value does not satisfy validation rules"
                if _looks_like_private_location(message)
                else message
            )
        ctx = _sanitize_ctx(raw_ctx)
        if ctx:
            safe["ctx"] = ctx
        result.append(safe)
    return result


class ApiError(Exception):
    def __init__(self, message: str, *, status_code: int = 500, error_code: str = "api_error") -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code


class IndexNotReadyError(ApiError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=503, error_code="index_not_ready")


class SearchApiError(ApiError):
    pass


def request_id_from(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def error_payload(request: Request, *, status: str, error_code: str, message: str, details=None) -> dict:
    payload = {
        "status": status,
        "error_code": error_code,
        "error": message,
        "request_id": request_id_from(request),
    }
    if details is not None:
        payload["details"] = details
    return payload


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload(request, status="error", error_code=exc.error_code, message=exc.message),
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=error_payload(
            request,
            status="error",
            error_code="validation_error",
            message="Некорректный запрос к API",
            details=_sanitize_validation_errors(exc.errors()),
        ),
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content=error_payload(
            request,
            status="error",
            error_code="internal_error",
            message="Внутренняя ошибка API. Передайте request_id для диагностики.",
        ),
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
