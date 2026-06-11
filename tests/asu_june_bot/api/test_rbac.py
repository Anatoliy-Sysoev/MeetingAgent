"""Integration tests for RBAC, CSRF, and auth dependency resolution."""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
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
from asu_june_bot.meetings.service import MeetingsService  # noqa: E402

MACHINE_TOKEN = "machine-test-token"
MACHINE_AUTH = {"Authorization": f"Bearer {MACHINE_TOKEN}"}
PASSWORD = "correct horse battery staple"

VALID_CARD = {
    "schema_version": 1,
    "meeting_id": "2026-01-15__rbac-test",
    "title": "RBAC Test Meeting",
    "date": "2026-01-15",
    "processing_status": "indexed",
    "participants": [],
    "source": {"kind": "offline_record"},
    "artifacts": {},
    "classification": {},
    "links": {},
    "retention": {"policy": "default"},
    "rag": {"index_policy": "structured_artifacts_and_final_transcript"},
    "created_at": "2026-01-15T10:00:00",
    "updated_at": "2026-01-15T11:00:00",
}


@dataclass(slots=True)
class FakeState:
    meetings_service: MeetingsService
    local_auth_service: LocalAuthService


@pytest.fixture()
def repo(tmp_path: Path) -> AuthRepository:
    r = AuthRepository(tmp_path / "auth.db")
    r.initialize()
    return r


@pytest.fixture()
def service(repo: AuthRepository) -> LocalAuthService:
    return LocalAuthService(repo)


@pytest.fixture()
def client(tmp_path: Path, repo: AuthRepository, service: LocalAuthService) -> TestClient:
    os.environ["MEETINGAGENT_API_TOKEN"] = MACHINE_TOKEN
    meetings_root = tmp_path / "meetings"
    meetings_root.mkdir()
    app = create_app()
    c = TestClient(app, raise_server_exceptions=False)
    app.state.asu_june_bot = FakeState(
        meetings_service=MeetingsService(meetings_root),
        local_auth_service=service,
    )
    return c


def make_user(repo: AuthRepository, email: str, role: str) -> None:
    user = repo.create_user(email=email)
    repo.create_local_credential(user.user_id, hash_password(PASSWORD))
    repo.set_user_roles(user.user_id, {role})


