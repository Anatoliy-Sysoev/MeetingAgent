"""Integration tests for the admin bootstrap and user management API."""
from __future__ import annotations

import os
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
from asu_june_bot.api.bootstrap_policy import BootstrapPolicy  # noqa: E402
from asu_june_bot.auth.passwords import hash_password  # noqa: E402
from asu_june_bot.auth.repository import AuthRepository  # noqa: E402
from asu_june_bot.auth.service import AdminService, LocalAuthService  # noqa: E402
from asu_june_bot.auth.throttle import LoginThrottle  # noqa: E402

MACHINE_TOKEN = "admin-api-test-token"
MACHINE_AUTH = {"Authorization": f"Bearer {MACHINE_TOKEN}"}
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASS = "adminpassword1"
VIEWER_EMAIL = "viewer@example.com"
VIEWER_PASS = "viewerpassword1"
# Bootstrap secret used by all test_admin_api tests; TestClient host is "testclient"
# (non-local), so allow_remote=True + secret is required.
_TEST_BOOTSTRAP_SECRET = "test-bootstrap-secret-for-admin-api"
_TEST_BOOTSTRAP_POLICY = BootstrapPolicy(allow_remote=True, secret=_TEST_BOOTSTRAP_SECRET)


@dataclass(slots=True)
class FakeState:
    auth_repository: AuthRepository
    local_auth_service: LocalAuthService
    admin_service: AdminService
    login_throttle: LoginThrottle = field(default_factory=LoginThrottle)
    bootstrap_policy: BootstrapPolicy = field(
        default_factory=lambda: _TEST_BOOTSTRAP_POLICY
    )


@pytest.fixture()
def repo(tmp_path: Path) -> AuthRepository:
    r = AuthRepository(tmp_path / "auth.db")
    r.initialize()
    return r


@pytest.fixture()
def client(repo: AuthRepository) -> TestClient:
    os.environ["MEETINGAGENT_API_TOKEN"] = MACHINE_TOKEN
    app = create_app()
    c = TestClient(app, raise_server_exceptions=False)
    app.state.asu_june_bot = FakeState(
        auth_repository=repo,
        local_auth_service=LocalAuthService(repo),
        admin_service=AdminService(repo),
    )
    return c


def bootstrap(client: TestClient, email: str = ADMIN_EMAIL, password: str = ADMIN_PASS) -> dict:
    resp = client.post(
        "/admin/bootstrap",
        json={"email": email, "password": password},
        headers={"X-Bootstrap-Token": _TEST_BOOTSTRAP_SECRET},
    )
    assert resp.status_code == 201, resp.json()
    return resp.json()


def admin_login(client: TestClient, email: str = ADMIN_EMAIL) -> tuple[str, str]:
    resp = client.post("/auth/local/login", json={"email": email, "password": ADMIN_PASS})
    assert resp.status_code == 200, resp.json()
    return resp.cookies["ma_session"], resp.json()["csrf_token"]


def viewer_login(client: TestClient) -> tuple[str, str]:
    resp = client.post(
        "/auth/local/login", json={"email": VIEWER_EMAIL, "password": VIEWER_PASS}
    )
    assert resp.status_code == 200, resp.json()
    return resp.cookies["ma_session"], resp.json()["csrf_token"]


def create_viewer(client: TestClient, repo: AuthRepository) -> dict:
    """Create a viewer user directly via repo (for tests that need non-admin user)."""
    user = repo.create_user(email=VIEWER_EMAIL)
    repo.create_local_credential(user.user_id, hash_password(VIEWER_PASS))
    repo.set_user_roles(user.user_id, {"viewer"})
    return {"user_id": user.user_id, "email": user.email}


# ------------------------------------------------------------------
# 12. POST /admin/bootstrap succeeds on empty DB
# ------------------------------------------------------------------

def test_bootstrap_succeeds_on_empty_db(client: TestClient) -> None:
    resp = client.post(
        "/admin/bootstrap",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASS},
        headers={"X-Bootstrap-Token": _TEST_BOOTSTRAP_SECRET},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == ADMIN_EMAIL
    assert "admin" in body["roles"]
    assert body["status"] == "active"


