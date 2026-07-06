"""API tests for manual SPEAKER_XX mapping (#122)."""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.api.app import create_app  # noqa: E402
from asu_june_bot.auth.repository import AuthRepository  # noqa: E402
from asu_june_bot.auth.service import AdminService, LocalAuthService  # noqa: E402
from asu_june_bot.auth.throttle import LoginThrottle  # noqa: E402
from asu_june_bot.meetings.service import MeetingsService  # noqa: E402

TOKEN = "speaker-mapping-token"
MEETING_ID = "2026-06-01__speaker-map"

VALID_CARD = {
    "schema_version": 1,
    "meeting_id": MEETING_ID,
    "title": "Speaker Map Meeting",
    "date": "2026-06-01",
    "processing_status": "transcribed",
    "participants": [],
    "source": {"kind": "offline_record"},
    "artifacts": {"speaker_transcript": "transcript/speaker_transcript.jsonl"},
    "classification": {},
    "links": {},
    "retention": {"policy": "default"},
    "rag": {"index_policy": "structured_artifacts_and_final_transcript"},
    "created_at": "2026-06-01T10:00:00",
    "updated_at": "2026-06-01T11:00:00",
}


@dataclass(slots=True)
class FakeState:
    meetings_service: MeetingsService
    local_auth_service: LocalAuthService
    admin_service: AdminService
    login_throttle: LoginThrottle = field(default_factory=LoginThrottle)


def make_meeting(root: Path, *, card_extra: dict | None = None) -> Path:
    card = dict(VALID_CARD)
    if card_extra:
        card.update(card_extra)
    meeting_dir = root / MEETING_ID
    (meeting_dir / "transcript").mkdir(parents=True)
    rows = [
        {"utterance_id": "utt-1", "speaker": "SPEAKER_01", "start": 0, "end": 1, "text": "Hello"},
        {"utterance_id": "utt-2", "speaker": "SPEAKER_02", "start": 1, "end": 2, "text": "Hi"},
    ]
    (meeting_dir / "transcript" / "speaker_transcript.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    (meeting_dir / "meeting.json").write_text(
        json.dumps(card, ensure_ascii=False),
        encoding="utf-8",
    )
    return meeting_dir


def make_client(root: Path) -> tuple[TestClient, AdminService]:
    os.environ["MEETINGAGENT_API_TOKEN"] = TOKEN
    repo = AuthRepository(root / "_auth.db")
    repo.initialize()
    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)
    auth = LocalAuthService(repo)
    admin = AdminService(repo)
    app.state.asu_june_bot = FakeState(
        meetings_service=MeetingsService(root),
        local_auth_service=auth,
        admin_service=admin,
    )
    return client, admin


def login(client: TestClient, admin: AdminService, email: str, roles: list[str]) -> tuple[str, str]:
    password = "speakerpass123"
    admin.create_user(email=email, password=password, roles=roles, actor_id="system")
    resp = client.post("/auth/local/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.cookies["ma_session"], resp.json()["csrf_token"]


def test_get_speakers_requires_auth(tmp_path: Path) -> None:
    make_meeting(tmp_path)
    client, _ = make_client(tmp_path)

    resp = client.get(f"/meetings/{MEETING_ID}/speakers")

    assert resp.status_code == 401


def test_get_speakers_returns_discovered_and_mapped_names(tmp_path: Path) -> None:
    make_meeting(
        tmp_path,
        card_extra={"speaker_mapping": {"SPEAKER_01": {"name": "Денис", "role": "Lead"}}},
    )
    client, _ = make_client(tmp_path)

    resp = client.get(
        f"/meetings/{MEETING_ID}/speakers",
        headers={"Authorization": f"Bearer {TOKEN}"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["mapping"] == {"SPEAKER_01": {"name": "Денис", "role": "Lead"}}
    assert body["speakers"][0]["display_name"] == "Денис"
    assert "C:\\" not in resp.text


def test_update_mapping_requires_csrf_for_cookie_user(tmp_path: Path) -> None:
    make_meeting(tmp_path)
    client, admin = make_client(tmp_path)
    cookie, _csrf = login(client, admin, "editor@example.com", ["editor"])

    resp = client.put(
        f"/meetings/{MEETING_ID}/speakers/mapping",
        json={"mapping": {"SPEAKER_01": {"name": "Денис", "role": "Lead"}}},
        cookies={"ma_session": cookie},
    )

    assert resp.status_code == 403


def test_update_mapping_requires_editor_role(tmp_path: Path) -> None:
    make_meeting(tmp_path)
    client, admin = make_client(tmp_path)
    cookie, csrf = login(client, admin, "viewer@example.com", ["viewer"])

    resp = client.put(
        f"/meetings/{MEETING_ID}/speakers/mapping",
        json={"mapping": {"SPEAKER_01": {"name": "Денис", "role": "Lead"}}},
        cookies={"ma_session": cookie},
        headers={"X-CSRF-Token": csrf},
    )

    assert resp.status_code == 403


def test_update_mapping_persists_and_transcript_uses_names(tmp_path: Path) -> None:
    make_meeting(tmp_path)
    client, admin = make_client(tmp_path)
    cookie, csrf = login(client, admin, "editor2@example.com", ["editor"])

    resp = client.put(
        f"/meetings/{MEETING_ID}/speakers/mapping",
        json={"mapping": {"SPEAKER_01": {"name": "Денис Белецкий", "role": "Lead"}}},
        cookies={"ma_session": cookie},
        headers={"X-CSRF-Token": csrf},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["mapping"]["SPEAKER_01"]["name"] == "Денис Белецкий"
    transcript = client.get(
        f"/meetings/{MEETING_ID}/transcript/segments",
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert transcript.status_code == 200
    segment = transcript.json()["segments"][0]
    assert segment["speaker"] == "Денис Белецкий"
    assert segment["speaker_label"] == "SPEAKER_01"
    assert segment["speaker_role"] == "Lead"


def test_update_mapping_rejects_unknown_speaker_label(tmp_path: Path) -> None:
    make_meeting(tmp_path)
    client, admin = make_client(tmp_path)
    cookie, csrf = login(client, admin, "editor3@example.com", ["editor"])

    resp = client.put(
        f"/meetings/{MEETING_ID}/speakers/mapping",
        json={"mapping": {"ADMIN": {"name": "Bad"}}},
        cookies={"ma_session": cookie},
        headers={"X-CSRF-Token": csrf},
    )

    assert resp.status_code == 422
