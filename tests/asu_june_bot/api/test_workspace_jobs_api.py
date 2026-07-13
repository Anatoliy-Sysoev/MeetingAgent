"""Tests for workspace job controls: CSRF endpoint, stages metadata, and
CSRF/RBAC enforcement on job start/cancel from browser sessions."""
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
from asu_june_bot.api.ui_assets import load_ui_asset  # noqa: E402
from asu_june_bot.auth.repository import AuthRepository  # noqa: E402
from asu_june_bot.auth.service import AdminService, LocalAuthService  # noqa: E402
from asu_june_bot.auth.throttle import LoginThrottle  # noqa: E402
from asu_june_bot.jobs.runner import JobRunner  # noqa: E402
from asu_june_bot.meetings.service import MeetingsService  # noqa: E402

TOKEN = "test-wjc-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
MEETING_ID = "2026-02-01__wjc"

VALID_CARD = {
    "schema_version": 1,
    "meeting_id": MEETING_ID,
    "title": "WJC Meeting",
    "date": "2026-02-01",
    "processing_status": "new",
    "participants": [],
    "source": {"kind": "offline_record"},
    "artifacts": {},
    "classification": {},
    "links": {},
    "retention": {"policy": "default"},
    "rag": {"index_policy": "structured_artifacts_and_final_transcript"},
    "created_at": "2026-02-01T10:00:00+00:00",
    "updated_at": "2026-02-01T10:00:00+00:00",
}


@dataclass(slots=True)
class FakeState:
    meetings_service: MeetingsService
    job_runner: JobRunner
    local_auth_service: LocalAuthService
    admin_service: AdminService = field(default=None)  # type: ignore[assignment]
    login_throttle: LoginThrottle = field(default_factory=LoginThrottle)


def make_meeting(meetings_root: Path, meeting_id: str = MEETING_ID) -> None:
    d = meetings_root / meeting_id
    d.mkdir(parents=True, exist_ok=True)
    card = dict(VALID_CARD)
    card["meeting_id"] = meeting_id
    (d / "meeting.json").write_text(json.dumps(card), encoding="utf-8")


def make_client(
    meetings_root: Path, runner: JobRunner | None = None
) -> tuple[TestClient, JobRunner, AdminService]:
    os.environ["MEETINGAGENT_API_TOKEN"] = TOKEN
    repo = AuthRepository(meetings_root / "_auth.db")
    repo.initialize()
    app = create_app()
    jr = runner or JobRunner()
    client = TestClient(app, raise_server_exceptions=False)
    svc = LocalAuthService(repo)
    admin_svc = AdminService(repo)
    app.state.asu_june_bot = FakeState(
        meetings_service=MeetingsService(meetings_root),
        job_runner=jr,
        local_auth_service=svc,
        admin_service=admin_svc,
    )
    return client, jr, admin_svc


