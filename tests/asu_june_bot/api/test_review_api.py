"""Integration tests for the review queue API."""
from __future__ import annotations

import json
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
from asu_june_bot.observability.review_queue import ReviewQueue  # noqa: E402

MACHINE_TOKEN = "review-api-test-token"
MACHINE_AUTH = {"Authorization": f"Bearer {MACHINE_TOKEN}"}
ADMIN_EMAIL = "admin@review.test"
ADMIN_PASS = "adminpassword1"
VIEWER_EMAIL = "viewer@review.test"
VIEWER_PASS = "viewerpassword1"
_BOOTSTRAP_SECRET = "test-bootstrap-secret-for-review-api"
_BOOTSTRAP_POLICY = BootstrapPolicy(allow_remote=True, secret=_BOOTSTRAP_SECRET)


@dataclass(slots=True)
class FakeState:
    auth_repository: AuthRepository
    local_auth_service: LocalAuthService
    admin_service: AdminService
    review_queue: ReviewQueue
    login_throttle: LoginThrottle = field(default_factory=LoginThrottle)
    bootstrap_policy: BootstrapPolicy = field(default_factory=lambda: _BOOTSTRAP_POLICY)


@pytest.fixture()
def repo(tmp_path: Path) -> AuthRepository:
    r = AuthRepository(tmp_path / "auth.db")
    r.initialize()
    return r


@pytest.fixture()
def review_queue(tmp_path: Path) -> ReviewQueue:
    return ReviewQueue(
        runs_path=tmp_path / "chat_runs.jsonl",
        labels_path=tmp_path / "chat_run_labels.jsonl",
    )


@pytest.fixture()
def client(repo: AuthRepository, review_queue: ReviewQueue) -> TestClient:
    os.environ["MEETINGAGENT_API_TOKEN"] = MACHINE_TOKEN
    app = create_app()
    c = TestClient(app, raise_server_exceptions=False)
    app.state.asu_june_bot = FakeState(
        auth_repository=repo,
        local_auth_service=LocalAuthService(repo),
        admin_service=AdminService(repo),
        review_queue=review_queue,
    )
    return c


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _bootstrap_admin(client: TestClient) -> None:
    resp = client.post(
        "/admin/bootstrap",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASS},
        headers={"X-Bootstrap-Token": _BOOTSTRAP_SECRET},
    )
    assert resp.status_code == 201, resp.json()


