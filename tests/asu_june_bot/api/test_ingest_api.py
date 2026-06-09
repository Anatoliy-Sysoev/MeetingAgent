from __future__ import annotations

import io
import json
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
from asu_june_bot.meetings.service import MeetingsService  # noqa: E402

TOKEN = "test-secret-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
AUDIO_BYTES = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00"  # fake WAV header


@dataclass(slots=True)
class FakeState:
    meetings_service: MeetingsService


def make_client(meetings_root: Path) -> TestClient:
    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)
    app.state.asu_june_bot = FakeState(meetings_service=MeetingsService(meetings_root))
    return client


# ------------------------------------------------------------------
# require_token
# ------------------------------------------------------------------

def test_missing_token_header_returns_401(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    client = make_client(tmp_path)
    resp = client.post("/meetings/ingest", files={"file": ("a.mp3", AUDIO_BYTES, "audio/mpeg")})
    assert resp.status_code == 401


def test_invalid_token_returns_401(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    client = make_client(tmp_path)
    resp = client.post(
        "/meetings/ingest",
        files={"file": ("a.mp3", AUDIO_BYTES, "audio/mpeg")},
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert resp.status_code == 401


def test_malformed_auth_header_returns_401(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    client = make_client(tmp_path)
    resp = client.post(
        "/meetings/ingest",
        files={"file": ("a.mp3", AUDIO_BYTES, "audio/mpeg")},
        headers={"Authorization": TOKEN},  # missing "Bearer " prefix
    )
    assert resp.status_code == 401


def test_env_token_not_set_returns_500(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MEETINGAGENT_API_TOKEN", raising=False)
    client = make_client(tmp_path)
    resp = client.post(
        "/meetings/ingest",
        files={"file": ("a.mp3", AUDIO_BYTES, "audio/mpeg")},
        headers=AUTH,
    )
    assert resp.status_code == 500


def test_valid_token_allows_upload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    client = make_client(tmp_path)
    resp = client.post(
        "/meetings/ingest",
        files={"file": ("recording.mp3", AUDIO_BYTES, "audio/mpeg")},
        headers=AUTH,
    )
    assert resp.status_code == 201


# ------------------------------------------------------------------
# File validation
# ------------------------------------------------------------------

def test_unsupported_file_type_returns_422(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    client = make_client(tmp_path)
    resp = client.post(
        "/meetings/ingest",
        files={"file": ("document.pdf", b"%PDF", "application/pdf")},
        headers=AUTH,
    )
    assert resp.status_code == 422


def test_no_file_returns_422(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    client = make_client(tmp_path)
    resp = client.post("/meetings/ingest", headers=AUTH)
    assert resp.status_code == 422


# ------------------------------------------------------------------
# Happy path: 201 card created
# ------------------------------------------------------------------

def test_valid_upload_returns_201_and_creates_card(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    client = make_client(tmp_path)
    resp = client.post(
        "/meetings/ingest",
        files={"file": ("meeting.mp3", AUDIO_BYTES, "audio/mpeg")},
        data={"title": "Test Meeting", "date": "2026-01-10"},
        headers=AUTH,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "Test Meeting"
    assert body["date"] == "2026-01-10"
    assert len(body["sha256"]) == 64
    assert body["meeting_id"].startswith("2026-01-10__")

    # Card file exists on disk
    meeting_dir = tmp_path / body["meeting_id"]
    card_path = meeting_dir / "meeting.json"
    assert card_path.exists()

    card = json.loads(card_path.read_text(encoding="utf-8"))
    assert card["processing_status"] == "new"
    assert card["meeting_id"] == body["meeting_id"]
    assert card["source"]["media_files"][0]["sha256"] == body["sha256"]


def test_sha256_in_card_matches_content(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import hashlib
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    client = make_client(tmp_path)
    content = b"fake audio data 12345"
    resp = client.post(
        "/meetings/ingest",
        files={"file": ("audio.wav", content, "audio/wav")},
        headers=AUTH,
    )
    assert resp.status_code == 201
    expected = hashlib.sha256(content).hexdigest()
    assert resp.json()["sha256"] == expected
    # Also verify it's in the card
    meeting_id = resp.json()["meeting_id"]
    card = json.loads((tmp_path / meeting_id / "meeting.json").read_text(encoding="utf-8"))
    assert card["source"]["media_files"][0]["sha256"] == expected


# ------------------------------------------------------------------
# Duplicate detection
# ------------------------------------------------------------------

def test_duplicate_upload_returns_409(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    client = make_client(tmp_path)
    content = b"unique audio bytes for dedup test"

    resp1 = client.post(
        "/meetings/ingest",
        files={"file": ("rec.mp3", content, "audio/mpeg")},
        headers=AUTH,
    )
    assert resp1.status_code == 201
    first_id = resp1.json()["meeting_id"]

    resp2 = client.post(
        "/meetings/ingest",
        files={"file": ("rec.mp3", content, "audio/mpeg")},
        headers=AUTH,
    )
    assert resp2.status_code == 409
    body2 = resp2.json()
    assert body2["duplicate"] is True
    assert body2["existing_meeting_id"] == first_id


def test_duplicate_does_not_create_second_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    client = make_client(tmp_path)
    content = b"another unique audio for directory test"

    client.post(
        "/meetings/ingest",
        files={"file": ("dup.mp3", content, "audio/mpeg")},
        headers=AUTH,
    )
    dirs_before = [d for d in tmp_path.iterdir() if d.is_dir()]
    assert len(dirs_before) == 1

    client.post(
        "/meetings/ingest",
        files={"file": ("dup.mp3", content, "audio/mpeg")},
        headers=AUTH,
    )
    dirs_after = [d for d in tmp_path.iterdir() if d.is_dir()]
    assert len(dirs_after) == 1  # no second directory


def test_different_content_creates_separate_cards(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    client = make_client(tmp_path)

    resp1 = client.post(
        "/meetings/ingest",
        files={"file": ("a.mp3", b"audio data AAA", "audio/mpeg")},
        data={"title": "Meeting A"},
        headers=AUTH,
    )
    resp2 = client.post(
        "/meetings/ingest",
        files={"file": ("b.mp3", b"audio data BBB", "audio/mpeg")},
        data={"title": "Meeting B"},
        headers=AUTH,
    )
    assert resp1.status_code == 201
    assert resp2.status_code == 201
    assert resp1.json()["meeting_id"] != resp2.json()["meeting_id"]
    assert len([d for d in tmp_path.iterdir() if d.is_dir()]) == 2


# ------------------------------------------------------------------
# meeting.json schema validation
# ------------------------------------------------------------------

def test_meeting_json_passes_schema_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import jsonschema

    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    client = make_client(tmp_path)
    resp = client.post(
        "/meetings/ingest",
        files={"file": ("valid.mp4", b"fake mp4 data", "video/mp4")},
        data={"title": "Schema Test", "date": "2026-03-15"},
        headers=AUTH,
    )
    assert resp.status_code == 201

    meeting_id = resp.json()["meeting_id"]
    card_path = tmp_path / meeting_id / "meeting.json"
    card = json.loads(card_path.read_text(encoding="utf-8"))

    schema_path = ROOT / "configs" / "schemas" / "meeting.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    # Must not raise
    jsonschema.Draft202012Validator(schema).validate(card)


# ------------------------------------------------------------------
# Rollback: bad schema → directory removed
# ------------------------------------------------------------------

def test_rollback_on_schema_failure_removes_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If create_meeting triggers schema error, meeting dir is cleaned up."""
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)

    # Inject a service with a bad schema path so validation always fails
    bad_schema_path = tmp_path / "bad_schema.json"
    bad_schema_path.write_text('{"type": "array"}', encoding="utf-8")

    from asu_june_bot.api.app import create_app as _create_app
    from asu_june_bot.api.routes_ingest import _SCHEMA_PATH
    import asu_june_bot.api.routes_ingest as ingest_mod

    meetings_root = tmp_path / "meetings"
    meetings_root.mkdir()
    svc = MeetingsService(meetings_root)

    app = _create_app()
    client = TestClient(app, raise_server_exceptions=False)
    app.state.asu_june_bot = FakeState(meetings_service=svc)

    # Patch the module-level schema path
    monkeypatch.setattr(ingest_mod, "_SCHEMA_PATH", bad_schema_path)

    resp = client.post(
        "/meetings/ingest",
        files={"file": ("rec.mp3", b"audio bytes", "audio/mpeg")},
        headers=AUTH,
    )
    assert resp.status_code == 422
    # No meeting directories should remain
    leftover = [d for d in meetings_root.iterdir() if d.is_dir()]
    assert leftover == []
