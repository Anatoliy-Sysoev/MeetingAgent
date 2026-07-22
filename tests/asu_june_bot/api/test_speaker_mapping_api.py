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
    (meeting_dir / "transcript" / "segments.jsonl").write_text(
        '{"segment_id":"seg-raw","text":"raw"}\n', encoding="utf-8"
    )
    (meeting_dir / "transcript" / "diarization.jsonl").write_text(
        '{"speaker":"SPEAKER_01","start":0,"end":1}\n', encoding="utf-8"
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
        meetings_service=MeetingsService(
            root,
            speaker_directory_path=root / "data" / "speaker_directory.json",
        ),
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
        json={"mapping": {"SPEAKER_01": {"name": "Алексей Петров", "role": "Lead"}}},
        cookies={"ma_session": cookie},
        headers={"X-CSRF-Token": csrf},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["mapping"]["SPEAKER_01"]["name"] == "Алексей Петров"
    transcript = client.get(
        f"/meetings/{MEETING_ID}/transcript/segments",
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert transcript.status_code == 200
    segment = transcript.json()["segments"][0]
    assert segment["speaker"] == "Алексей Петров"
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


def test_speaker_directory_crud_and_mapping_snapshot_survives_delete(tmp_path: Path) -> None:
    make_meeting(tmp_path)
    client, admin = make_client(tmp_path)
    cookie, csrf = login(client, admin, "directory-editor@example.com", ["editor"])
    headers = {"X-CSRF-Token": csrf}
    cookies = {"ma_session": cookie}

    created = client.post(
        "/speakers",
        json={"name": "Анна", "role": "Аналитик", "company": "Acme"},
        headers=headers,
        cookies=cookies,
    )
    assert created.status_code == 201, created.text
    profile = created.json()
    assert "C:\\" not in created.text

    updated = client.put(
        f"/speakers/{profile['speaker_id']}",
        json={"name": "Анна", "role": "Ведущий аналитик", "company": "Acme"},
        headers=headers,
        cookies=cookies,
    )
    assert updated.status_code == 200, updated.text
    profile = updated.json()

    listed = client.get("/speakers?query=acme", cookies=cookies)
    assert listed.status_code == 200
    assert listed.json()["profiles"][0]["speaker_id"] == profile["speaker_id"]
    assert client.get(
        "/speakers", headers={"Authorization": f"Bearer {TOKEN}"}
    ).status_code == 403

    mapped = client.put(
        f"/meetings/{MEETING_ID}/speakers/mapping",
        json={
            "mapping": {
                "SPEAKER_01": {
                    "speaker_id": profile["speaker_id"],
                    "name": profile["name"],
                    "role": profile["role"],
                    "company": profile["company"],
                }
            }
        },
        headers=headers,
        cookies=cookies,
    )
    assert mapped.status_code == 200, mapped.text

    deleted = client.delete(
        f"/speakers/{profile['speaker_id']}", headers=headers, cookies=cookies
    )
    assert deleted.status_code == 204
    after = client.get(
        f"/meetings/{MEETING_ID}/speakers",
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert after.status_code == 200
    snapshot = after.json()["mapping"]["SPEAKER_01"]
    assert snapshot["name"] == "Анна"
    assert snapshot["company"] == "Acme"
    assert snapshot["role"] == "Ведущий аналитик"


def test_speaker_directory_write_requires_csrf_and_rejects_duplicate(tmp_path: Path) -> None:
    make_meeting(tmp_path)
    client, admin = make_client(tmp_path)
    cookie, csrf = login(client, admin, "directory-security@example.com", ["editor"])
    payload = {"name": "Анна", "company": "Acme"}

    missing_csrf = client.post("/speakers", json=payload, cookies={"ma_session": cookie})
    assert missing_csrf.status_code == 403
    first = client.post(
        "/speakers",
        json=payload,
        cookies={"ma_session": cookie},
        headers={"X-CSRF-Token": csrf},
    )
    assert first.status_code == 201
    duplicate = client.post(
        "/speakers",
        json={"name": " анна ", "company": "acme"},
        cookies={"ma_session": cookie},
        headers={"X-CSRF-Token": csrf},
    )
    assert duplicate.status_code == 409


def test_speaker_override_single_and_range_are_resolved_without_raw_mutation(tmp_path: Path) -> None:
    meeting_dir = make_meeting(tmp_path)
    raw_segments = (meeting_dir / "transcript" / "segments.jsonl").read_bytes()
    raw_diarization = (meeting_dir / "transcript" / "diarization.jsonl").read_bytes()
    raw_speaker_transcript = (meeting_dir / "transcript" / "speaker_transcript.jsonl").read_bytes()
    client, admin = make_client(tmp_path)
    cookie, csrf = login(client, admin, "override-editor@example.com", ["editor"])
    auth = {"X-CSRF-Token": csrf}
    cookies = {"ma_session": cookie}

    single = client.put(
        f"/meetings/{MEETING_ID}/speakers/overrides",
        json={"segment_ids": ["utt-1"], "speaker_label": "SPEAKER_02"},
        headers=auth,
        cookies=cookies,
    )
    assert single.status_code == 200, single.text
    assert single.json()["overrides"][0]["segment_id"] == "utt-1"

    range_update = client.put(
        f"/meetings/{MEETING_ID}/speakers/overrides",
        json={"segment_ids": ["utt-1", "utt-2"], "speaker_label": "SPEAKER_01"},
        headers=auth,
        cookies=cookies,
    )
    assert range_update.status_code == 200, range_update.text
    assert {item["segment_id"] for item in range_update.json()["overrides"]} == {"utt-1", "utt-2"}

    transcript = client.get(f"/meetings/{MEETING_ID}/transcript/segments", cookies=cookies)
    assert transcript.status_code == 200
    rows = transcript.json()["segments"]
    assert [row["speaker_label"] for row in rows] == ["SPEAKER_01", "SPEAKER_01"]
    assert rows[0]["automatic_speaker_label"] == "SPEAKER_01"
    assert rows[1]["automatic_speaker_label"] == "SPEAKER_02"
    assert all(row["speaker_overridden"] for row in rows)
    assert (meeting_dir / "transcript" / "segments.jsonl").read_bytes() == raw_segments
    assert (meeting_dir / "transcript" / "diarization.jsonl").read_bytes() == raw_diarization
    assert (meeting_dir / "transcript" / "speaker_transcript.jsonl").read_bytes() == raw_speaker_transcript


def test_speaker_override_reset_restores_automatic_attribution(tmp_path: Path) -> None:
    make_meeting(tmp_path)
    client, admin = make_client(tmp_path)
    cookie, csrf = login(client, admin, "override-reset@example.com", ["editor"])
    request = {"headers": {"X-CSRF-Token": csrf}, "cookies": {"ma_session": cookie}}
    assert client.put(
        f"/meetings/{MEETING_ID}/speakers/overrides",
        json={"segment_ids": ["utt-1"], "speaker_label": "SPEAKER_02"},
        **request,
    ).status_code == 200

    reset = client.post(
        f"/meetings/{MEETING_ID}/speakers/overrides/reset",
        json={"segment_ids": ["utt-1"]},
        **request,
    )
    assert reset.status_code == 200
    assert reset.json()["overrides"] == []
    transcript = client.get(f"/meetings/{MEETING_ID}/transcript/segments", cookies=request["cookies"])
    row = transcript.json()["segments"][0]
    assert row["speaker_label"] == "SPEAKER_01"
    assert row["speaker_overridden"] is False


def test_speaker_override_rejects_unknown_ids_labels_and_missing_csrf(tmp_path: Path) -> None:
    make_meeting(tmp_path)
    client, admin = make_client(tmp_path)
    cookie, csrf = login(client, admin, "override-security@example.com", ["editor"])
    endpoint = f"/meetings/{MEETING_ID}/speakers/overrides"

    no_csrf = client.put(
        endpoint,
        json={"segment_ids": ["utt-1"], "speaker_label": "SPEAKER_02"},
        cookies={"ma_session": cookie},
    )
    assert no_csrf.status_code == 403
    unknown_id = client.put(
        endpoint,
        json={"segment_ids": ["utt-404"], "speaker_label": "SPEAKER_02"},
        cookies={"ma_session": cookie},
        headers={"X-CSRF-Token": csrf},
    )
    assert unknown_id.status_code == 422
    unknown_label = client.put(
        endpoint,
        json={"segment_ids": ["utt-1"], "speaker_label": "SPEAKER_99"},
        cookies={"ma_session": cookie},
        headers={"X-CSRF-Token": csrf},
    )
    assert unknown_label.status_code == 422
    assert "C:\\" not in unknown_id.text + unknown_label.text


def test_speaker_override_write_requires_editor_and_audit_read_is_private(tmp_path: Path) -> None:
    make_meeting(tmp_path)
    client, admin = make_client(tmp_path)
    viewer_cookie, viewer_csrf = login(client, admin, "override-viewer@example.com", ["viewer"])
    endpoint = f"/meetings/{MEETING_ID}/speakers/overrides"

    assert client.get(endpoint, cookies={"ma_session": viewer_cookie}).status_code == 403
    denied = client.put(
        endpoint,
        json={"segment_ids": ["utt-1"], "speaker_label": "SPEAKER_02"},
        cookies={"ma_session": viewer_cookie},
        headers={"X-CSRF-Token": viewer_csrf},
    )
    assert denied.status_code == 403


def test_corrupt_speaker_override_document_returns_controlled_error(tmp_path: Path) -> None:
    meeting_dir = make_meeting(tmp_path)
    (meeting_dir / "transcript" / "speaker_overrides.json").write_text(
        '{"schema_version":1,"meeting_id":"wrong","events":[]}', encoding="utf-8"
    )
    client, admin = make_client(tmp_path)
    cookie, _csrf = login(client, admin, "override-corrupt@example.com", ["editor"])

    resp = client.get(f"/meetings/{MEETING_ID}/transcript/segments", cookies={"ma_session": cookie})

    assert resp.status_code == 422
    assert resp.json()["detail"]["error"] == "invalid_speaker_override"
    assert "C:\\" not in resp.text


def test_invalid_or_duplicate_source_segment_ids_fail_closed(tmp_path: Path) -> None:
    meeting_dir = make_meeting(tmp_path)
    transcript_path = meeting_dir / "transcript" / "speaker_transcript.jsonl"
    transcript_path.write_text(
        '{"utterance_id":[],"speaker":"SPEAKER_01","start":0,"end":1,"text":"bad"}\n',
        encoding="utf-8",
    )
    client, admin = make_client(tmp_path)
    cookie, _csrf = login(client, admin, "override-bad-source@example.com", ["editor"])

    resp = client.get(f"/meetings/{MEETING_ID}/transcript/segments", cookies={"ma_session": cookie})

    assert resp.status_code == 422
    assert resp.json()["detail"]["error"] == "invalid_speaker_override"
