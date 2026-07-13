from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from asu_june_bot.api.app import create_app
from asu_june_bot.auth.repository import AuthRepository
from asu_june_bot.auth.service import AdminService, LocalAuthService
from asu_june_bot.auth.throttle import LoginThrottle
from asu_june_bot.meetings.service import MeetingsService


TOKEN = "live-refinement-api-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
MEETING_ID = "2026-07-13__refinement-api"
NOW = "2026-07-13T12:00:00+03:00"


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _meeting(root: Path) -> Path:
    meeting_dir = root / MEETING_ID
    audio = "source/live_audio.MIC.wav"
    segments = "transcript/live/live_segments.MIC.jsonl"
    report = "transcript/live/live_report.MIC.json"
    _write(meeting_dir / audio, "pcm")
    _write(meeting_dir / segments, '{"text":"draft"}\n')
    _write(
        meeting_dir / report,
        json.dumps(
            {
                "engine": "vosk",
                "model": "vosk-small-ru",
                "duration_seconds": 10,
                "elapsed_seconds": 8,
                "segments_count": 2,
                "chars_count": 20,
                "started_at": NOW,
                "finished_at": NOW,
            }
        ),
    )
    card = {
        "schema_version": 1,
        "meeting_id": MEETING_ID,
        "title": "Refinement API",
        "date": "2026-07-13",
        "processing_status": "processing",
        "participants": [],
        "source": {
            "kind": "live_session",
            "media_files": [{"path": audio, "media_type": "audio"}],
            "audio_tracks": ["MIC"],
        },
        "artifacts": {
            "live_audio_mic": audio,
            "live_segments_mic": segments,
            "live_report_mic": report,
        },
        "classification": {},
        "links": {},
        "retention": {"policy": "default"},
        "rag": {
            "index_policy": "structured_artifacts_and_final_transcript",
            "no_index_artifacts": [audio, segments, report],
        },
        "created_at": NOW,
        "updated_at": NOW,
    }
    _write(meeting_dir / "meeting.json", json.dumps(card))
    return meeting_dir


class _FakeJob:
    meeting_id = MEETING_ID
    stage = "transcribe"
    status = "running"

    def as_dict(self) -> dict:
        return {
            "job_id": "job-refine-1",
            "meeting_id": MEETING_ID,
            "stage": "transcribe",
            "status": "running",
            "started_at": NOW,
            "finished_at": None,
            "exit_code": None,
            "recovery_status": None,
            "stderr_tail": [],
            "operation": {"kind": "live_refinement", "source": "MIC"},
        }


class _FakeRunner:
    def __init__(self) -> None:
        self.active_job = None
        self.submitted: dict | None = None

    def get_active(self):
        return self.active_job

    async def submit(self, **kwargs):
        self.submitted = kwargs
        job = _FakeJob()
        self.active_job = job
        return job


class _FakeLiveService:
    def __init__(self) -> None:
        self.current = None

    def active(self, _meeting_id: str, *, source=None):
        return self.current

    def shutdown(self) -> None:
        return None


@dataclass(slots=True)
class _State:
    meetings_service: MeetingsService
    job_runner: _FakeRunner
    live_session_service: _FakeLiveService
    local_auth_service: LocalAuthService
    admin_service: AdminService
    login_throttle: LoginThrottle = field(default_factory=LoginThrottle)
    trusted_proxy_cidrs: list[str] = field(default_factory=list)


@pytest.fixture
def api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    meetings_root = tmp_path / "meetings"
    meeting_dir = _meeting(meetings_root)
    repository = AuthRepository(tmp_path / "auth.db")
    repository.initialize()
    local_auth = LocalAuthService(repository)
    admin = AdminService(repository)
    runner = _FakeRunner()
    live = _FakeLiveService()
    app = create_app(config={})
    app.state.asu_june_bot = _State(
        meetings_service=MeetingsService(meetings_root),
        job_runner=runner,
        live_session_service=live,
        local_auth_service=local_auth,
        admin_service=admin,
    )
    client = TestClient(app, raise_server_exceptions=False)
    try:
        yield client, meeting_dir, runner, live, admin
    finally:
        client.close()


def _login(client: TestClient, admin: AdminService) -> str:
    admin.create_user(
        email="editor@example.test",
        password="StrongPassword!123",
        roles=["editor"],
        actor_id="system",
    )
    response = client.post(
        "/auth/local/login",
        json={"email": "editor@example.test", "password": "StrongPassword!123"},
    )
    assert response.status_code == 200
    return response.json()["csrf_token"]


def test_refinement_status_requires_authentication(api) -> None:
    client, *_ = api
    assert client.get(f"/meetings/{MEETING_ID}/live/refinement").status_code == 401


def test_refinement_status_exposes_safe_draft_metadata(api) -> None:
    client, *_ = api

    response = client.get(
        f"/meetings/{MEETING_ID}/live/refinement?source=MIC",
        headers=AUTH,
    )

    assert response.status_code == 200
    assert response.json()["state"] == "draft"
    assert response.json()["can_refine"] is True
    assert response.json()["live"]["engine"] == "vosk"
    assert "source/live" not in response.text
    assert "meetings" not in response.text.lower()


