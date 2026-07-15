from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response


REQUEST_ID_HEADER = "X-Request-Id"
ELAPSED_HEADER = "X-Elapsed-Ms"
CONTENT_SECURITY_POLICY = "; ".join(
    (
        "default-src 'none'",
        "base-uri 'none'",
        "frame-ancestors 'none'",
        "form-action 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "connect-src 'self'",
        "img-src 'self' data:",
        "media-src 'self' blob:",
        "font-src 'self'",
        "object-src 'none'",
    )
)


def _is_product_ui_path(path: str) -> bool:
    return path in {"/", "/ui", "/MeetingAgent", "/MeetingAgent/new", "/MeetingAgent/processing", "/admin"} or (
        path.startswith("/meetings/") and path.endswith("/workspace")
    )


async def request_context_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
    request.state.request_id = request_id
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000
    response.headers[REQUEST_ID_HEADER] = request_id
    response.headers[ELAPSED_HEADER] = f"{elapsed_ms:.3f}"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if _is_product_ui_path(request.url.path):
        response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
    if request.url.path.startswith(
        ("/assets/v1/", "/assets/v2/", "/assets/v3/", "/assets/v4/")
    ):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response
