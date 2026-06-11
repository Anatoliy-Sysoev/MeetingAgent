from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.api.app import create_app  # noqa: E402
from asu_june_bot.auth.passwords import hash_password  # noqa: E402
from asu_june_bot.auth.repository import AuthRepository  # noqa: E402
from asu_june_bot.auth.service import LocalAuthService  # noqa: E402
from asu_june_bot.auth.throttle import LoginThrottle  # noqa: E402

PASSWORD = "correct horse battery staple"
GENERIC = "Invalid email or password"


@dataclass(slots=True)
class FakeState:
    auth_repository: AuthRepository
    local_auth_service: LocalAuthService
    login_throttle: LoginThrottle = field(default_factory=LoginThrottle)


@pytest.fixture()
def repo(tmp_path: Path) -> AuthRepository:
    r = AuthRepository(tmp_path / "auth.db")
    r.initialize()
    return r


@pytest.fixture()
def client(repo: AuthRepository) -> TestClient:
    app = create_app()
    c = TestClient(app, raise_server_exceptions=False)
    app.state.asu_june_bot = FakeState(
        auth_repository=repo, local_auth_service=LocalAuthService(repo)
    )
    return c


def make_user(repo: AuthRepository, email: str = "alice@example.com", roles={"editor"}):
    user = repo.create_user(email=email, display_name="Alice")
    repo.create_local_credential(user.user_id, hash_password(PASSWORD))
    repo.set_user_roles(user.user_id, set(roles))
    return user


def login(client: TestClient, email: str = "alice@example.com", password: str = PASSWORD):
    return client.post("/auth/local/login", json={"email": email, "password": password})


# ------------------------------------------------------------------
# Login
# ------------------------------------------------------------------

def test_login_success_sets_cookie(client: TestClient, repo: AuthRepository) -> None:
    make_user(repo)
    resp = login(client)
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "alice@example.com"
    assert body["roles"] == ["editor"]
    assert "jobs.start" in body["permissions"]
    assert "expires_at" in body
    assert "ma_session" in resp.cookies
    set_cookie = resp.headers["set-cookie"].lower()
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie


def test_login_wrong_password_generic_error(client: TestClient, repo: AuthRepository) -> None:
    make_user(repo)
    resp = login(client, password="wrong")
    assert resp.status_code == 401
    assert resp.json()["detail"] == GENERIC


def test_login_unknown_email_same_response(client: TestClient, repo: AuthRepository) -> None:
    make_user(repo)
    wrong_pw = login(client, password="wrong")
    unknown = login(client, email="ghost@example.com")
    assert wrong_pw.status_code == unknown.status_code == 401
    assert wrong_pw.json() == unknown.json()


def test_login_disabled_user_rejected(client: TestClient, repo: AuthRepository) -> None:
    user = make_user(repo)
    repo.set_user_status(user.user_id, "disabled")
    resp = login(client)
    assert resp.status_code == 401
    assert resp.json()["detail"] == GENERIC


# ------------------------------------------------------------------
# /auth/me
# ------------------------------------------------------------------