def browser_login(client: TestClient, email: str) -> tuple[str, str]:
    """Returns (session_cookie, csrf_token)."""
    resp = client.post("/auth/local/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200, resp.json()
    return resp.cookies["ma_session"], resp.json()["csrf_token"]


def make_meeting_dir(tmp_path: Path) -> None:
    d = tmp_path / "meetings" / "2026-01-15__rbac-test"
    d.mkdir(parents=True, exist_ok=True)
    (d / "meeting.json").write_text(json.dumps(VALID_CARD), encoding="utf-8")


# ------------------------------------------------------------------
# get_optional_principal: anonymous / browser / machine
# ------------------------------------------------------------------

def test_anonymous_no_credentials(client: TestClient) -> None:
    resp = client.get("/meetings", headers={})
    assert resp.status_code == 401


def test_machine_bearer_resolves(client: TestClient, tmp_path: Path) -> None:
    make_meeting_dir(tmp_path)
    resp = client.get("/meetings", headers=MACHINE_AUTH)
    assert resp.status_code == 200


def test_browser_session_resolves(client: TestClient, repo: AuthRepository) -> None:
    make_user(repo, "viewer@example.com", "viewer")
    cookie, _ = browser_login(client, "viewer@example.com")
    client.cookies.set("ma_session", cookie)
    resp = client.get("/meetings")
    assert resp.status_code == 200


# ------------------------------------------------------------------
# Invalid Bearer → 401, no fallback to cookie
# ------------------------------------------------------------------

def test_invalid_bearer_no_cookie_fallback(
    client: TestClient, repo: AuthRepository
) -> None:
    make_user(repo, "viewer2@example.com", "viewer")
    cookie, _ = browser_login(client, "viewer2@example.com")
    # Set both invalid bearer AND valid cookie — must get 401, not 200
    resp = client.get(
        "/meetings",
        headers={"Authorization": "Bearer wrong-token"},
        cookies={"ma_session": cookie},
    )
    assert resp.status_code == 401


# ------------------------------------------------------------------
# Viewer / editor / admin permission matrix on read routes
# ------------------------------------------------------------------

def test_viewer_can_read_meetings(client: TestClient, repo: AuthRepository) -> None:
    make_user(repo, "v@example.com", "viewer")
    cookie, _ = browser_login(client, "v@example.com")
    client.cookies.set("ma_session", cookie)
    assert client.get("/meetings").status_code == 200


def test_editor_can_read_meetings(client: TestClient, repo: AuthRepository) -> None:
    make_user(repo, "e@example.com", "editor")
    cookie, _ = browser_login(client, "e@example.com")
    client.cookies.set("ma_session", cookie)
    assert client.get("/meetings").status_code == 200


# ------------------------------------------------------------------
# Machine principal permission scope
# ------------------------------------------------------------------

def test_machine_can_read_meetings(client: TestClient, tmp_path: Path) -> None:
    make_meeting_dir(tmp_path)
    assert client.get("/meetings", headers=MACHINE_AUTH).status_code == 200


def test_machine_has_no_users_manage(client: TestClient) -> None:
    from asu_june_bot.auth.permissions import MACHINE_PERMISSIONS
    assert "users.manage" not in MACHINE_PERMISSIONS
    assert "roles.manage" not in MACHINE_PERMISSIONS
    assert "meetings.delete" not in MACHINE_PERMISSIONS
    assert "tokens.manage" not in MACHINE_PERMISSIONS


# ------------------------------------------------------------------
# CSRF — browser write requests
# ------------------------------------------------------------------

def test_viewer_cannot_ingest(
    client: TestClient, repo: AuthRepository, tmp_path: Path
) -> None:
    make_user(repo, "viewer3@example.com", "viewer")
    cookie, csrf = browser_login(client, "viewer3@example.com")
    client.cookies.set("ma_session", cookie)
    resp = client.post(
        "/meetings/ingest",
        files={"file": ("a.mp3", b"data", "audio/mpeg")},
        headers={"X-CSRF-Token": csrf},
    )
    # sessions.upload not in viewer perms → 403
    assert resp.status_code == 403


def test_editor_ingest_without_csrf_returns_403(
    client: TestClient, repo: AuthRepository
) -> None:
    make_user(repo, "ed1@example.com", "editor")
    cookie, _ = browser_login(client, "ed1@example.com")
    client.cookies.set("ma_session", cookie)
    resp = client.post(
        "/meetings/ingest",
        files={"file": ("a.mp3", b"data", "audio/mpeg")},
        # No X-CSRF-Token header
    )
    assert resp.status_code == 403


def test_editor_ingest_with_wrong_csrf_returns_403(
    client: TestClient, repo: AuthRepository
) -> None:
    make_user(repo, "ed2@example.com", "editor")
    cookie, _ = browser_login(client, "ed2@example.com")
    client.cookies.set("ma_session", cookie)
    resp = client.post(
        "/meetings/ingest",
        files={"file": ("a.mp3", b"data", "audio/mpeg")},
        headers={"X-CSRF-Token": "wrong-token"},
    )
    assert resp.status_code == 403


def test_editor_ingest_with_valid_csrf_proceeds(
    client: TestClient, repo: AuthRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CSRF passes; 201 or 422 depending on file, not 401/403."""
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", MACHINE_TOKEN)
    make_user(repo, "ed3@example.com", "editor")
    cookie, csrf = browser_login(client, "ed3@example.com")
    client.cookies.set("ma_session", cookie)
    resp = client.post(
        "/meetings/ingest",
        files={"file": ("a.mp3", b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00", "audio/mpeg")},
        data={"title": "RBAC test", "date": "2026-01-15"},
        headers={"X-CSRF-Token": csrf},
    )
    # Auth passed — result is 201 (created) or 409 (dup); not 401/403
    assert resp.status_code not in (401, 403)


def test_wrong_session_csrf_rejected(
    client: TestClient, repo: AuthRepository
) -> None:
    """CSRF token from one session must not be accepted for another session's cookie."""
    make_user(repo, "user_a@example.com", "editor")
    make_user(repo, "user_b@example.com", "editor")
    cookie_a, csrf_a = browser_login(client, "user_a@example.com")
    cookie_b, csrf_b = browser_login(client, "user_b@example.com")
    # Use cookie_a but csrf from session_b
    client.cookies.set("ma_session", cookie_a)
    resp = client.post(
        "/meetings/ingest",
        files={"file": ("a.mp3", b"data", "audio/mpeg")},
        headers={"X-CSRF-Token": csrf_b},
    )
    assert resp.status_code == 403


def test_machine_bearer_write_no_csrf_needed(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Machine bearer token does not require X-CSRF-Token."""
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", MACHINE_TOKEN)
    resp = client.post(
        "/meetings/ingest",
        files={"file": ("a.mp3", b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00", "audio/mpeg")},
        data={"title": "Machine upload", "date": "2026-01-15"},
        headers=MACHINE_AUTH,
    )
    assert resp.status_code not in (401, 403)


# ------------------------------------------------------------------
# Logout revokes CSRF state
# ------------------------------------------------------------------

def test_logout_invalidates_csrf(
    client: TestClient, repo: AuthRepository
) -> None:
    make_user(repo, "ed4@example.com", "editor")
    cookie, csrf = browser_login(client, "ed4@example.com")
    client.cookies.set("ma_session", cookie)
    client.post("/auth/logout")
    client.cookies.set("ma_session", cookie)
    resp = client.post(
        "/meetings/ingest",
        files={"file": ("a.mp3", b"data", "audio/mpeg")},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 401


# ------------------------------------------------------------------
# Health and login remain public
# ------------------------------------------------------------------

def test_login_route_is_public(client: TestClient) -> None:
    """Login must be reachable without any credentials."""
    resp = client.post(
        "/auth/local/login",
        json={"email": "nobody@example.com", "password": "x"},
        headers={},  # No auth
    )
    # 401 means wrong creds, not auth-blocked — route is reachable
    assert resp.status_code == 401


# ------------------------------------------------------------------
# Disabled/expired sessions
# ------------------------------------------------------------------

def test_disabled_user_session_rejected(
    client: TestClient, repo: AuthRepository
) -> None:
    make_user(repo, "dis@example.com", "editor")
    cookie, _ = browser_login(client, "dis@example.com")
    user = repo.get_user_by_email("dis@example.com")
    repo.set_user_status(user.user_id, "disabled")
    client.cookies.set("ma_session", cookie)
    assert client.get("/meetings").status_code == 401
