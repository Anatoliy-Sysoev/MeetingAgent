from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from asu_june_bot.api.dependencies import get_local_auth_service
from asu_june_bot.auth.service import (
    AuthenticatedSession,
    InvalidCredentialsError,
    LocalAuthService,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_GENERIC_LOGIN_ERROR = "Invalid email or password"


class LoginRequest(BaseModel):
    email: str
    password: str


def _resolve_secure(service: LocalAuthService, request: Request) -> bool:
    mode = service.cookie_secure
    if mode == "true":
        return True
    if mode == "false":
        return False
    # auto: detect from incoming scheme / reverse-proxy header
    if request.url.scheme == "https":
        return True
    return request.headers.get("x-forwarded-proto", "").lower() == "https"


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
    response.set_cookie(
        key=service.cookie_name,
        value=token,
        httponly=True,
        samesite="lax",
        secure=_resolve_secure(service, request),
        max_age=service.session_ttl_seconds,
        path="/",
    )
    return {**_me_payload(auth), "expires_at": auth.session.expires_at}


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
    service.logout(token)
    response = Response(status_code=204)
    response.delete_cookie(
        key=service.cookie_name,
        httponly=True,
        samesite="lax",
        secure=_resolve_secure(service, request),
        path="/",
    )
    return response
