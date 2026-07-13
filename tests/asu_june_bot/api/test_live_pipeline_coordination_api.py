from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from asu_june_bot.api.app import create_app
from asu_june_bot.auth.repository import AuthRepository
from asu_june_bot.auth.service import AdminService, LocalAuthService
from asu_june_bot.auth.throttle import LoginThrottle
from asu_june_bot.jobs.runner import JobRunner
from asu_june_bot.jobs.store import JobStore
from asu_june_bot.live_sessions import LiveSessionService, LiveSessionStore
from asu_june_bot.live_sessions.store import now_iso
from asu_june_bot.meeting_work import MeetingWorkCoordinator
from asu_june_bot.meetings.service import MeetingsService
from meeting_agent.live_transcription.audio_capture import AudioSourcePreflight

TOKEN = "coordination-api-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
MEETING_ID = "2026-07-13__coordination"


def _job_record() -> dict:
    return {
        "job_id": str(uuid.uuid4()),
        "meeting_id": MEETING_ID,
        "kind": "stage",
        "stage": "transcribe",
        "status": "starting",
        "started_at": now_iso(),
    }


def _live_record() -> dict:
    timestamp = now_iso()
    return {
        "session_id": str(uuid.uuid4()),
        "meeting_id": MEETING_ID,
        "source": "MIC",
        "status": "starting",
        "engine": "vosk",
        "model": "synthetic",
        "vad": "silero",
        "created_at": timestamp,
        "started_at": timestamp,
        "updated_at": timestamp,
        "finished_at": None,
        "last_event_id": 1,
        "events": [
            {
                "event_id": 1,
                "type": "status",
                "timestamp": timestamp,
                "status": "starting",
            }
        ],
        "warnings": [],
        "error": None,
        "artifact_keys": [],
    }


@dataclass(slots=True)
class _State:
    meetings_service: MeetingsService
    job_runner: JobRunner
    live_session_service: LiveSessionService
    local_auth_service: LocalAuthService
    admin_service: AdminService
    login_throttle: LoginThrottle = field(default_factory=LoginThrottle)
    trusted_proxy_cidrs: list[str] = field(default_factory=list)


def _source_preflight(source: str, **_kwargs) -> AudioSourcePreflight:
    return AudioSourcePreflight(
        source=source,
        available=True,
        device_available=True,
        capture_supported=True,
    )


def _write_meeting(root: Path) -> None:
    meeting_dir = root / MEETING_ID
    meeting_dir.mkdir(parents=True)
    (meeting_dir / "meeting.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "meeting_id": MEETING_ID,
                "title": "Coordination API",
                "processing_status": "new",
                "source": {"kind": "live_session"},
                "artifacts": {},
                "rag": {
                    "index_policy": "structured_artifacts_and_final_transcript"
                },
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture
def coordination_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    meetings_root = tmp_path / "meetings"
    _write_meeting(meetings_root)
    model_path = tmp_path / "model"
    for relative in ("am/final.mdl", "conf/model.conf", "graph/HCLG.fst"):
        target = model_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()

    job_store = JobStore(tmp_path / "runtime" / "jobs.json")
    live_store = LiveSessionStore(
        tmp_path / "runtime" / "live.json",
        active_sessions_max=2,
    )
    coordinator = MeetingWorkCoordinator(
        tmp_path / "runtime" / "meeting_work.lock",
        job_store=job_store,
        live_store=live_store,
    )
    runner = JobRunner(
        meetings_root=meetings_root,
        store=job_store,
        coordinator=coordinator,
    )
    live_service = LiveSessionService(
        meetings_root=meetings_root,
        state_path=live_store.path,
        model_path=model_path,
        source_preflight=_source_preflight,
        store=live_store,
        coordinator=coordinator,
    )
    repository = AuthRepository(tmp_path / "auth.db")
    repository.initialize()
    app = create_app(config={})
    app.state.asu_june_bot = _State(
        meetings_service=MeetingsService(meetings_root),
        job_runner=runner,
        live_session_service=live_service,
        local_auth_service=LocalAuthService(repository),
        admin_service=AdminService(repository),
    )
    client = TestClient(app, raise_server_exceptions=False)
    try:
        yield client, coordinator, job_store, live_store
    finally:
        client.close()
        live_service.shutdown()


def test_stage_start_returns_machine_409_while_live_is_active(coordination_api) -> None:
    client, coordinator, _job_store, _live_store = coordination_api
    coordinator.reserve_live(_live_record())

    response = client.post(
        f"/meetings/{MEETING_ID}/jobs/transcribe",
        headers=AUTH,
    )

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "live_session_active",
        "message": "Stop live capture before starting offline meeting processing",
    }
    assert "runtime" not in response.text


def test_pipeline_start_returns_machine_409_while_live_is_active(coordination_api) -> None:
    client, coordinator, _job_store, _live_store = coordination_api
    coordinator.reserve_live(_live_record())

    response = client.post(
        f"/meetings/{MEETING_ID}/jobs/pipeline",
        headers=AUTH,
        json={"profile": "full"},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "live_session_active"


def test_stage_retry_returns_machine_409_while_live_is_active(coordination_api) -> None:
    client, coordinator, _job_store, _live_store = coordination_api
    coordinator.reserve_live(_live_record())

    response = client.post(
        f"/meetings/{MEETING_ID}/jobs/transcribe/retry",
        headers=AUTH,
        json={"force": False},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "live_session_active"


def test_live_start_returns_machine_409_while_offline_job_is_active(
    coordination_api,
) -> None:
    client, coordinator, _job_store, _live_store = coordination_api
    coordinator.reserve_job(_job_record())

    response = client.post(
        f"/meetings/{MEETING_ID}/live/sessions",
        headers=AUTH,
        json={"source": "MIC"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "offline_job_active",
        "message": "Stop offline meeting processing before starting live capture",
    }
    assert str(Path.cwd()) not in response.text


def test_readiness_blocks_pending_stages_while_live_is_active(coordination_api) -> None:
    client, coordinator, _job_store, _live_store = coordination_api
    coordinator.reserve_live(_live_record())

    response = client.get(
        f"/meetings/{MEETING_ID}/pipeline/readiness",
        headers=AUTH,
    )

    assert response.status_code == 200
    pending = [stage for stage in response.json()["stages"] if stage["state"] != "done"]
    assert pending
    assert all(stage["state"] == "blocked" for stage in pending)
    assert all(stage["reason"] == "live_session_active" for stage in pending)


def test_live_preflight_blocks_capture_while_offline_job_is_active(
    coordination_api,
) -> None:
    client, coordinator, _job_store, _live_store = coordination_api
    coordinator.reserve_job(_job_record())

    response = client.get(
        f"/meetings/{MEETING_ID}/live/preflight?source=MIC",
        headers=AUTH,
    )

    assert response.status_code == 200
    assert response.json()["available"] is False
    assert response.json()["reason"] == "offline_job_active"
