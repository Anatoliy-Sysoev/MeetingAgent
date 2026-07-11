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
from asu_june_bot.auth.repository import AuthRepository  # noqa: E402
from asu_june_bot.auth.service import AdminService, LocalAuthService  # noqa: E402
from asu_june_bot.auth.throttle import LoginThrottle  # noqa: E402
from asu_june_bot.meetings.service import MeetingCardError, MeetingsService  # noqa: E402

TOKEN = "meeting-metadata-redaction-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
MEETING_ID = "2026-07-11__metadata-redaction"
PRIVATE_ABS = r"C:\Users\Private\Customer\meeting.mp4"
PRIVATE_REL = "artifacts/internal/customer-summary.md"
TRAVERSAL = "../../outside/secret.md"


@dataclass(slots=True)
class FakeState:
    meetings_service: MeetingsService
    local_auth_service: LocalAuthService
    admin_service: AdminService
    auth_repository: AuthRepository
    config: dict = field(default_factory=dict)
    trusted_proxy_cidrs: list[str] = field(default_factory=list)
    login_throttle: LoginThrottle = field(default_factory=LoginThrottle)


def _make_client(root: Path) -> tuple[TestClient, AdminService]:
    os.environ["MEETINGAGENT_API_TOKEN"] = TOKEN
    repository = AuthRepository(root / "_auth.db")
    repository.initialize()
    admin_service = AdminService(repository)
    app = create_app()
    app.state.asu_june_bot = FakeState(
        meetings_service=MeetingsService(root),
        local_auth_service=LocalAuthService(repository),
        admin_service=admin_service,
        auth_repository=repository,
    )
    return TestClient(app, raise_server_exceptions=False), admin_service


def _write_card(root: Path, card: dict, meeting_id: str = MEETING_ID) -> Path:
    meeting_dir = root / meeting_id
    meeting_dir.mkdir(parents=True, exist_ok=True)
    (meeting_dir / "meeting.json").write_text(
        json.dumps(card, ensure_ascii=False), encoding="utf-8"
    )
    return meeting_dir


def _private_card() -> dict:
    return {
        "schema_version": 1,
        "meeting_id": MEETING_ID,
        "title": "Metadata Contract",
        "date": "2026-07-11",
        "start_time": "10:00:00",
        "duration_minutes": 15,
        "processing_status": "failed",
        "participants": ["Analyst", "Owner"],
        "source": {
            "kind": "offline_record",
            "original_location": PRIVATE_ABS,
            "media_files": [
                {
                    "path": "source/audio.wav",
                    "media_type": "audio",
                    "sha256": "a" * 64,
                    "duration_seconds": 12.5,
                }
            ],
            "audio_tracks": ["MIC"],
            "derived_tracks": ["MIX"],
            "notes": PRIVATE_ABS,
        },
        "artifacts": {"memo": PRIVATE_REL},
        "classification": {
            "project_stage": "PRJ-01",
            "summary": PRIVATE_ABS,
            "confidence": 0.8,
            "needs_review": True,
        },
        "links": {
            "related_documents": [{"id_or_path": PRIVATE_ABS, "title": "Private"}]
        },
        "retention": {"policy": "protected", "reason": PRIVATE_ABS},
        "rag": {
            "index_policy": "structured_artifacts_and_final_transcript",
            "indexed_artifacts": [PRIVATE_REL],
            "no_index_artifacts": [TRAVERSAL],
            "last_indexed_at": "2026-07-11T10:30:00+00:00",
        },
        "last_error": {
            "stage": "transcribe",
            "code": "stage_failed",
            "message": PRIVATE_ABS,
            "timestamp": "2026-07-11T10:20:00+00:00",
        },
        "created_at": "2026-07-11T10:00:00+00:00",
        "updated_at": "2026-07-11T10:20:00+00:00",
    }


def _assert_private_metadata_absent(response_text: str) -> None:
    assert PRIVATE_ABS not in response_text
    assert PRIVATE_REL not in response_text
    assert TRAVERSAL not in response_text
    assert "original_location" not in response_text
    assert "no_index_artifacts" not in response_text
    assert '"message"' not in response_text