# ------------------------------------------------------------------
# 13. POST /admin/bootstrap second call returns 409
# ------------------------------------------------------------------

def test_bootstrap_second_call_returns_409(client: TestClient) -> None:
    bootstrap(client)
    resp = client.post(
        "/admin/bootstrap",
        json={"email": "other@example.com", "password": ADMIN_PASS},
        headers={"X-Bootstrap-Token": _TEST_BOOTSTRAP_SECRET},
    )
    assert resp.status_code == 409


# ------------------------------------------------------------------
# 14. Bootstrap response excludes password hash
# ------------------------------------------------------------------

def test_bootstrap_response_excludes_password_hash(client: TestClient) -> None:
    resp = client.post(
        "/admin/bootstrap",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASS},
        headers={"X-Bootstrap-Token": _TEST_BOOTSTRAP_SECRET},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "password_hash" not in body
    assert "password" not in body


# ------------------------------------------------------------------
# 15. Admin can create viewer/editor/admin user
# ------------------------------------------------------------------

@pytest.mark.parametrize("role", ["viewer", "editor", "admin"])
def test_admin_can_create_user_with_role(client: TestClient, role: str) -> None:
    bootstrap(client)
    cookie, csrf = admin_login(client)
    resp = client.post(
        "/admin/users",
        json={"email": f"{role}user@example.com", "password": "somepass12", "roles": [role]},
        cookies={"ma_session": cookie},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 201, resp.json()
    body = resp.json()
    assert role in body["roles"]
    assert "password_hash" not in body


# ------------------------------------------------------------------
# 16. Non-admin user cannot create users
# ------------------------------------------------------------------

def test_non_admin_user_cannot_create_users(client: TestClient, repo: AuthRepository) -> None:
    bootstrap(client)
    create_viewer(client, repo)
    cookie, csrf = viewer_login(client)
    resp = client.post(
        "/admin/users",
        json={"email": "new@example.com", "password": "somepass12", "roles": ["viewer"]},
        cookies={"ma_session": cookie},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 403


# ------------------------------------------------------------------
# 17. Machine bearer cannot create users
# ------------------------------------------------------------------

def test_machine_bearer_cannot_create_users(client: TestClient) -> None:
    resp = client.post(
        "/admin/users",
        json={"email": "new@example.com", "password": "somepass12", "roles": ["viewer"]},
        headers=MACHINE_AUTH,
    )
    assert resp.status_code == 403


# ------------------------------------------------------------------
# 18. Unauthenticated admin route returns 401
# ------------------------------------------------------------------

def test_unauthenticated_admin_route_returns_401(client: TestClient) -> None:
    resp = client.get("/admin/users")
    assert resp.status_code == 401


# ------------------------------------------------------------------
# 19. Admin write without CSRF returns 403
# ------------------------------------------------------------------

def test_admin_write_without_csrf_returns_403(client: TestClient) -> None:
    bootstrap(client)
    cookie, _ = admin_login(client)
    resp = client.post(
        "/admin/users",
        json={"email": "new@example.com", "password": "somepass12", "roles": ["viewer"]},
        cookies={"ma_session": cookie},
        # No X-CSRF-Token
    )
    assert resp.status_code == 403


# ------------------------------------------------------------------
# 20. Admin write with valid CSRF succeeds
# ------------------------------------------------------------------

def test_admin_write_with_valid_csrf_succeeds(client: TestClient) -> None:
    bootstrap(client)
    cookie, csrf = admin_login(client)
    resp = client.post(
        "/admin/users",
        json={"email": "new@example.com", "password": "somepass12", "roles": ["viewer"]},
        cookies={"ma_session": cookie},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 201


# ------------------------------------------------------------------
# 21. Admin can list users
# ------------------------------------------------------------------

def test_admin_can_list_users(client: TestClient) -> None:
    bootstrap(client)
    cookie, _ = admin_login(client)
    resp = client.get("/admin/users", cookies={"ma_session": cookie})
    assert resp.status_code == 200
    body = resp.json()
    assert "users" in body
    assert len(body["users"]) == 1


# ------------------------------------------------------------------
# 22. Admin can read user
# ------------------------------------------------------------------

def test_admin_can_read_user(client: TestClient) -> None:
    result = bootstrap(client)
    cookie, _ = admin_login(client)
    user_id = result["user_id"]
    resp = client.get(f"/admin/users/{user_id}", cookies={"ma_session": cookie})
    assert resp.status_code == 200
    assert resp.json()["user_id"] == user_id


def test_get_nonexistent_user_returns_404(client: TestClient) -> None:
    bootstrap(client)
    cookie, _ = admin_login(client)
    resp = client.get("/admin/users/nonexistent-id", cookies={"ma_session": cookie})
    assert resp.status_code == 404


# ------------------------------------------------------------------
# 23. Admin can disable user
# ------------------------------------------------------------------

def test_admin_can_disable_user(client: TestClient) -> None:
    bootstrap(client)
    cookie, csrf = admin_login(client)
    # Create a second user to disable
    resp = client.post(
        "/admin/users",
        json={"email": "target@example.com", "password": "targetpass1", "roles": ["viewer"]},
        cookies={"ma_session": cookie},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 201
    target_id = resp.json()["user_id"]

    resp = client.post(
        f"/admin/users/{target_id}/disable",
        cookies={"ma_session": cookie},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "disabled"


# ------------------------------------------------------------------
# 24. Admin can enable user
# ------------------------------------------------------------------

def test_admin_can_enable_user(client: TestClient) -> None:
    bootstrap(client)
    cookie, csrf = admin_login(client)
    resp = client.post(
        "/admin/users",
        json={"email": "target@example.com", "password": "targetpass1", "roles": ["viewer"]},
        cookies={"ma_session": cookie},
        headers={"X-CSRF-Token": csrf},
    )
    target_id = resp.json()["user_id"]
    client.post(
        f"/admin/users/{target_id}/disable",
        cookies={"ma_session": cookie},
        headers={"X-CSRF-Token": csrf},
    )
    resp = client.post(
        f"/admin/users/{target_id}/enable",
        cookies={"ma_session": cookie},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


# ------------------------------------------------------------------
# 25. Last active admin protection returns 409
# ------------------------------------------------------------------

def test_last_active_admin_protection_returns_409(client: TestClient) -> None:
    result = bootstrap(client)
    cookie, csrf = admin_login(client)
    resp = client.post(
        f"/admin/users/{result['user_id']}/disable",
        cookies={"ma_session": cookie},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 409


def test_last_active_admin_demotion_returns_409(client: TestClient) -> None:
    result = bootstrap(client)
    cookie, csrf = admin_login(client)
    resp = client.patch(
        f"/admin/users/{result['user_id']}",
        json={"roles": ["viewer"]},
        cookies={"ma_session": cookie},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 409


# ------------------------------------------------------------------
# Extra: unknown role returns 422
# ------------------------------------------------------------------

def test_create_user_unknown_role_returns_422(client: TestClient) -> None:
    bootstrap(client)
    cookie, csrf = admin_login(client)
    resp = client.post(
        "/admin/users",
        json={"email": "new@example.com", "password": "somepass12", "roles": ["superuser"]},
        cookies={"ma_session": cookie},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 422


def test_duplicate_email_returns_409(client: TestClient) -> None:
    result = bootstrap(client)
    cookie, csrf = admin_login(client)
    resp = client.post(
        "/admin/users",
        json={"email": result["email"], "password": "somepass12", "roles": ["viewer"]},
        cookies={"ma_session": cookie},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 409


def test_patch_user_display_name(client: TestClient) -> None:
    result = bootstrap(client)
    cookie, csrf = admin_login(client)
    resp = client.patch(
        f"/admin/users/{result['user_id']}",
        json={"display_name": "Main Admin"},
        cookies={"ma_session": cookie},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Main Admin"


# ------------------------------------------------------------------
# Machine bearer explicitly forbidden on all user-management routes
# ------------------------------------------------------------------

def test_machine_bearer_cannot_list_users(client: TestClient) -> None:
    resp = client.get("/admin/users", headers=MACHINE_AUTH)
    assert resp.status_code == 403


def test_machine_bearer_cannot_get_user(client: TestClient) -> None:
    bootstrap(client)
    resp = client.get("/admin/users/some-id", headers=MACHINE_AUTH)
    assert resp.status_code == 403
