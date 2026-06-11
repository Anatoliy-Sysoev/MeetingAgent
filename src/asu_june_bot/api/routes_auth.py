from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from pydantic import BaseModel

from asu_june_bot.api.auth import CSRF_HEADER
from asu_june_bot.api.dependencies import get_local_auth_service
from asu_june_bot.auth.passwords import verify_csrf_token
from asu_june_bot.auth.service import (
    AuthenticatedSession,
    InvalidCredentialsError,
    LocalAuthService,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_GENERIC_LOGIN_ERROR = "Invalid email or password"
_CSRF_COOKIE_SUFFIX = "_csrf"


class LoginRequest(BaseModel):
    email: str
    password: str


def _resolve_secure(service: LocalAuthService, request: Request) -> bool:
    mode = service.cookie_secure
    if mode == "true":
        return True
    if mode == "false":
        return False
    if request.url.scheme == "https":
        return True
    return request.headers.get("x-forwarded-proto", "").lower() == "https"


def _csrf_cookie_name(service: LocalAuthService) -> str:
    return service.cookie_name + _CSRF_COOKIE_SUFFIX


def _me_payload(auth: AuthenticatedSession) -> dict:
    return {
        "user_id": auth.user.user_id,
        "email": auth.user.email,
        "display_name": auth.user.display_name,
        "roles": sorted(auth.principal.roles),
        "permissions": sorted(auth.principal.permissions),
        "provider": "local",
    }


@router.post("/local/login")
async def local_login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    service: LocalAuthService = Depends(get_local_auth_service),
) -> dict:
    try:
        token, auth = service.login(payload.email, payload.password)
    except InvalidCredentialsError:
        raise HTTPException(status_code=401, detail=_GENERIC_LOGIN_ERROR)
    secure = _resolve_secure(service, request)
    # HttpOnly session cookie — JS cannot read this.
    response.set_cookie(
        key=service.cookie_name,
        value=token,
        httponly=True,
        samesite="lax",
        secure=secure,
        max_age=service.session_ttl_seconds,
        path="/",
    )
    # Non-HttpOnly CSRF cookie — JS must read this and send as X-CSRF-Token.
    response.set_cookie(
        key=_csrf_cookie_name(service),
        value=auth.csrf_token,
        httponly=False,
        samesite="lax",
        secure=secure,
        max_age=service.session_ttl_seconds,
        path="/",
    )
    return {
        **_me_payload(auth),
        "expires_at": auth.session.expires_at,
        "csrf_token": auth.csrf_token,
    }


@router.get("/me")
async def auth_me(
    request: Request,
    service: LocalAuthService = Depends(get_local_auth_service),
) -> dict:
    token = request.cookies.get(service.cookie_name, "")
    auth = service.resolve_session(token)
    if auth is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return _me_payload(auth)


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    service: LocalAuthService = Depends(get_local_auth_service),
) -> Response:
    token = request.cookies.get(service.cookie_name, "")
    auth = service.resolve_session(token) if token else None
    if auth is not None:
        # State-changing cookie request on a live session — require session-bound CSRF.
        csrf_value = request.headers.get(CSRF_HEADER, "")
        if not csrf_value:
            raise HTTPException(status_code=403, detail="CSRF token required")
        if auth.session.csrf_token_hash is None or not verify_csrf_token(
            auth.session.csrf_token_hash, csrf_value
        ):
            raise HTTPException(status_code=403, detail="Invalid CSRF token")
    service.logout(token)
    response = Response(status_code=204)
    secure = _resolve_secure(service, request)
    response.delete_cookie(
        key=service.cookie_name,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
    )
    response.delete_cookie(
        key=_csrf_cookie_name(service),
        httponly=False,
        samesite="lax",
        secure=secure,
        path="/",
    )
    return response