def test_meeting_list_and_detail_use_path_safe_dtos(tmp_path: Path) -> None:
    meeting_dir = _write_card(tmp_path, _private_card())
    source = meeting_dir / "source"
    source.mkdir()
    (source / "audio.wav").write_bytes(b"RIFF0000WAVE")
    client, _ = _make_client(tmp_path)

    list_response = client.get("/meetings", headers=AUTH)
    detail_response = client.get(f"/meetings/{MEETING_ID}", headers=AUTH)

    assert list_response.status_code == 200
    assert detail_response.status_code == 200
    _assert_private_metadata_absent(list_response.text)
    _assert_private_metadata_absent(detail_response.text)
    summary = list_response.json()["items"][0]
    detail = detail_response.json()
    assert "media_files" not in summary
    assert summary["media_count"] == 1
    assert summary["workspace_url"].endswith("/workspace")
    assert detail["source"] == {
        "kind": "offline_record",
        "audio_tracks": ["MIC"],
        "derived_tracks": ["MIX"],
    }
    assert detail["rag"]["indexed"] is True
    assert detail["rag"]["indexed_artifacts_count"] == 1
    assert detail["last_error"]["detail"].startswith("Meeting processing stage failed")
    assert detail["media"][0]["media_id"] == "0"
    assert detail["media"][0]["view_url"].endswith("/media/0")
    assert "path" not in detail["media"][0]


def test_artifact_metadata_uses_ids_urls_and_stable_path_errors(tmp_path: Path) -> None:
    card = _private_card()
    card["artifacts"] = {
        "memo": TRAVERSAL,
        "tasks": PRIVATE_ABS,
        "protocol": "artifacts/protocol.md",
    }
    _write_card(tmp_path, card)
    client, _ = _make_client(tmp_path)

    response = client.get(f"/meetings/{MEETING_ID}/artifacts", headers=AUTH)

    assert response.status_code == 200
    _assert_private_metadata_absent(response.text)
    artifacts = {entry["artifact_id"]: entry for entry in response.json()["artifacts"]}
    assert artifacts["memo"]["error"] == "invalid_artifact_path"
    assert artifacts["tasks"]["error"] == "invalid_artifact_path"
    assert artifacts["protocol"]["exists"] is False
    assert all("path" not in entry for entry in artifacts.values())


def test_broken_card_errors_are_bounded_machine_codes(tmp_path: Path) -> None:
    meeting_dir = tmp_path / MEETING_ID
    meeting_dir.mkdir()
    raw = "{broken-json " + PRIVATE_ABS
    (meeting_dir / "meeting.json").write_text(raw, encoding="utf-8")
    client, _ = _make_client(tmp_path)

    list_response = client.get("/meetings", headers=AUTH)
    detail_response = client.get(f"/meetings/{MEETING_ID}", headers=AUTH)

    assert list_response.status_code == 200
    error = list_response.json()["errors"][0]
    assert error == {
        "meeting_id": MEETING_ID,
        "code": "meeting_card_invalid_json",
        "detail": "Meeting card is invalid or unreadable.",
    }
    assert detail_response.status_code == 422
    assert detail_response.json()["detail"] == {
        "error": "meeting_card_invalid_json",
        "message": "Meeting card is invalid or unreadable",
    }
    assert PRIVATE_ABS not in list_response.text + detail_response.text
    assert "line 1 column" not in list_response.text + detail_response.text


def test_read_failure_detail_is_not_exposed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_card(tmp_path, _private_card())
    client, _ = _make_client(tmp_path)

    def _raise(_path: Path) -> dict:
        raise MeetingCardError("meeting_card_unreadable", PRIVATE_ABS)

    monkeypatch.setattr("asu_june_bot.meetings.service._read_meeting_json", _raise)
    response = client.get(f"/meetings/{MEETING_ID}", headers=AUTH)

    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "meeting_card_unreadable"
    assert PRIVATE_ABS not in response.text


def test_traversal_identifiers_are_not_echoed_in_errors(tmp_path: Path) -> None:
    client, _ = _make_client(tmp_path)
    private_id = "C:private-secret"

    meeting_response = client.get(f"/meetings/{private_id}", headers=AUTH)
    artifact_response = client.get(
        f"/meetings/{MEETING_ID}/artifacts/{private_id}", headers=AUTH
    )

    assert meeting_response.status_code == 404
    assert artifact_response.status_code == 404
    assert private_id not in meeting_response.text
    assert private_id not in artifact_response.text


