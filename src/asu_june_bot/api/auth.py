from __future__ import annotations

import os
import secrets

from fastapi import HTTPException, Request


def require_machine_token(request: Request) -> str:
    """Validate Bearer token against MEETINGAGENT_API_TOKEN.

    500 if env var is not configured (fail-secure).
    401 if header is missing or token is wrong.

    Internal implementation. Routes should depend on require_write_access().
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

    if not secrets.compare_digest(parts[1], configured):
        raise HTTPException(status_code=401, detail="Invalid token")

    return parts[1]


def require_write_access(request: Request) -> str:
    """Authorization dependency for write/action routes.

    This is the stable contract routes depend on. For the MVP it delegates to a
    machine token; future tasks (#39/#40) can swap the backing mechanism here
    without touching routes.
    """
    return require_machine_token(request)
