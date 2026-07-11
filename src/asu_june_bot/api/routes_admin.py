from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from asu_june_bot.api.auth import require_admin_action_permission, require_admin_user_permission
from asu_june_bot.auth.deployment_safety import _deployment_mode, validate_deployment_safety
from asu_june_bot.api.bootstrap_policy import (
    BOOTSTRAP_TOKEN_HEADER,
    BootstrapPolicy,
    is_local_request,
)
from asu_june_bot.api.host_policy import is_local_host_header
from asu_june_bot.auth.models import Principal
from asu_june_bot.auth.service import (
    AdminService,
    AdminUserNotFoundError,
    BootstrapConflictError,
    DuplicateUserError,
    InvalidRolesError,
    LastAdminError,
)

router = APIRouter(prefix="/admin", tags=["admin"])

_require_admin_read = require_admin_user_permission("users.manage")
_require_admin_write = require_admin_action_permission("users.manage")


def _get_admin_service(request: Request) -> AdminService:
    return request.app.state.asu_june_bot.admin_service


# ------------------------------------------------------------------
# Request / response schemas
# ------------------------------------------------------------------

class BootstrapRequest(BaseModel):
    email: str = Field(..., min_length=1, max_length=320)
    password: str = Field(..., min_length=8, max_length=1024)
    display_name: str | None = Field(None, max_length=200)


class CreateUserRequest(BaseModel):
    email: str = Field(..., min_length=1, max_length=320)
    password: str = Field(..., min_length=8, max_length=1024)
    display_name: str | None = Field(None, max_length=200)
    roles: list[str] = Field(default_factory=list)


class UpdateUserRequest(BaseModel):
    display_name: str | None = None
    roles: list[str] | None = None


# ------------------------------------------------------------------
# Bootstrap (no auth — first-user path)
# ------------------------------------------------------------------

def _enforce_bootstrap_policy(request: Request, policy: BootstrapPolicy) -> None:
    """Reject non-local bootstrap requests that lack operator authorisation.

    The local bypass (loopback peer → no secret required) applies only when
    there are no forwarded proxy headers.  If X-Forwarded-For or Forwarded is
    present the direct peer is a reverse proxy, not the real client, so the
    local bypass is suppressed and the normal policy is enforced.

    Forwarded headers are intentionally NOT used to identify the real client
    IP — they are only examined to detect proxy presence (X-Forwarded-For,
    Forwarded, X-Real-IP).
    """
    peer_host = request.client.host if request.client else None
    has_forwarded = bool(
        request.headers.get("x-forwarded-for")
        or request.headers.get("forwarded")
        or request.headers.get("x-real-ip")
    )
    host_header = request.headers.get("host", "")
    if is_local_request(peer_host) and is_local_host_header(host_header) and not has_forwarded:
        return
    if not policy.allow_remote:
        raise HTTPException(
            status_code=403,
            detail="Bootstrap is not available from remote addresses",
        )
    provided = request.headers.get(BOOTSTRAP_TOKEN_HEADER, "")
    if not policy.verify_secret(provided):
        raise HTTPException(
            status_code=403,
            detail="Invalid or missing bootstrap token",
        )


@router.post("/bootstrap", status_code=201)
def bootstrap_admin(
    payload: BootstrapRequest,
    request: Request,
) -> dict:
    """Create the first admin user. Returns 409 if any user already exists."""
    policy: BootstrapPolicy = request.app.state.asu_june_bot.bootstrap_policy
    _enforce_bootstrap_policy(request, policy)
    admin_service: AdminService = _get_admin_service(request)
    try:
        user = admin_service.bootstrap_admin(
            payload.email,
            payload.password,
            payload.display_name,
        )
    except BootstrapConflictError:
        raise HTTPException(status_code=409, detail="Bootstrap rejected: users already exist")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return user


# ------------------------------------------------------------------
# Admin user management (require users.manage — admin browser session)
# ------------------------------------------------------------------

