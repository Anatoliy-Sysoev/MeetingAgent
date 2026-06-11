from __future__ import annotations

"""Provider-independent auth dependencies for the MeetingAgent API.

Resolution order:
  1. Bearer token present → validate as machine token → machine Principal (or 401, no fallback)
  2. Session cookie present → resolve via LocalAuthService → user Principal (or None)
  3. Neither → anonymous (None)

Invalid supplied credentials always raise 401 — they never silently downgrade to anonymous.
"""

import os
import secrets

from fastapi import Depends, HTTPException, Request

from asu_june_bot.auth.models import Principal
from asu_june_bot.auth.passwords import verify_csrf_token
from asu_june_bot.auth.permissions import MACHINE_PERMISSIONS
from asu_june_bot.auth.service import LocalAuthService

_BEARER_PREFIX = "bearer "
CSRF_HEADER = "X-CSRF-Token"


# ------------------------------------------------------------------
# Machine token (low-level, internal)
# ------------------------------------------------------------------

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


def _get_local_auth_service(request: Request) -> LocalAuthService:
    return request.app.state.asu_june_bot.local_auth_service


def _bearer_header(request: Request) -> str | None:
    """Return the Bearer token, None if no Authorization header at all.

    Any present-but-malformed Authorization (non-Bearer scheme, missing token)
    raises 401 — supplied credentials must never silently downgrade to
    anonymous/cookie access.
    """
    auth = request.headers.get("Authorization", "")
    if not auth:
        return None
    stripped = auth.strip()
    if stripped.lower().startswith(_BEARER_PREFIX):
        token = stripped[len(_BEARER_PREFIX):].strip()
        if not token:
            raise HTTPException(status_code=401, detail="Empty Bearer token")
        return token
    raise HTTPException(status_code=401, detail="Invalid Authorization header format")


def _resolve_machine_principal(token: str) -> Principal:
    """Build a limited machine Principal. Does not validate the token value — caller must."""
    return Principal(
        principal_type="machine",
        principal_id="machine",
        provider="machine",
        permissions=MACHINE_PERMISSIONS,
    )


# ------------------------------------------------------------------
# Provider-independent dependencies
# ------------------------------------------------------------------

def get_optional_principal(
    request: Request,
    service: LocalAuthService = Depends(_get_local_auth_service),
) -> Principal | None:
    """Resolve a Principal from Bearer token or session cookie; None if no credentials.

    If a Bearer token header is present but invalid → 401 (no silent fallback).
    """
    bearer = _bearer_header(request)
    if bearer is not None:
        configured = os.environ.get("MEETINGAGENT_API_TOKEN", "").strip()
        if not configured:
            raise HTTPException(status_code=500, detail="MEETINGAGENT_API_TOKEN not configured")
        if not secrets.compare_digest(bearer, configured):
            raise HTTPException(status_code=401, detail="Invalid token")
        return _resolve_machine_principal(bearer)

    token = request.cookies.get(service.cookie_name, "")
    if not token:
        return None
    auth = service.resolve_session(token)
    if auth is None:
        return None
    return auth.principal


def require_user(
    principal: Principal | None = Depends(get_optional_principal),
) -> Principal:
    if principal is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return principal


def require_permission(permission: str):
    """Dependency factory: require authenticated principal with given permission."""
    def _dep(principal: Principal = Depends(require_user)) -> Principal:
        if not principal.has_permission(permission):
            raise HTTPException(status_code=403, detail=f"Permission required: {permission}")
        return principal
    return _dep


def require_role(role: str):
    """Dependency factory: require authenticated user principal with given role."""
    def _dep(principal: Principal = Depends(require_user)) -> Principal:
        if principal.principal_type != "user" or not principal.has_role(role):
            raise HTTPException(status_code=403, detail=f"Role required: {role}")
        return principal
    return _dep


def _check_csrf(request: Request, service: LocalAuthService) -> None:
    """Verify CSRF token for cookie-authenticated requests.

    Machine Bearer requests are exempt. Cookie-authenticated write requests must
    supply a valid session-bound X-CSRF-Token header.
    """
    bearer = _bearer_header(request)
    if bearer is not None:
        return  # Machine bearer; exempt from CSRF
    token = request.cookies.get(service.cookie_name, "")
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    auth = service.resolve_session(token)
    if auth is None:
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    csrf_value = request.headers.get(CSRF_HEADER, "")
    if not csrf_value:
        raise HTTPException(status_code=403, detail="CSRF token required")
    if auth.session.csrf_token_hash is None:
        raise HTTPException(status_code=403, detail="Session has no CSRF token")
    if not verify_csrf_token(auth.session.csrf_token_hash, csrf_value):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")


def require_write_access(
    request: Request,
    service: LocalAuthService = Depends(_get_local_auth_service),
) -> Principal:
    """Authorization dependency for write/action routes.

    Accepts:
    - valid machine Bearer token → machine Principal
    - authenticated browser user Principal with a write permission

    Rejects:
    - viewer-only user Principal with 403
    - missing/invalid credentials with 401
    - cookie-authenticated requests without valid CSRF with 403
    """
    bearer = _bearer_header(request)
    if bearer is not None:
        configured = os.environ.get("MEETINGAGENT_API_TOKEN", "").strip()
        if not configured:
            raise HTTPException(status_code=500, detail="MEETINGAGENT_API_TOKEN not configured")
        if not secrets.compare_digest(bearer, configured):
            raise HTTPException(status_code=401, detail="Invalid token")
        return _resolve_machine_principal(bearer)

    # Cookie path — requires CSRF for state-changing requests
    _check_csrf(request, service)
    token = request.cookies.get(service.cookie_name, "")
    auth = service.resolve_session(token)
    if auth is None:
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    if not auth.principal.has_permission("meetings.upload"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return auth.principal