def _login(
    client: TestClient, admin_svc: AdminService, email: str, password: str, roles: list[str]
) -> tuple[str, str]:
    """Create a user, log in, return (session_cookie, csrf_token)."""
    admin_svc.create_user(email=email, password=password, roles=roles, actor_id="system")
    resp = client.post("/auth/local/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.json()
    return resp.cookies["ma_session"], resp.json()["csrf_token"]


# ==================================================================
# GET /auth/csrf
# ==================================================================

def test_csrf_endpoint_returns_token_for_cookie_user(tmp_path: Path) -> None:
    client, _, admin_svc = make_client(tmp_path)
    cookie, csrf = _login(client, admin_svc, "v@example.com", "viewerpass1", ["viewer"])
    resp = client.get("/auth/csrf", cookies={"ma_session": cookie})
    assert resp.status_code == 200
    assert resp.json()["csrf_token"] == csrf


def test_csrf_endpoint_does_not_leak_session_or_hash(tmp_path: Path) -> None:
    client, _, admin_svc = make_client(tmp_path)
    cookie, _ = _login(client, admin_svc, "v2@example.com", "viewerpass1", ["viewer"])
    resp = client.get("/auth/csrf", cookies={"ma_session": cookie})
    body = resp.json()
    assert set(body.keys()) == {"csrf_token"}
    assert isinstance(body["csrf_token"], str)
    assert body["csrf_token"]


def test_csrf_endpoint_unauthenticated_returns_401(tmp_path: Path) -> None:
    client, _, _ = make_client(tmp_path)
    resp = client.get("/auth/csrf")
    assert resp.status_code == 401


def test_csrf_endpoint_403_when_csrf_cookie_missing(tmp_path: Path) -> None:
    client, _, admin_svc = make_client(tmp_path)
    cookie, _ = _login(client, admin_svc, "v3@example.com", "viewerpass1", ["viewer"])
    # Valid session cookie but no CSRF cookie sent → 403.
    fresh = TestClient(client.app, raise_server_exceptions=False)
    resp = fresh.get("/auth/csrf", cookies={"ma_session": cookie})
    assert resp.status_code == 403


def test_csrf_endpoint_does_not_create_session(tmp_path: Path) -> None:
    client, _, admin_svc = make_client(tmp_path)
    cookie, _ = _login(client, admin_svc, "v4@example.com", "viewerpass1", ["viewer"])
    resp = client.get("/auth/csrf", cookies={"ma_session": cookie})
    # No Set-Cookie issued by this endpoint.
    assert "set-cookie" not in {k.lower() for k in resp.headers.keys()}


# ==================================================================
# GET /meetings/{id}/jobs/stages
# ==================================================================

def test_stages_requires_auth(tmp_path: Path) -> None:
    make_meeting(tmp_path)
    client, _, _ = make_client(tmp_path)
    resp = client.get(f"/meetings/{MEETING_ID}/jobs/stages")
    assert resp.status_code == 401


def test_stages_returns_all_runnable_stages(tmp_path: Path) -> None:
    make_meeting(tmp_path)
    client, _, _ = make_client(tmp_path)
    resp = client.get(f"/meetings/{MEETING_ID}/jobs/stages", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["meeting_id"] == MEETING_ID
    stage_names = [s["stage"] for s in body["stages"]]
    expected = [
        "extract_audio", "transcribe", "diarize", "merge",
        "chunk", "enrich", "index", "analyze",
    ]
    assert stage_names == expected, "stages must be returned in pipeline order"
    for s in body["stages"]:
        assert s["start_permission"] == "jobs.start"
        assert s["cancel_permission"] == "jobs.cancel"
        assert "label" in s and "description" in s
        assert "order" in s


def test_stages_no_filesystem_paths_in_response(tmp_path: Path) -> None:
    make_meeting(tmp_path)
    client, _, _ = make_client(tmp_path)
    resp = client.get(f"/meetings/{MEETING_ID}/jobs/stages", headers=AUTH)
    text = resp.text
    # No script paths, absolute paths, or .py references leak.
    assert ".py" not in text
    assert "/scripts/" not in text
    assert str(tmp_path) not in text


def test_stages_unknown_meeting_returns_404(tmp_path: Path) -> None:
    client, _, _ = make_client(tmp_path)
    resp = client.get("/meetings/2099-01-01__gone/jobs/stages", headers=AUTH)
    assert resp.status_code == 404


def test_stages_viewer_can_read(tmp_path: Path) -> None:
    make_meeting(tmp_path)
    client, _, admin_svc = make_client(tmp_path)
    cookie, _ = _login(client, admin_svc, "viewer@example.com", "viewerpass1", ["viewer"])
    resp = client.get(
        f"/meetings/{MEETING_ID}/jobs/stages", cookies={"ma_session": cookie}
    )
    assert resp.status_code == 200


# ==================================================================
# CSRF + RBAC on job start/cancel (browser flow used by workspace)
# ==================================================================

def test_machine_bearer_starts_job_without_csrf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_meeting(tmp_path)
    client, _, _ = make_client(tmp_path)

    async def fake_subprocess(*args, stdout, stderr):
        from tests.asu_june_bot.api.test_jobs_api import _ImmediateProcess
        return _ImmediateProcess(returncode=0)

    import asu_june_bot.jobs.runner as runner_mod
    monkeypatch.setattr(runner_mod, "_create_subprocess", fake_subprocess)

    resp = client.post(f"/meetings/{MEETING_ID}/jobs/transcribe", headers=AUTH)
    assert resp.status_code == 202


def test_viewer_cannot_start_job(tmp_path: Path) -> None:
    make_meeting(tmp_path)
    client, _, admin_svc = make_client(tmp_path)
    cookie, csrf = _login(client, admin_svc, "viewer5@example.com", "viewerpass1", ["viewer"])
    resp = client.post(
        f"/meetings/{MEETING_ID}/jobs/transcribe",
        cookies={"ma_session": cookie},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 403


def test_viewer_cannot_cancel_job(tmp_path: Path) -> None:
    make_meeting(tmp_path)
    client, _, admin_svc = make_client(tmp_path)
    cookie, csrf = _login(client, admin_svc, "viewer6@example.com", "viewerpass1", ["viewer"])
    resp = client.post(
        f"/meetings/{MEETING_ID}/jobs/some-job-id/cancel",
        cookies={"ma_session": cookie},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 403


def test_editor_cookie_start_without_csrf_returns_403(tmp_path: Path) -> None:
    make_meeting(tmp_path)
    client, _, admin_svc = make_client(tmp_path)
    cookie, _ = _login(client, admin_svc, "editor3@example.com", "editorpass1", ["editor"])
    resp = client.post(
        f"/meetings/{MEETING_ID}/jobs/transcribe",
        cookies={"ma_session": cookie},
        # no X-CSRF-Token
    )
    assert resp.status_code == 403


def test_editor_cookie_start_with_invalid_csrf_returns_403(tmp_path: Path) -> None:
    make_meeting(tmp_path)
    client, _, admin_svc = make_client(tmp_path)
    cookie, _ = _login(client, admin_svc, "editor4@example.com", "editorpass1", ["editor"])
    resp = client.post(
        f"/meetings/{MEETING_ID}/jobs/transcribe",
        cookies={"ma_session": cookie},
        headers={"X-CSRF-Token": "wrong-token"},
    )
    assert resp.status_code == 403


def test_editor_cookie_start_with_valid_csrf_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_meeting(tmp_path)
    client, _, admin_svc = make_client(tmp_path)
    cookie, csrf = _login(client, admin_svc, "editor5@example.com", "editorpass1", ["editor"])

    async def fake_subprocess(*args, stdout, stderr):
        from tests.asu_june_bot.api.test_jobs_api import _ImmediateProcess
        return _ImmediateProcess(returncode=0)

    import asu_june_bot.jobs.runner as runner_mod
    monkeypatch.setattr(runner_mod, "_create_subprocess", fake_subprocess)

    resp = client.post(
        f"/meetings/{MEETING_ID}/jobs/transcribe",
        cookies={"ma_session": cookie},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 202


def test_csrf_token_from_endpoint_authorizes_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end browser flow: fetch CSRF via /auth/csrf, then start a job."""
    make_meeting(tmp_path)
    client, _, admin_svc = make_client(tmp_path)
    cookie, _ = _login(client, admin_svc, "editor6@example.com", "editorpass1", ["editor"])

    csrf_resp = client.get("/auth/csrf", cookies={"ma_session": cookie})
    assert csrf_resp.status_code == 200
    token = csrf_resp.json()["csrf_token"]

    async def fake_subprocess(*args, stdout, stderr):
        from tests.asu_june_bot.api.test_jobs_api import _ImmediateProcess
        return _ImmediateProcess(returncode=0)

    import asu_june_bot.jobs.runner as runner_mod
    monkeypatch.setattr(runner_mod, "_create_subprocess", fake_subprocess)

    resp = client.post(
        f"/meetings/{MEETING_ID}/jobs/transcribe",
        cookies={"ma_session": cookie},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 202


# ==================================================================
# Workspace UI wiring
# ==================================================================

def test_workspace_html_includes_pipeline_controls(tmp_path: Path) -> None:
    make_meeting(tmp_path)
    client, _, _ = make_client(tmp_path)
    resp = client.get(f"/meetings/{MEETING_ID}/workspace")
    assert resp.status_code == 200
    body = resp.text
    assert "jobs-stages" in body
    assert "jobs-refresh-btn" in body
    assert "Pipeline" in body


def test_workspace_js_references_csrf_header_and_endpoints(tmp_path: Path) -> None:
    make_meeting(tmp_path)
    client, _, _ = make_client(tmp_path)
    body = client.get(f"/meetings/{MEETING_ID}/workspace").text + load_ui_asset("workspace.js")
    assert "X-CSRF-Token" in body
    assert "/auth/csrf" in body
    assert "/jobs/stages" in body
    assert "startStage" in body
    assert "cancelActiveJob" in body


def test_workspace_js_no_unsafe_inline_job_interpolation(tmp_path: Path) -> None:
    """Dynamic job/stage values must be wired via addEventListener + dataset,
    not inline onclick string interpolation."""
    make_meeting(tmp_path)
    client, _, _ = make_client(tmp_path)
    body = client.get(f"/meetings/{MEETING_ID}/workspace").text + load_ui_asset("workspace.js")
    assert "onclick=\"startStage(" not in body
    assert "onclick=\"cancelActiveJob(" not in body
    assert "dataset.stage" in body
    assert "addEventListener" in body


def test_workspace_html_has_no_inline_event_handlers(tmp_path: Path) -> None:
    """No HTML element may carry inline on* handlers — required for strict CSP."""
    import re as _re
    make_meeting(tmp_path)
    client, _, _ = make_client(tmp_path)
    body = client.get(f"/meetings/{MEETING_ID}/workspace").text + load_ui_asset("workspace.js")
    matches = _re.findall(r'\son[a-z]+\s*=\s*"', body)
    assert matches == [], f"found inline handlers: {matches}"


def test_workspace_transcript_uses_dataset_not_inline_onclick(tmp_path: Path) -> None:
    """Transcript segments must seek via dataset.startSec + addEventListener."""
    make_meeting(tmp_path)
    client, _, _ = make_client(tmp_path)
    body = client.get(f"/meetings/{MEETING_ID}/workspace").text + load_ui_asset("workspace.js")
    assert 'onclick="seekTo(' not in body
    # Segments are built via DOM API — startSec is set through dataset property in JS.
    assert "dataset.startSec" in body
    assert "addEventListener" in body


def test_workspace_static_controls_wired_via_listeners(tmp_path: Path) -> None:
    """Refresh, filter and close-artifact controls are wired in JS, not inline."""
    make_meeting(tmp_path)
    client, _, _ = make_client(tmp_path)
    body = client.get(f"/meetings/{MEETING_ID}/workspace").text + load_ui_asset("workspace.js")
    # Elements carry ids that the init block binds listeners to.
    assert 'id="hdr-refresh-btn"' in body
    assert 'id="seg-filter"' in body
    assert 'id="close-artifact-btn"' in body
    for fragment in (
        'getElementById("hdr-refresh-btn")',
        'getElementById("seg-filter")',
        'getElementById("close-artifact-btn")',
    ):
        assert fragment in body, f"missing listener wiring: {fragment}"


def test_workspace_js_does_not_persist_csrf_token(tmp_path: Path) -> None:
    """CSRF token must stay in JS memory — no localStorage/sessionStorage."""
    make_meeting(tmp_path)
    client, _, _ = make_client(tmp_path)
    body = client.get(f"/meetings/{MEETING_ID}/workspace").text + load_ui_asset("workspace.js")
    assert "localStorage" not in body
    assert "sessionStorage" not in body


def test_workspace_html_has_error_container(tmp_path: Path) -> None:
    make_meeting(tmp_path)
    client, _, _ = make_client(tmp_path)
    body = client.get(f"/meetings/{MEETING_ID}/workspace").text + load_ui_asset("workspace.js")
    assert "jobs-error" in body
    assert "auth-overlay" in body


def test_workspace_transcript_and_artifacts_use_dom_api_not_innerhtml(tmp_path: Path) -> None:
    """loadTranscript, loadArtifacts, and viewArtifact must not set innerHTML with
    runtime-data template literals — they must use createElement/textContent/replaceChildren."""
    make_meeting(tmp_path)
    client, _, _ = make_client(tmp_path)
    body = client.get(f"/meetings/{MEETING_ID}/workspace").text + load_ui_asset("workspace.js")
    # DOM API idioms must be present.
    assert "replaceChildren" in body
    assert "createElement" in body
    assert "textContent" in body
    # Dynamic runtime data must NOT be interpolated into innerHTML.
    import re
    # innerHTML assignments that interpolate variables (${...}) are violations.
    bad_patterns = [
        r'list\.innerHTML\s*=\s*_segments',
        r'panel\.innerHTML\s*=\s*`[^`]*\$\{',
        r'viewer\.innerHTML\s*=\s*`[^`]*\$\{',
    ]
    for pat in bad_patterns:
        assert not re.search(pat, body), f"dynamic innerHTML found: {pat}"
