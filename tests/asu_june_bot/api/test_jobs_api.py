from __future__ import annotations

import json
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
from asu_june_bot.auth.models import Principal  # noqa: E402
from asu_june_bot.auth.permissions import EDITOR_PERMISSIONS, ROLE_PERMISSIONS, VIEWER_PERMISSIONS  # noqa: E402
from asu_june_bot.auth.repository import AuthRepository  # noqa: E402
from asu_june_bot.auth.service import AdminService, LocalAuthService  # noqa: E402
from asu_june_bot.jobs.runner import JobRunner, JobState  # noqa: E402
from asu_june_bot.auth.throttle import LoginThrottle  # noqa: E402
from asu_june_bot.meetings.service import MeetingsService  # noqa: E402

TOKEN = "test-job-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
MEETING_ID = "2026-01-10__test-meeting"

VALID_CARD = {
    "schema_version": 1,
    "meeting_id": MEETING_ID,
    "title": "Test Meeting",
    "date": "2026-01-10",
    "processing_status": "new",
    "participants": [],
    "source": {"kind": "offline_record"},
    "artifacts": {},
    "classification": {},
    "links": {},
    "retention": {"policy": "default"},
    "rag": {"index_policy": "structured_artifacts_and_final_transcript"},
    "created_at": "2026-01-10T10:00:00+00:00",
    "updated_at": "2026-01-10T10:00:00+00:00",
}


# ------------------------------------------------------------------
# Fake async process helpers
# ------------------------------------------------------------------

class _HangingProcess:
    """Simulate a long-running subprocess that never completes until terminate()."""

    def __init__(self) -> None:
        self.returncode: int | None = None
        self.pid = 99999
        self._done: bool = False

    async def communicate(self) -> tuple[bytes, bytes]:
        import asyncio
        # Block until explicitly terminated via terminate()
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self._fut = fut
        await fut
        return b"", b""

    def terminate(self) -> None:
        self.returncode = -15
        if hasattr(self, "_fut") and not self._fut.done():
            self._fut.get_loop().call_soon_threadsafe(self._fut.set_result, None)


class _ImmediateProcess:
    """Simulate a subprocess that exits immediately."""

    def __init__(self, returncode: int = 0, stderr: bytes = b"") -> None:
        self.returncode = returncode
        self.pid = 11111
        self._stderr = stderr

    async def communicate(self) -> tuple[bytes, bytes]:
        return b"", self._stderr

    def terminate(self) -> None:
        self.returncode = -15


# ------------------------------------------------------------------
# Test fixtures
# ------------------------------------------------------------------

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
    meetings_root: Path,
    runner: JobRunner | None = None,
) -> tuple[TestClient, JobRunner]:
    import os
    os.environ["MEETINGAGENT_API_TOKEN"] = TOKEN
    repo = AuthRepository(meetings_root / "_auth.db")
    repo.initialize()
    app = create_app()
    jr = runner or JobRunner()
    client = TestClient(app, raise_server_exceptions=False)
    svc = LocalAuthService(repo)
    app.state.asu_june_bot = FakeState(
        meetings_service=MeetingsService(meetings_root),
        job_runner=jr,
        local_auth_service=svc,
        admin_service=AdminService(repo),
    )
    return client, jr