def test_refinement_post_passes_only_allowlisted_runner_options(api) -> None:
    client, _meeting_dir, runner, _live, _admin = api

    response = client.post(
        f"/meetings/{MEETING_ID}/live/refinement",
        headers=AUTH,
        json={"source": "MIC", "asr_engine": "gigaam"},
    )

    assert response.status_code == 202
    assert response.json()["state"] == "refining"
    assert response.json()["job"]["job_id"] == "job-refine-1"
    assert runner.submitted is not None
    assert runner.submitted["stage"] == "transcribe"
    assert runner.submitted["stage_options"] == {
        "asr_engine": "gigaam",
        "media_path": "source/live_audio.MIC.wav",
        "live_refinement_source": "MIC",
        "force": False,
        "resume": False,
    }
    status = client.get(
        f"/meetings/{MEETING_ID}/live/refinement?source=MIC",
        headers=AUTH,
    )
    assert status.json()["state"] == "refining"
    assert status.json()["job"]["job_id"] == "job-refine-1"


def test_browser_refinement_requires_csrf(api) -> None:
    client, _meeting_dir, _runner, _live, admin = api
    csrf = _login(client, admin)

    rejected = client.post(
        f"/meetings/{MEETING_ID}/live/refinement",
        json={"source": "MIC"},
    )
    accepted = client.post(
        f"/meetings/{MEETING_ID}/live/refinement",
        headers={"X-CSRF-Token": csrf},
        json={"source": "MIC"},
    )

    assert rejected.status_code == 403
    assert accepted.status_code == 202


def test_active_live_capture_blocks_refinement(api) -> None:
    client, _meeting_dir, runner, live, _admin = api
    live.current = {"session_id": "live-1", "is_active": True}

    response = client.post(
        f"/meetings/{MEETING_ID}/live/refinement",
        headers=AUTH,
        json={"source": "MIC"},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "live_session_active"
    assert runner.submitted is None


def test_missing_live_audio_fails_before_runner_submission(api) -> None:
    client, meeting_dir, runner, _live, _admin = api
    (meeting_dir / "source/live_audio.MIC.wav").unlink()

    response = client.post(
        f"/meetings/{MEETING_ID}/live/refinement",
        headers=AUTH,
        json={"source": "MIC"},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "live_audio_missing"
    assert runner.submitted is None


def test_failed_refinement_requires_resume(api) -> None:
    client, meeting_dir, runner, _live, _admin = api
    card_path = meeting_dir / "meeting.json"
    card = json.loads(card_path.read_text(encoding="utf-8"))
    card["live_refinements"] = {
        "MIC": {
            "source": "MIC",
            "state": "failed",
            "offline_engine": "faster-whisper",
            "offline_model": "large-v3-turbo",
            "started_at": NOW,
            "finished_at": NOW,
            "error_code": "refinement_interrupted",
        }
    }
    card_path.write_text(json.dumps(card), encoding="utf-8")

    rejected = client.post(
        f"/meetings/{MEETING_ID}/live/refinement",
        headers=AUTH,
        json={"source": "MIC"},
    )
    resumed = client.post(
        f"/meetings/{MEETING_ID}/live/refinement",
        headers=AUTH,
        json={"source": "MIC", "resume": True},
    )
    assert rejected.status_code == 409
    assert rejected.json()["detail"]["code"] == "refinement_resume_required"
    assert resumed.status_code == 202
    assert runner.submitted["stage_options"]["resume"] is True


def test_final_refinement_requires_explicit_force(api) -> None:
    client, meeting_dir, runner, _live, _admin = api
    card_path = meeting_dir / "meeting.json"
    card = json.loads(card_path.read_text(encoding="utf-8"))
    report_rel = "transcript/live/refinement.MIC.json"
    _write(
        meeting_dir / report_rel,
        json.dumps(
            {
                "schema_version": 1,
                "source": "MIC",
                "state": "final",
                "live": {"engine": "vosk"},
                "offline": {"engine": "faster-whisper"},
                "comparison": {},
                "created_at": NOW,
            }
        ),
    )
    card["artifacts"]["live_refinement_mic"] = report_rel
    card["rag"]["no_index_artifacts"].append(report_rel)
    card["live_refinements"] = {
        "MIC": {
            "source": "MIC",
            "state": "final",
            "offline_engine": "faster-whisper",
            "offline_model": "large-v3-turbo",
            "started_at": NOW,
            "finished_at": NOW,
            "report_artifact_key": "live_refinement_mic",
        }
    }
    card_path.write_text(json.dumps(card), encoding="utf-8")

    rejected = client.post(
        f"/meetings/{MEETING_ID}/live/refinement",
        headers=AUTH,
        json={"source": "MIC"},
    )
    accepted = client.post(
        f"/meetings/{MEETING_ID}/live/refinement",
        headers=AUTH,
        json={"source": "MIC", "force": True},
    )

    assert rejected.status_code == 409
    assert rejected.json()["detail"]["code"] == "refinement_already_final"
    assert accepted.status_code == 202
    assert runner.submitted["stage_options"]["force"] is True


def test_force_and_resume_are_rejected_together(api) -> None:
    client, *_ = api
    response = client.post(
        f"/meetings/{MEETING_ID}/live/refinement",
        headers=AUTH,
        json={"source": "MIC", "force": True, "resume": True},
    )
    assert response.status_code == 422
