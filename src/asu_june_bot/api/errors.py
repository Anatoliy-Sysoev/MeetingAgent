from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


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
            details=exc.errors(),
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