def _admin_login(client: TestClient) -> tuple[str, str]:
    resp = client.post("/auth/local/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
    assert resp.status_code == 200, resp.json()
    return resp.cookies["ma_session"], resp.json()["csrf_token"]


def _create_viewer(client: TestClient, repo: AuthRepository) -> None:
    user = repo.create_user(email=VIEWER_EMAIL)
    repo.create_local_credential(user.user_id, hash_password(VIEWER_PASS))
    repo.set_user_roles(user.user_id, {"viewer"})


def _viewer_login(client: TestClient) -> tuple[str, str]:
    resp = client.post("/auth/local/login", json={"email": VIEWER_EMAIL, "password": VIEWER_PASS})
    assert resp.status_code == 200, resp.json()
    return resp.cookies["ma_session"], resp.json()["csrf_token"]


def _write_runs(path: Path, runs: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in runs:
            fh.write(json.dumps(r) + "\n")


def _make_run(run_id: str, **kwargs) -> dict:
    return {
        "run_id": run_id,
        "created_at": "2026-06-20T10:00:00+00:00",
        "query": f"test query {run_id}",
        "status": "answered",
        "guard_decision": "allow",
        "answer_preview": "test answer",
        "answer_chars": 11,
        "prompt_sources": "INTERNAL SECRET PROMPT",
        **kwargs,
    }


# ---------------------------------------------------------------------------
# GET /admin/review/chat-runs — auth
# ---------------------------------------------------------------------------

def test_list_runs_requires_auth(client: TestClient) -> None:
    resp = client.get("/admin/review/chat-runs")
    assert resp.status_code == 401


def test_list_runs_machine_token_blocked(client: TestClient) -> None:
    resp = client.get("/admin/review/chat-runs", headers=MACHINE_AUTH)
    assert resp.status_code == 403


def test_list_runs_viewer_blocked(client: TestClient, repo: AuthRepository) -> None:
    _bootstrap_admin(client)
    _create_viewer(client, repo)
    session, _ = _viewer_login(client)
    resp = client.get("/admin/review/chat-runs", cookies={"ma_session": session})
    assert resp.status_code == 403


def test_list_runs_admin_ok(client: TestClient, review_queue: ReviewQueue) -> None:
    _bootstrap_admin(client)
    session, _ = _admin_login(client)
    resp = client.get("/admin/review/chat-runs", cookies={"ma_session": session})
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data


# ---------------------------------------------------------------------------
# GET /admin/review/chat-runs — content
# ---------------------------------------------------------------------------

def test_list_runs_returns_runs(client: TestClient, review_queue: ReviewQueue) -> None:
    _write_runs(review_queue.runs_path, [_make_run("r1"), _make_run("r2")])
    _bootstrap_admin(client)
    session, _ = _admin_login(client)
    resp = client.get("/admin/review/chat-runs", cookies={"ma_session": session})
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 2


def test_list_runs_does_not_expose_prompt_internals(client: TestClient, review_queue: ReviewQueue) -> None:
    _write_runs(review_queue.runs_path, [_make_run("r1")])
    _bootstrap_admin(client)
    session, _ = _admin_login(client)
    resp = client.get("/admin/review/chat-runs", cookies={"ma_session": session})
    item = resp.json()["items"][0]
    assert "prompt_sources" not in item


def test_list_runs_filter_by_status(client: TestClient, review_queue: ReviewQueue) -> None:
    _write_runs(review_queue.runs_path, [
        _make_run("r1", status="answered"),
        _make_run("r2", status="refused"),
    ])
    _bootstrap_admin(client)
    session, _ = _admin_login(client)
    resp = client.get(
        "/admin/review/chat-runs?status=refused",
        cookies={"ma_session": session},
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["run_id"] == "r2"


# ---------------------------------------------------------------------------
# POST /admin/review/chat-runs/{run_id}/label
# ---------------------------------------------------------------------------

def test_set_label_requires_auth(client: TestClient) -> None:
    resp = client.post("/admin/review/chat-runs/r1/label", json={"label": "correct"})
    assert resp.status_code == 401


def test_set_label_machine_token_blocked(client: TestClient) -> None:
    resp = client.post(
        "/admin/review/chat-runs/r1/label",
        json={"label": "correct"},
        headers=MACHINE_AUTH,
    )
    assert resp.status_code == 403


def test_set_label_viewer_blocked(client: TestClient, repo: AuthRepository) -> None:
    _bootstrap_admin(client)
    _create_viewer(client, repo)
    session, csrf = _viewer_login(client)
    resp = client.post(
        "/admin/review/chat-runs/r1/label",
        json={"label": "correct"},
        cookies={"ma_session": session},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 403


def test_set_label_admin_ok(client: TestClient, review_queue: ReviewQueue) -> None:
    _bootstrap_admin(client)
    session, csrf = _admin_login(client)
    resp = client.post(
        "/admin/review/chat-runs/r1/label",
        json={"label": "correct"},
        cookies={"ma_session": session},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["run_id"] == "r1"
    assert data["label"] == "correct"


def test_set_label_invalid_label_returns_422(client: TestClient) -> None:
    _bootstrap_admin(client)
    session, csrf = _admin_login(client)
    resp = client.post(
        "/admin/review/chat-runs/r1/label",
        json={"label": "not_a_real_label"},
        cookies={"ma_session": session},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 422


def test_set_label_with_manual_issue_and_comment(client: TestClient, review_queue: ReviewQueue) -> None:
    _bootstrap_admin(client)
    session, csrf = _admin_login(client)
    resp = client.post(
        "/admin/review/chat-runs/r1/label",
        json={"label": "false_refuse", "manual_issue": "GH-123", "comment": "should have answered"},
        cookies={"ma_session": session},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["manual_issue"] == "GH-123"
    assert data["comment"] == "should have answered"


def test_set_label_run_id_too_long_returns_422(client: TestClient) -> None:
    _bootstrap_admin(client)
    session, csrf = _admin_login(client)
    long_id = "x" * 200
    resp = client.post(
        f"/admin/review/chat-runs/{long_id}/label",
        json={"label": "correct"},
        cookies={"ma_session": session},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 422


def test_set_label_writes_to_sidecar(client: TestClient, review_queue: ReviewQueue) -> None:
    _bootstrap_admin(client)
    session, csrf = _admin_login(client)
    client.post(
        "/admin/review/chat-runs/r1/label",
        json={"label": "needs_case"},
        cookies={"ma_session": session},
        headers={"X-CSRF-Token": csrf},
    )
    labels = review_queue._load_labels()
    assert "r1" in labels
    assert labels["r1"]["label"] == "needs_case"


# ---------------------------------------------------------------------------
# GET /admin/review/chat-runs/export
# ---------------------------------------------------------------------------

def test_export_requires_auth(client: TestClient) -> None:
    resp = client.get("/admin/review/chat-runs/export")
    assert resp.status_code == 401


def test_export_admin_ok(client: TestClient, review_queue: ReviewQueue) -> None:
    _write_runs(review_queue.runs_path, [_make_run("r1"), _make_run("r2")])
    _bootstrap_admin(client)
    session, _ = _admin_login(client)
    resp = client.get("/admin/review/chat-runs/export", cookies={"ma_session": session})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 2


def test_export_joined_includes_label(client: TestClient, review_queue: ReviewQueue) -> None:
    _write_runs(review_queue.runs_path, [_make_run("r1")])
    _bootstrap_admin(client)
    session, csrf = _admin_login(client)
    client.post(
        "/admin/review/chat-runs/r1/label",
        json={"label": "correct"},
        cookies={"ma_session": session},
        headers={"X-CSRF-Token": csrf},
    )
    resp = client.get("/admin/review/chat-runs/export", cookies={"ma_session": session})
    item = resp.json()["items"][0]
    assert item["current_label"] == "correct"


def test_export_does_not_expose_prompt_internals(client: TestClient, review_queue: ReviewQueue) -> None:
    _write_runs(review_queue.runs_path, [_make_run("r1")])
    _bootstrap_admin(client)
    session, _ = _admin_login(client)
    resp = client.get("/admin/review/chat-runs/export", cookies={"ma_session": session})
    item = resp.json()["items"][0]
    assert "prompt_sources" not in item


# ---------------------------------------------------------------------------
# UI security static checks (no XSS via innerHTML, CSRF via /auth/csrf)
# ---------------------------------------------------------------------------

def _get_html(client: TestClient) -> str:
    resp = client.get("/")
    assert resp.status_code == 200
    return resp.text


def test_review_ui_csrf_uses_auth_csrf_endpoint(client: TestClient) -> None:
    html = _get_html(client)
    assert "/auth/csrf" in html, "Review UI must use /auth/csrf to obtain CSRF token"


def test_review_ui_no_innerHTML_with_run_fields(client: TestClient) -> None:
    html = _get_html(client)
    # Ensure run_id, status, guard_decision are not assigned via innerHTML
    assert "run.run_id" not in html.split("innerHTML")[1] if "innerHTML" in html else True
    # More direct: the template must not contain the known XSS pattern
    assert "meta.innerHTML" not in html, "run fields must be set via textContent, not innerHTML"


def test_review_ui_no_inline_onclick(client: TestClient) -> None:
    html = _get_html(client)
    assert 'onclick="loadReviewRuns()"' not in html, "reviewLoad button must use addEventListener, not inline onclick"