def test_admin_only_diagnostics_preserve_raw_card_and_storage_path(tmp_path: Path) -> None:
    _write_card(tmp_path, _private_card())
    client, admin_service = _make_client(tmp_path)
    admin_service.create_user(
        email="admin@example.com",
        password="admin-password",
        roles=["admin"],
        actor_id="test",
    )
    admin_service.create_user(
        email="viewer@example.com",
        password="viewer-password",
        roles=["viewer"],
        actor_id="test",
    )

    anonymous = client.get(f"/admin/diagnostics/meetings/{MEETING_ID}")
    machine = client.get(
        f"/admin/diagnostics/meetings/{MEETING_ID}", headers=AUTH
    )
    viewer_login = client.post(
        "/auth/local/login",
        json={"email": "viewer@example.com", "password": "viewer-password"},
    )
    client.cookies.set("ma_session", viewer_login.cookies["ma_session"])
    viewer = client.get(f"/admin/diagnostics/meetings/{MEETING_ID}")
    admin_login = client.post(
        "/auth/local/login",
        json={"email": "admin@example.com", "password": "admin-password"},
    )
    client.cookies.set("ma_session", admin_login.cookies["ma_session"])
    admin = client.get(f"/admin/diagnostics/meetings/{MEETING_ID}")

    assert anonymous.status_code == 401
    assert machine.status_code == 403
    assert viewer.status_code == 403
    assert admin.status_code == 200
    assert admin.json()["status"] == "ok"
    assert admin.json()["card"]["source"]["original_location"] == PRIVATE_ABS
    assert str(tmp_path) in admin.json()["storage_path"]


def test_malformed_machine_fields_cannot_smuggle_paths(tmp_path: Path) -> None:
    card = _private_card()
    card["processing_status"] = PRIVATE_ABS
    card["date"] = PRIVATE_ABS
    card["start_time"] = TRAVERSAL
    card["created_at"] = PRIVATE_ABS
    card["updated_at"] = TRAVERSAL
    card["source"]["kind"] = TRAVERSAL
    card["source"]["audio_tracks"] = ["MIC", PRIVATE_ABS]
    card["source"]["media_files"][0]["sha256"] = PRIVATE_ABS
    card["classification"]["project_stage"] = PRIVATE_ABS
    card["retention"]["policy"] = TRAVERSAL
    card["rag"]["index_policy"] = PRIVATE_ABS
    card["last_error"]["stage"] = PRIVATE_ABS
    card["last_error"]["code"] = TRAVERSAL
    meeting_dir = _write_card(tmp_path, card)
    source = meeting_dir / "source"
    source.mkdir()
    (source / "audio.wav").write_bytes(b"RIFF0000WAVE")
    client, _ = _make_client(tmp_path)

    response = client.get(f"/meetings/{MEETING_ID}", headers=AUTH)

    assert response.status_code == 200
    _assert_private_metadata_absent(response.text)
    detail = response.json()
    assert detail["processing_status"] == "unknown"
    assert detail["date"] is None
    assert detail["start_time"] is None
    assert detail["created_at"] is None
    assert detail["updated_at"] is None
    assert detail["source"]["kind"] is None
    assert detail["source"]["audio_tracks"] == ["MIC"]
    assert detail["classification"]["project_stage"] is None
    assert detail["retention"]["policy"] is None
    assert detail["rag"]["index_policy"] is None
    assert detail["last_error"]["stage"] is None
    assert detail["last_error"]["code"] == "stage_failed"
    assert detail["media"][0]["sha256"] is None


def test_openapi_declares_explicit_meeting_metadata_models(tmp_path: Path) -> None:
    client, _ = _make_client(tmp_path)
    openapi = client.app.openapi()

    expected = {
        "/meetings": "MeetingListResponse",
        "/meetings/{meeting_id}": "MeetingDetail",
        "/meetings/{meeting_id}/artifacts": "ArtifactListResponse",
        "/meetings/{meeting_id}/media": "MediaListResponse",
    }
    for path, schema_name in expected.items():
        schema = openapi["paths"][path]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]
        assert schema["$ref"].endswith(f"/{schema_name}")