def test_me_with_valid_session(client: TestClient, repo: AuthRepository) -> None:
    user = make_user(repo)
    login(client)
    resp = client.get("/auth/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == user.user_id
    assert body["email"] == "alice@example.com"
    assert body["roles"] == ["editor"]
    assert "jobs.start" in body["permissions"]


def test_me_without_cookie_401(client: TestClient) -> None:
    assert client.get("/auth/me").status_code == 401


def test_me_with_garbage_cookie_401(client: TestClient) -> None:
    client.cookies.set("ma_session", "garbage")
    assert client.get("/auth/me").status_code == 401


# ------------------------------------------------------------------
# Logout
# ------------------------------------------------------------------

def test_logout_revokes_session(client: TestClient, repo: AuthRepository) -> None:
    make_user(repo)
    csrf = login(client).json()["csrf_token"]
    assert client.get("/auth/me").status_code == 200
    resp = client.post("/auth/logout", headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 204
    client.cookies.clear()
    # session is revoked server-side, not just cookie-cleared
    assert client.get("/auth/me").status_code == 401


def test_logout_clears_cookie(client: TestClient, repo: AuthRepository) -> None:
    make_user(repo)
    csrf = login(client).json()["csrf_token"]
    resp = client.post("/auth/logout", headers={"X-CSRF-Token": csrf})
    set_cookie = resp.headers.get("set-cookie", "")
    assert "ma_session" in set_cookie


def test_logout_without_session_idempotent(client: TestClient) -> None:
    assert client.post("/auth/logout").status_code == 204


def test_logout_with_live_session_requires_csrf(
    client: TestClient, repo: AuthRepository
) -> None:
    make_user(repo)
    login(client)
    # No X-CSRF-Token on a live cookie session → 403, session stays valid
    assert client.post("/auth/logout").status_code == 403
    assert client.get("/auth/me").status_code == 200


def test_logout_with_wrong_csrf_rejected(
    client: TestClient, repo: AuthRepository
) -> None:
    make_user(repo)
    login(client)
    assert client.post(
        "/auth/logout", headers={"X-CSRF-Token": "wrong"}
    ).status_code == 403
    assert client.get("/auth/me").status_code == 200


def make_client_with_service(repo: AuthRepository, service: LocalAuthService) -> TestClient:
    from asu_june_bot.api.app import create_app
    app = create_app()
    app.state.asu_june_bot = FakeState(auth_repository=repo, local_auth_service=service)
    return TestClient(app, raise_server_exceptions=False)


def test_login_cookie_path_and_max_age(client: TestClient, repo: AuthRepository) -> None:
    make_user(repo)
    set_cookie = login(client).headers["set-cookie"].lower()
    assert "path=/" in set_cookie
    assert "max-age=86400" in set_cookie  # default TTL 24h


def test_cookie_secure_auto_http_not_secure(client: TestClient, repo: AuthRepository) -> None:
    make_user(repo)
    assert "secure" not in login(client).headers["set-cookie"].lower()


def test_cookie_secure_auto_forwarded_https(client: TestClient, repo: AuthRepository) -> None:
    make_user(repo)
    resp = client.post(
        "/auth/local/login",
        json={"email": "alice@example.com", "password": PASSWORD},
        headers={"x-forwarded-proto": "https"},
    )
    assert "secure" in resp.headers["set-cookie"].lower()


def test_cookie_secure_true_forces_secure(repo: AuthRepository) -> None:
    c = make_client_with_service(repo, LocalAuthService(repo, cookie_secure="true"))
    make_user(repo, email="sec@example.com")
    resp = c.post("/auth/local/login", json={"email": "sec@example.com", "password": PASSWORD})
    assert "secure" in resp.headers["set-cookie"].lower()


def test_cookie_secure_false_never_secure(repo: AuthRepository) -> None:
    c = make_client_with_service(repo, LocalAuthService(repo, cookie_secure="false"))
    make_user(repo, email="nosec@example.com")
    resp = c.post(
        "/auth/local/login",
        json={"email": "nosec@example.com", "password": PASSWORD},
        headers={"x-forwarded-proto": "https"},
    )
    assert "secure" not in resp.headers["set-cookie"].lower()


def test_normalize_cookie_secure_values() -> None:
    from asu_june_bot.api.dependencies import _normalize_cookie_secure
    assert _normalize_cookie_secure(None) == "auto"
    assert _normalize_cookie_secure(True) == "true"
    assert _normalize_cookie_secure(False) == "false"
    assert _normalize_cookie_secure("  True ") == "true"
    assert _normalize_cookie_secure("AUTO") == "auto"
    with pytest.raises(ValueError):
        _normalize_cookie_secure("yes")
    with pytest.raises(ValueError):
        _normalize_cookie_secure(1)


def test_configurable_cookie_name(repo: AuthRepository) -> None:
    from asu_june_bot.api.app import create_app
    app = create_app()
    custom_service = LocalAuthService(repo, cookie_name="custom_cookie")
    app.state.asu_june_bot = FakeState(auth_repository=repo, local_auth_service=custom_service)
    c = TestClient(app, raise_server_exceptions=False)
    make_user(repo, email="custom@example.com")
    resp = c.post("/auth/local/login", json={"email": "custom@example.com", "password": PASSWORD})
    assert resp.status_code == 200
    assert "custom_cookie" in resp.cookies


def test_revoked_token_rejected_even_if_cookie_kept(
    client: TestClient, repo: AuthRepository
) -> None:
    make_user(repo)
    resp = login(client)
    token = resp.cookies["ma_session"]
    csrf = resp.json()["csrf_token"]
    client.post("/auth/logout", headers={"X-CSRF-Token": csrf})
    client.cookies.set("ma_session", token)
    assert client.get("/auth/me").status_code == 401
