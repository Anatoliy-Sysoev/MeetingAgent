from __future__ import annotations

import os

from fastapi import HTTPException, Request


def require_token(request: Request) -> str:
    """FastAPI dependency: validate Bearer token against MEETINGAGENT_API_TOKEN.

    500 if env var is not configured (fail-secure).
    401 if header is missing or token is wrong.
    """
    configured = os.environ.get("MEETINGAGENT_API_TOKEN", "").strip()
    if not configured:
        raise HTTPException(status_code=500, detail="MEETINGAGENT_API_TOKEN not configured")

    auth = request.headers.get("Authorization", "")
    if not auth:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    parts = auth.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid Authorization header format")

    if parts[1] != configured:
        raise HTTPException(status_code=401, detail="Invalid token")

    return parts[1]
