from __future__ import annotations

import json
import threading
import wave
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from asu_june_bot.api.app import create_app
from asu_june_bot.auth.repository import AuthRepository
from asu_june_bot.auth.service import AdminService, LocalAuthService
from asu_june_bot.auth.throttle import LoginThrottle
from asu_june_bot.live_sessions import LiveSessionService
from meeting_agent.live_transcription.audio_capture import AudioDevice, AudioSourcePreflight
from meeting_agent.live_transcription.schema import LiveSegment
from meeting_agent.live_transcription.vosk_backend import VoskLiveResult


TOKEN = "live-api-test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
MEETING_ID = "2026-07-13__live-api"


def _meeting(root: Path) -> None:
    meeting_dir = root / MEETING_ID
    meeting_dir.mkdir(parents=True)
    (meeting_dir / "meeting.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "meeting_id": MEETING_ID,
                "title": "Live API",
                "processing_status": "new",
                "source": {"kind": "live_session"},
                "artifacts": {},
                "rag": {"index_policy": "structured_artifacts_and_final_transcript"},
            }
        ),
        encoding="utf-8",
    )


def _preflight(source: str, **_kwargs) -> AudioSourcePreflight:
    return AudioSourcePreflight(
        source=source,
        available=True,
        device_available=True,
        capture_supported=True,
        devices=[
            AudioDevice(
                index=3,
                name=r"C:\Users\private\Headset",
                hostapi="raw-host-api",
                max_input_channels=2,
                max_output_channels=0,
                default_samplerate=48_000,
            )
        ],
    )