@router.get("/users")
def list_users(
    request: Request,
    _principal: Annotated[Principal, Depends(_require_admin_read)],
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
) -> dict:
    admin_service: AdminService = _get_admin_service(request)
    users = admin_service.list_users(offset=offset, limit=limit)
    return {"users": users, "total": len(users), "offset": offset, "limit": limit}


@router.get("/users/{user_id}")
def get_user(
    user_id: str,
    request: Request,
    _principal: Annotated[Principal, Depends(_require_admin_read)],
) -> dict:
    admin_service: AdminService = _get_admin_service(request)
    user = admin_service.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post("/users", status_code=201)
def create_user(
    payload: CreateUserRequest,
    request: Request,
    principal: Annotated[Principal, Depends(_require_admin_write)],
) -> dict:
    admin_service: AdminService = _get_admin_service(request)
    try:
        user = admin_service.create_user(
            email=payload.email,
            password=payload.password,
            display_name=payload.display_name,
            roles=payload.roles,
            actor_id=principal.principal_id,
        )
    except InvalidRolesError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except DuplicateUserError:
        raise HTTPException(status_code=409, detail="Email already registered")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return user


@router.patch("/users/{user_id}")
def update_user(
    user_id: str,
    payload: UpdateUserRequest,
    request: Request,
    principal: Annotated[Principal, Depends(_require_admin_write)],
) -> dict:
    admin_service: AdminService = _get_admin_service(request)
    kw: dict = {}
    if "display_name" in payload.model_fields_set:
        kw["display_name"] = payload.display_name
    if "roles" in payload.model_fields_set:
        if payload.roles is None:
            raise HTTPException(status_code=422, detail="roles cannot be null")
        kw["roles"] = payload.roles
    try:
        user = admin_service.update_user(user_id, principal.principal_id, **kw)
    except AdminUserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found")
    except InvalidRolesError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except LastAdminError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return user


@router.post("/users/{user_id}/disable")
def disable_user(
    user_id: str,
    request: Request,
    principal: Annotated[Principal, Depends(_require_admin_write)],
) -> dict:
    admin_service: AdminService = _get_admin_service(request)
    try:
        user = admin_service.disable_user(user_id, principal.principal_id)
    except AdminUserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found")
    except LastAdminError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return user


@router.get("/security/status")
def security_status(
    request: Request,
    _principal: Annotated[Principal, Depends(_require_admin_read)],
) -> dict:
    """Return deployment mode and redacted safety findings.

    Admin-only. Response never includes raw secrets, token values, token hashes,
    session IDs, bootstrap secrets, or private filesystem paths.
    """
    config = request.app.state.asu_june_bot.config
    findings = validate_deployment_safety(config, os.environ)
    mode = _deployment_mode(config, os.environ)
    trusted_cidrs: list[str] = getattr(
        request.app.state.asu_june_bot, "trusted_proxy_cidrs", []
    ) or []
    return {
        "deployment_mode": mode,
        "findings": [
            {
                "code": f.code,
                "severity": f.severity,
                "message": f.message,
                "setting": f.setting,
            }
            for f in findings
        ],
        "error_count": sum(1 for f in findings if f.severity == "error"),
        "warning_count": sum(1 for f in findings if f.severity == "warning"),
        "trusted_proxy_policy": {
            "configured": len(trusted_cidrs) > 0,
            "count": len(trusted_cidrs),
        },
    }


@router.get("/diagnostics/meetings/{meeting_id}")
def meeting_card_diagnostics(
    meeting_id: str,
    request: Request,
    _principal: Annotated[Principal, Depends(_require_admin_read)],
) -> dict:
    """Return raw meeting-card/storage diagnostics to an admin browser user."""
    service = request.app.state.asu_june_bot.meetings_service
    result = service.get_meeting_diagnostics(meeting_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return result


@router.post("/users/{user_id}/enable")
def enable_user(
    user_id: str,
    request: Request,
    principal: Annotated[Principal, Depends(_require_admin_write)],
) -> dict:
    admin_service: AdminService = _get_admin_service(request)
    try:
        user = admin_service.enable_user(user_id, principal.principal_id)
    except AdminUserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found")
    return user
