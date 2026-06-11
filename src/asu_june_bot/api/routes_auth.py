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

SESSION_COOKIE_NAME = "ma_session"

_GENERIC_LOGIN_ERROR = "Invalid email or password"


class LoginRequest(BaseModel):
    email: str
    password: str


def _cookie_secure(request: Request) -> bool:
    if request.url.scheme == "https":
        return True
    forwarded = request.headers.get("x-forwarded-proto", "")
    return forwarded.lower() == "https"


def _me_payload(auth: AuthenticatedSession) -> dict:
    return {
        "user_id": auth.user.user_id,
        "email": auth.user.email,
        "display_name": auth.user.display_name,
        "roles": sorted(auth.roles),
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
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=_cookie_secure(request),
        max_age=service.session_ttl_seconds,
        path="/",
    )
    return _me_payload(auth)


@router.get("/me")
async def auth_me(
    request: Request,
    service: LocalAuthService = Depends(get_local_auth_service),
) -> dict:
    token = request.cookies.get(SESSION_COOKIE_NAME, "")
    auth = service.resolve_session(token)
    if auth is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return _me_payload(auth)


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    service: LocalAuthService = Depends(get_local_auth_service),
) -> Response:
    token = request.cookies.get(SESSION_COOKIE_NAME, "")
    service.logout(token)
    response = Response(status_code=204)
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        httponly=True,
        samesite="lax",
        secure=_cookie_secure(request),
        path="/",
    )
    return response