def _cookie_session(
    client: TestClient,
    admin_svc: "AdminService",
    email: str,
    password: str,
    roles: list[str],
) -> tuple[str, str]:
    """Create a user with given roles, log in, return (session_cookie, csrf_token)."""
    admin_svc.create_user(
        email=email, password=password, roles=roles, actor_id="system"
    )
    resp = client.post("/auth/local/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.json()
    return resp.cookies["ma_session"], resp.json()["csrf_token"]


# ------------------------------------------------------------------
# Auth
# ------------------------------------------------------------------

def test_no_auth_returns_401(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    make_meeting(tmp_path)
    client, _ = make_client(tmp_path)
    resp = client.post(f"/meetings/{MEETING_ID}/jobs/transcribe")
    assert resp.status_code == 401


def test_bad_token_returns_401(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    make_meeting(tmp_path)
    client, _ = make_client(tmp_path)
    resp = client.post(
        f"/meetings/{MEETING_ID}/jobs/transcribe",
        headers={"Authorization": "Bearer wrong"},
    )
    assert resp.status_code == 401


# ------------------------------------------------------------------
# Input validation
# ------------------------------------------------------------------

def test_unknown_stage_returns_422(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    make_meeting(tmp_path)
    client, _ = make_client(tmp_path)
    resp = client.post(f"/meetings/{MEETING_ID}/jobs/nonexistent", headers=AUTH)
    assert resp.status_code == 422


def test_missing_meeting_returns_404(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    client, _ = make_client(tmp_path)
    resp = client.post("/meetings/2099-01-01__gone/jobs/transcribe", headers=AUTH)
    assert resp.status_code == 404


# ------------------------------------------------------------------
# POST /jobs/{stage}  — happy path
# ------------------------------------------------------------------

def test_start_job_returns_202_with_job_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    make_meeting(tmp_path)
    client, _ = make_client(tmp_path)

    calls: list = []

    async def fake_subprocess(*args, stdout, stderr):
        calls.append(args)
        return _ImmediateProcess(returncode=0)

    import asu_june_bot.jobs.runner as runner_mod
    monkeypatch.setattr(runner_mod, "_create_subprocess", fake_subprocess)

    resp = client.post(f"/meetings/{MEETING_ID}/jobs/transcribe", headers=AUTH)
    assert resp.status_code == 202
    body = resp.json()
    assert "job_id" in body
    assert body["meeting_id"] == MEETING_ID
    assert body["stage"] == "transcribe"
    assert body["status"] in ("starting", "running")


# ------------------------------------------------------------------
# Concurrency
# ------------------------------------------------------------------

def test_second_job_while_first_running_returns_409(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    make_meeting(tmp_path)
    client, runner = make_client(tmp_path)

    call_count = 0

    async def fake_subprocess(*args, stdout, stderr):
        nonlocal call_count
        call_count += 1
        if "--dry-run" in args:
            return _ImmediateProcess(returncode=0)
        return _HangingProcess()  # real job hangs

    import asu_june_bot.jobs.runner as runner_mod
    monkeypatch.setattr(runner_mod, "_create_subprocess", fake_subprocess)

    resp1 = client.post(f"/meetings/{MEETING_ID}/jobs/transcribe", headers=AUTH)
    assert resp1.status_code == 202

    resp2 = client.post(f"/meetings/{MEETING_ID}/jobs/transcribe", headers=AUTH)
    assert resp2.status_code == 409


# ------------------------------------------------------------------
# GET job status while running
# ------------------------------------------------------------------

def test_get_job_status_while_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    make_meeting(tmp_path)
    client, runner = make_client(tmp_path)

    async def fake_subprocess(*args, stdout, stderr):
        if "--dry-run" in args:
            return _ImmediateProcess(returncode=0)
        return _HangingProcess()

    import asu_june_bot.jobs.runner as runner_mod
    monkeypatch.setattr(runner_mod, "_create_subprocess", fake_subprocess)

    resp = client.post(f"/meetings/{MEETING_ID}/jobs/transcribe", headers=AUTH)
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    resp2 = client.get(f"/meetings/{MEETING_ID}/jobs/{job_id}", headers=AUTH)
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "running"


# ------------------------------------------------------------------
# GET completed job from history
# ------------------------------------------------------------------

def test_get_completed_job_from_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    make_meeting(tmp_path)
    runner = JobRunner()
    completed = JobState(
        job_id="done-job-001",
        meeting_id=MEETING_ID,
        stage="transcribe",
        status="completed",
        started_at="2026-01-10T10:00:00+00:00",
        finished_at="2026-01-10T10:05:00+00:00",
        exit_code=0,
        stderr_lines=["processing done"],
    )
    runner.history.append(completed)
    client, _ = make_client(tmp_path, runner=runner)

    resp = client.get(f"/meetings/{MEETING_ID}/jobs/done-job-001", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["exit_code"] == 0
    assert body["status"] == "completed"
    assert "processing done" in body["stderr_tail"]


# ------------------------------------------------------------------
# Cancel
# ------------------------------------------------------------------

def test_cancel_running_job_returns_200(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    make_meeting(tmp_path)
    client, runner = make_client(tmp_path)

    hanging = _HangingProcess()

    async def fake_subprocess(*args, stdout, stderr):
        if "--dry-run" in args:
            return _ImmediateProcess(returncode=0)
        return hanging

    import asu_june_bot.jobs.runner as runner_mod
    monkeypatch.setattr(runner_mod, "_create_subprocess", fake_subprocess)

    resp = client.post(f"/meetings/{MEETING_ID}/jobs/transcribe", headers=AUTH)
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    resp2 = client.post(
        f"/meetings/{MEETING_ID}/jobs/{job_id}/cancel", headers=AUTH
    )
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "cancelled"


def test_cancel_finished_job_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    make_meeting(tmp_path)
    runner = JobRunner()
    done = JobState(
        job_id="done-002",
        meeting_id=MEETING_ID,
        stage="diarize",
        status="completed",
        started_at="2026-01-10T10:00:00+00:00",
        exit_code=0,
    )
    runner.history.append(done)
    client, _ = make_client(tmp_path, runner=runner)

    resp = client.post(
        f"/meetings/{MEETING_ID}/jobs/done-002/cancel", headers=AUTH
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


# ------------------------------------------------------------------
# Preflight failure
# ------------------------------------------------------------------

def test_preflight_fail_returns_422_process_not_started(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    make_meeting(tmp_path)
    client, runner = make_client(tmp_path)

    real_calls: list = []

    async def fake_subprocess(*args, stdout, stderr):
        real_calls.append(args)
        if "--dry-run" in args:
            return _ImmediateProcess(returncode=1, stderr=b"model not found")
        return _ImmediateProcess(returncode=0)

    import asu_june_bot.jobs.runner as runner_mod
    monkeypatch.setattr(runner_mod, "_create_subprocess", fake_subprocess)

    resp = client.post(f"/meetings/{MEETING_ID}/jobs/transcribe", headers=AUTH)
    assert resp.status_code == 422
    assert "Preflight failed" in resp.json()["detail"]
    # Only the dry-run call should have been made
    assert all("--dry-run" in call for call in real_calls)
    # Runner slot freed
    assert runner.active_job is None


# ------------------------------------------------------------------
# GET /jobs/active
# ------------------------------------------------------------------

def test_get_active_returns_empty_when_idle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    client, _ = make_client(tmp_path)
    resp = client.get("/jobs/active", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json() == {}


def test_get_active_returns_cancelled_job_while_process_alive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After cancel, /jobs/active still shows the job (slot held) until process exits."""
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    make_meeting(tmp_path)
    client, runner = make_client(tmp_path)

    async def fake_subprocess(*args, stdout, stderr):
        if "--dry-run" in args:
            return _ImmediateProcess(returncode=0)
        return _HangingProcess()

    import asu_june_bot.jobs.runner as runner_mod
    monkeypatch.setattr(runner_mod, "_create_subprocess", fake_subprocess)

    resp = client.post(f"/meetings/{MEETING_ID}/jobs/transcribe", headers=AUTH)
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    client.post(f"/meetings/{MEETING_ID}/jobs/{job_id}/cancel", headers=AUTH)

    # System still busy — /jobs/active must show the cancelled job
    resp2 = client.get("/jobs/active", headers=AUTH)
    assert resp2.status_code == 200
    body = resp2.json()
    assert body["job_id"] == job_id
    assert body["status"] == "cancelled"
    assert body["is_active"] is True

    # Slot still held — second start is 409
    resp3 = client.post(f"/meetings/{MEETING_ID}/jobs/transcribe", headers=AUTH)
    assert resp3.status_code == 409


def test_get_active_returns_running_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    make_meeting(tmp_path)
    client, runner = make_client(tmp_path)

    async def fake_subprocess(*args, stdout, stderr):
        if "--dry-run" in args:
            return _ImmediateProcess(returncode=0)
        return _HangingProcess()

    import asu_june_bot.jobs.runner as runner_mod
    monkeypatch.setattr(runner_mod, "_create_subprocess", fake_subprocess)

    client.post(f"/meetings/{MEETING_ID}/jobs/transcribe", headers=AUTH)

    resp = client.get("/jobs/active", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"


# ------------------------------------------------------------------
# merge stage — no dry-run preflight (static check)
# ------------------------------------------------------------------

def test_merge_preflight_missing_segments_returns_422(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """merge stage has no --dry-run; preflight checks segments.jsonl exists."""
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    make_meeting(tmp_path)  # no segments.jsonl
    client, _ = make_client(tmp_path)

    # merge does NOT call _create_subprocess for preflight
    async def fake_subprocess(*args, stdout, stderr):
        return _ImmediateProcess(returncode=0)

    import asu_june_bot.jobs.runner as runner_mod
    monkeypatch.setattr(runner_mod, "_create_subprocess", fake_subprocess)

    resp = client.post(f"/meetings/{MEETING_ID}/jobs/merge", headers=AUTH)
    assert resp.status_code == 422
    assert "segments" in resp.json()["detail"].lower()


# ------------------------------------------------------------------
# Cancel meeting_id guard
# ------------------------------------------------------------------

def test_cancel_wrong_meeting_id_returns_404_job_still_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """cancel via wrong meeting_id must 404 without touching the job."""
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    make_meeting(tmp_path)
    client, runner = make_client(tmp_path)

    async def fake_subprocess(*args, stdout, stderr):
        if "--dry-run" in args:
            return _ImmediateProcess(returncode=0)
        return _HangingProcess()

    import asu_june_bot.jobs.runner as runner_mod
    monkeypatch.setattr(runner_mod, "_create_subprocess", fake_subprocess)

    resp = client.post(f"/meetings/{MEETING_ID}/jobs/transcribe", headers=AUTH)
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    resp2 = client.post(
        f"/meetings/2099-01-01__other/jobs/{job_id}/cancel", headers=AUTH
    )
    assert resp2.status_code == 404
    # job must still be running
    assert runner.active_job is not None
    assert runner.active_job.status == "running"


def test_cancel_holds_slot_until_process_exits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After cancel, active_job slot is held until _monitor sees process exit."""
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    make_meeting(tmp_path)
    client, runner = make_client(tmp_path)

    hanging = _HangingProcess()

    async def fake_subprocess(*args, stdout, stderr):
        if "--dry-run" in args:
            return _ImmediateProcess(returncode=0)
        return hanging

    import asu_june_bot.jobs.runner as runner_mod
    monkeypatch.setattr(runner_mod, "_create_subprocess", fake_subprocess)

    resp = client.post(f"/meetings/{MEETING_ID}/jobs/transcribe", headers=AUTH)
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    resp2 = client.post(
        f"/meetings/{MEETING_ID}/jobs/{job_id}/cancel", headers=AUTH
    )
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "cancelled"

    # Slot still occupied — second start must be 409
    resp3 = client.post(f"/meetings/{MEETING_ID}/jobs/transcribe", headers=AUTH)
    assert resp3.status_code == 409


# ------------------------------------------------------------------
# Jobs RBAC: cookie-user permission enforcement
# ------------------------------------------------------------------

def _rbac_client(tmp_path: Path, token: str = TOKEN) -> tuple[TestClient, JobRunner, AdminService]:
    import os
    os.environ["MEETINGAGENT_API_TOKEN"] = token
    repo = AuthRepository(tmp_path / "_auth.db")
    repo.initialize()
    app = create_app()
    jr = JobRunner()
    client = TestClient(app, raise_server_exceptions=False)
    admin_svc = AdminService(repo)
    app.state.asu_june_bot = FakeState(
        meetings_service=MeetingsService(tmp_path),
        job_runner=jr,
        local_auth_service=LocalAuthService(repo),
        admin_service=admin_svc,
    )
    make_meeting(tmp_path)
    return client, jr, admin_svc


def test_viewer_cannot_start_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Viewer role has jobs.read but not jobs.start — start returns 403."""
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    client, _, admin_svc = _rbac_client(tmp_path)
    cookie, csrf = _cookie_session(client, admin_svc, "viewer1@example.com", "viewerpass1", ["viewer"])
    resp = client.post(
        f"/meetings/{MEETING_ID}/jobs/transcribe",
        cookies={"ma_session": cookie},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 403


def test_viewer_cannot_cancel_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Viewer role has jobs.read but not jobs.cancel — cancel returns 403."""
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    client, runner, admin_svc = _rbac_client(tmp_path)
    done = JobState(
        job_id="done-rbac-001",
        meeting_id=MEETING_ID,
        stage="transcribe",
        status="running",
        started_at="2026-01-10T10:00:00+00:00",
    )
    runner.history.append(done)
    cookie, csrf = _cookie_session(client, admin_svc, "viewer2@example.com", "viewerpass2", ["viewer"])
    resp = client.post(
        f"/meetings/{MEETING_ID}/jobs/done-rbac-001/cancel",
        cookies={"ma_session": cookie},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 403


def test_viewer_can_read_job_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Viewer has jobs.read — job status GET returns 200."""
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    client, runner, admin_svc = _rbac_client(tmp_path)
    done = JobState(
        job_id="done-rbac-002",
        meeting_id=MEETING_ID,
        stage="transcribe",
        status="completed",
        started_at="2026-01-10T10:00:00+00:00",
        exit_code=0,
    )
    runner.history.append(done)
    cookie, _ = _cookie_session(client, admin_svc, "viewer3@example.com", "viewerpass3", ["viewer"])
    resp = client.get(
        f"/meetings/{MEETING_ID}/jobs/done-rbac-002",
        cookies={"ma_session": cookie},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


def test_editor_can_start_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Editor role has jobs.start — start returns 202."""
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    client, _, admin_svc = _rbac_client(tmp_path)

    async def fake_subprocess(*args, stdout, stderr):
        return _ImmediateProcess(returncode=0)

    import asu_june_bot.jobs.runner as runner_mod
    monkeypatch.setattr(runner_mod, "_create_subprocess", fake_subprocess)

    cookie, csrf = _cookie_session(client, admin_svc, "editor1@example.com", "editorpass1", ["editor"])
    resp = client.post(
        f"/meetings/{MEETING_ID}/jobs/transcribe",
        cookies={"ma_session": cookie},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 202


def test_editor_can_cancel_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Editor role has jobs.cancel — cancel returns 200."""
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    client, runner, admin_svc = _rbac_client(tmp_path)

    hanging = _HangingProcess()

    async def fake_subprocess(*args, stdout, stderr):
        if "--dry-run" in args:
            return _ImmediateProcess(returncode=0)
        return hanging

    import asu_june_bot.jobs.runner as runner_mod
    monkeypatch.setattr(runner_mod, "_create_subprocess", fake_subprocess)

    # Start via machine token
    start_resp = client.post(f"/meetings/{MEETING_ID}/jobs/transcribe", headers=AUTH)
    assert start_resp.status_code == 202
    job_id = start_resp.json()["job_id"]

    # Cancel via editor cookie
    cookie, csrf = _cookie_session(client, admin_svc, "editor2@example.com", "editorpass2", ["editor"])
    resp = client.post(
        f"/meetings/{MEETING_ID}/jobs/{job_id}/cancel",
        cookies={"ma_session": cookie},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


def test_machine_token_can_start_and_read_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Machine token retains jobs.start and jobs.read permissions."""
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    client, runner, _ = _rbac_client(tmp_path)

    async def fake_subprocess(*args, stdout, stderr):
        return _ImmediateProcess(returncode=0)

    import asu_june_bot.jobs.runner as runner_mod
    monkeypatch.setattr(runner_mod, "_create_subprocess", fake_subprocess)

    resp = client.post(f"/meetings/{MEETING_ID}/jobs/transcribe", headers=AUTH)
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    resp2 = client.get(f"/meetings/{MEETING_ID}/jobs/{job_id}", headers=AUTH)
    assert resp2.status_code == 200


def test_start_job_requires_csrf_for_cookie_user(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cookie-authenticated editor without CSRF header gets 403."""
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    client, _, admin_svc = _rbac_client(tmp_path)
    cookie, _ = _cookie_session(client, admin_svc, "editor3@example.com", "editorpass3", ["editor"])
    resp = client.post(
        f"/meetings/{MEETING_ID}/jobs/transcribe",
        cookies={"ma_session": cookie},
        # no X-CSRF-Token
    )
    assert resp.status_code == 403


# ------------------------------------------------------------------
# Least-privilege regression: upload-only role cannot start/cancel jobs
# ------------------------------------------------------------------

def _make_upload_only_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[TestClient, JobRunner, AdminService]:
    """Set up a client where the only cookie user has meetings.upload but NOT jobs.start/cancel."""
    import asu_june_bot.auth.models as models_mod
    import asu_june_bot.auth.permissions as perms_mod
    import asu_june_bot.auth.repository as repo_mod
    import asu_june_bot.auth.service as svc_mod

    upload_only_perms = VIEWER_PERMISSIONS | frozenset({"meetings.upload"})
    patched_perms = {**ROLE_PERMISSIONS, "upload_only": upload_only_perms}
    patched_builtin = frozenset(patched_perms)

    # permissions_for_roles() reads ROLE_PERMISSIONS from the permissions module at call time
    monkeypatch.setattr(perms_mod, "ROLE_PERMISSIONS", patched_perms)
    # BUILTIN_ROLES is imported by name into each module — patch every copy
    monkeypatch.setattr(perms_mod, "BUILTIN_ROLES", patched_builtin)
    monkeypatch.setattr(models_mod, "BUILTIN_ROLES", patched_builtin)
    monkeypatch.setattr(repo_mod, "BUILTIN_ROLES", patched_builtin)
    monkeypatch.setattr(svc_mod, "BUILTIN_ROLES", patched_builtin)

    return _rbac_client(tmp_path)


def test_upload_only_role_cannot_start_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """meetings.upload without jobs.start must not allow starting a job (regression)."""
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    client, _, admin_svc = _make_upload_only_client(tmp_path, monkeypatch)
    cookie, csrf = _cookie_session(
        client, admin_svc, "uploader@example.com", "uploaderpass1", ["upload_only"]
    )
    resp = client.post(
        f"/meetings/{MEETING_ID}/jobs/transcribe",
        cookies={"ma_session": cookie},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 403


def test_upload_only_role_cannot_cancel_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """meetings.upload without jobs.cancel must not allow cancelling a job (regression)."""
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    client, runner, admin_svc = _make_upload_only_client(tmp_path, monkeypatch)
    done = JobState(
        job_id="done-upload-001",
        meeting_id=MEETING_ID,
        stage="transcribe",
        status="running",
        started_at="2026-01-10T10:00:00+00:00",
    )
    runner.history.append(done)
    cookie, csrf = _cookie_session(
        client, admin_svc, "uploader2@example.com", "uploaderpass2", ["upload_only"]
    )
    resp = client.post(
        f"/meetings/{MEETING_ID}/jobs/done-upload-001/cancel",
        cookies={"ma_session": cookie},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 403