class _HoldTranscriber:
    def __init__(self) -> None:
        self.started = threading.Event()

    def __call__(self, config) -> VoskLiveResult:
        self.started.set()
        config.event_callback(
            "partial",
            {"text": "черновик", "start": 0.0, "end": 0.2},
        )
        segment = LiveSegment(
            segment_id="live-seg-000000",
            segment_index=0,
            start=0.0,
            end=0.5,
            text="готово",
            source=config.source,
            engine="vosk",
        )
        config.event_callback("final", segment.to_dict())
        config.stop_event.wait(timeout=5)
        assert config.audio_archive_path is not None
        config.audio_archive_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(config.audio_archive_path), "wb") as archive:
            archive.setnchannels(1)
            archive.setsampwidth(2)
            archive.setframerate(config.sample_rate)
            archive.writeframes(b"\x00\x00" * (config.sample_rate // 2))
        return VoskLiveResult(
            segments=[segment],
            partials=[],
            metrics={"duration": 0.5, "elapsed_seconds": 0.1},
            audio_archive_path=config.audio_archive_path,
        )


@dataclass(slots=True)
class _State:
    live_session_service: LiveSessionService
    local_auth_service: LocalAuthService
    admin_service: AdminService
    login_throttle: LoginThrottle = field(default_factory=LoginThrottle)
    trusted_proxy_cidrs: list[str] = field(default_factory=list)


@pytest.fixture
def live_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    meetings_root = tmp_path / "meetings"
    _meeting(meetings_root)
    model_path = tmp_path / "model"
    model_path.mkdir()
    (model_path / "am").mkdir()
    (model_path / "conf").mkdir()
    (model_path / "graph").mkdir()
    (model_path / "am" / "final.mdl").touch()
    (model_path / "conf" / "model.conf").touch()
    (model_path / "graph" / "HCLG.fst").touch()
    transcriber = _HoldTranscriber()
    service = LiveSessionService(
        meetings_root=meetings_root,
        state_path=tmp_path / "runtime" / "live.json",
        model_path=model_path,
        transcriber=transcriber,
        source_preflight=_preflight,
        stop_timeout_seconds=2,
    )
    repository = AuthRepository(tmp_path / "auth.db")
    repository.initialize()
    local_auth = LocalAuthService(repository)
    admin = AdminService(repository)
    app = create_app(config={})
    app.state.asu_june_bot = _State(
        live_session_service=service,
        local_auth_service=local_auth,
        admin_service=admin,
    )
    client = TestClient(app, raise_server_exceptions=False)
    try:
        yield client, service, transcriber, admin
    finally:
        client.close()
        service.shutdown()


def _login(
    client: TestClient,
    admin: AdminService,
    *,
    email: str,
    roles: list[str],
) -> str:
    admin.create_user(
        email=email,
        password="StrongPassword!123",
        roles=roles,
        actor_id="system",
    )
    response = client.post(
        "/auth/local/login",
        json={"email": email, "password": "StrongPassword!123"},
    )
    assert response.status_code == 200, response.json()
    return response.json()["csrf_token"]


def test_live_routes_require_authentication(live_api) -> None:
    client, _service, _transcriber, _admin = live_api

    response = client.get(f"/meetings/{MEETING_ID}/live/preflight")

    assert response.status_code == 401
    assert client.get(f"/meetings/{MEETING_ID}/live/timeline").status_code == 401


def test_viewer_can_read_preflight_but_cannot_start(live_api) -> None:
    client, _service, _transcriber, admin = live_api
    _login(client, admin, email="viewer@example.test", roles=["viewer"])

    preflight = client.get(f"/meetings/{MEETING_ID}/live/preflight?source=MIC")
    start = client.post(
        f"/meetings/{MEETING_ID}/live/sessions",
        json={"source": "MIC"},
    )

    assert preflight.status_code == 200
    assert preflight.json()["devices"] == [
        {"device_index": 3, "label": "Audio device 3"}
    ]
    assert "hostapi" not in preflight.text
    assert "Users" not in preflight.text
    assert start.status_code == 403
    timeline = client.get(f"/meetings/{MEETING_ID}/live/timeline")
    assert timeline.status_code == 200
    assert timeline.json()["segments"] == []


def test_editor_lifecycle_requires_csrf_and_exposes_bounded_events(live_api) -> None:
    client, _service, transcriber, admin = live_api
    csrf = _login(client, admin, email="editor@example.test", roles=["editor"])

    rejected = client.post(
        f"/meetings/{MEETING_ID}/live/sessions",
        json={"source": "MIC"},
    )
    assert rejected.status_code == 403

    started = client.post(
        f"/meetings/{MEETING_ID}/live/sessions",
        json={"source": "MIC", "vad": "silero"},
        headers={"X-CSRF-Token": csrf},
    )
    assert started.status_code == 202, started.json()
    assert transcriber.started.wait(timeout=1)
    session_id = started.json()["session_id"]

    active = client.get(f"/meetings/{MEETING_ID}/live/sessions/active")
    status = client.get(f"/meetings/{MEETING_ID}/live/sessions/{session_id}")
    events = client.get(
        f"/meetings/{MEETING_ID}/live/sessions/{session_id}/events?after=0&limit=20"
    )
    assert active.status_code == status.status_code == events.status_code == 200
    assert active.json()["session"]["session_id"] == session_id
    assert events.json()["partial_events_durable"] is False
    assert any(item["type"] == "final" for item in events.json()["events"])

    rejected_stop = client.post(
        f"/meetings/{MEETING_ID}/live/sessions/{session_id}/stop"
    )
    assert rejected_stop.status_code == 403
    stopped = client.post(
        f"/meetings/{MEETING_ID}/live/sessions/{session_id}/stop",
        headers={"X-CSRF-Token": csrf},
    )
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "completed"
    assert "live_audio_mic" in stopped.json()["artifact_keys"]
    assert "live_segments_mix" in stopped.json()["artifact_keys"]
    timeline = client.get(
        f"/meetings/{MEETING_ID}/live/timeline?after=0&limit=1"
    )
    assert timeline.status_code == 200
    assert timeline.json()["meeting_id"] == MEETING_ID
    assert timeline.json()["segments"][0]["source"] == "MIC"
    assert "path" not in timeline.text.lower()


def test_live_timeline_has_bounded_query_contract(live_api) -> None:
    client, _service, _transcriber, _admin = live_api

    assert client.get(
        f"/meetings/{MEETING_ID}/live/timeline?after=-1",
        headers=AUTH,
    ).status_code == 422
    assert client.get(
        f"/meetings/{MEETING_ID}/live/timeline?limit=1001",
        headers=AUTH,
    ).status_code == 422


def test_corrupt_live_timeline_fails_closed_without_path_disclosure(live_api) -> None:
    client, service, _transcriber, _admin = live_api
    output = service.meetings_root / MEETING_ID / "transcript" / "live"
    output.mkdir(parents=True)
    (output / "live_segments.MIX.jsonl").write_bytes(b"\xffprivate-path")

    response = client.get(
        f"/meetings/{MEETING_ID}/live/timeline",
        headers=AUTH,
    )

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "live_timeline_unavailable",
        "message": "Live conversation timeline is unavailable",
    }
    assert "private" not in response.text.lower()


def test_machine_token_can_start_and_stop_without_csrf(live_api) -> None:
    client, _service, transcriber, _admin = live_api

    started = client.post(
        f"/meetings/{MEETING_ID}/live/sessions",
        json={"source": "MIC"},
        headers=AUTH,
    )
    assert started.status_code == 202
    assert transcriber.started.wait(timeout=1)

    stopped = client.post(
        f"/meetings/{MEETING_ID}/live/sessions/{started.json()['session_id']}/stop",
        headers=AUTH,
    )
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "completed"


def test_duplicate_active_session_returns_machine_readable_409(live_api) -> None:
    client, _service, transcriber, _admin = live_api
    first = client.post(
        f"/meetings/{MEETING_ID}/live/sessions",
        json={"source": "MIC"},
        headers=AUTH,
    )
    assert first.status_code == 202
    assert transcriber.started.wait(timeout=1)

    duplicate = client.post(
        f"/meetings/{MEETING_ID}/live/sessions",
        json={"source": "MIC"},
        headers=AUTH,
    )

    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "live_session_active"


def test_missing_or_wrong_meeting_never_leaks_session(live_api) -> None:
    client, _service, transcriber, _admin = live_api
    missing = client.get(
        "/meetings/2026-07-13__missing/live/preflight",
        headers=AUTH,
    )
    assert missing.status_code == 404

    started = client.post(
        f"/meetings/{MEETING_ID}/live/sessions",
        json={"source": "MIC"},
        headers=AUTH,
    )
    assert started.status_code == 202
    assert transcriber.started.wait(timeout=1)
    wrong = client.get(
        f"/meetings/2026-07-13__missing/live/sessions/{started.json()['session_id']}",
        headers=AUTH,
    )
    assert wrong.status_code == 404
    assert "path" not in wrong.text.lower()


@pytest.mark.parametrize(
    "body",
    [
        {"source": "CAMERA"},
        {"source": "MIC", "audio_device_index": -1},
        {"source": "MIC", "duration_sec": 0},
        {"source": "MIC", "vad": "unknown"},
    ],
)
def test_start_request_is_strictly_bounded(live_api, body: dict) -> None:
    client, _service, _transcriber, _admin = live_api

    response = client.post(
        f"/meetings/{MEETING_ID}/live/sessions",
        json=body,
        headers=AUTH,
    )

    assert response.status_code == 422
