"""Tests for GET /meetings/{id}/media and GET /meetings/{id}/media/{media_id}."""
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
from asu_june_bot.auth.service import LocalAuthService  # noqa: E402
from asu_june_bot.auth.throttle import LoginThrottle  # noqa: E402
from asu_june_bot.meetings.service import MeetingsService  # noqa: E402

TOKEN = "test-media-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}

MEETING_ID = "2026-06-01__media-test"

VALID_CARD = {
    "schema_version": 1,
    "meeting_id": MEETING_ID,
    "title": "Media Test Meeting",
    "date": "2026-06-01",
    "processing_status": "indexed",
    "participants": [],
    "source": {"kind": "offline_record"},
    "artifacts": {},
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
    login_throttle: LoginThrottle = field(default_factory=LoginThrottle)


def make_client(meetings_root: Path) -> TestClient:
    os.environ["MEETINGAGENT_API_TOKEN"] = TOKEN
    repo = AuthRepository(meetings_root / "_auth.db")
    repo.initialize()
    app = create_app()
    client = TestClient(app, raise_server_exceptions=False, headers=AUTH)
    app.state.asu_june_bot = FakeState(
        meetings_service=MeetingsService(meetings_root),
        local_auth_service=LocalAuthService(repo),
    )
    return client


def make_meeting(tmp_path: Path, extra_card: dict | None = None) -> Path:
    card = dict(VALID_CARD)
    if extra_card:
        card.update(extra_card)
    d = tmp_path / MEETING_ID
    d.mkdir(parents=True)
    (d / "meeting.json").write_text(json.dumps(card), encoding="utf-8")
    return d


def make_media_file(meeting_dir: Path, name: str = "audio.wav") -> Path:
    source = meeting_dir / "source"
    source.mkdir(exist_ok=True)
    p = source / name
    p.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")  # minimal WAV-like bytes
    return p


# ------------------------------------------------------------------
# GET /meetings/{id}/media — list
# ------------------------------------------------------------------

def test_media_list_no_auth(tmp_path: Path) -> None:
    make_meeting(tmp_path)
    client = make_client(tmp_path)
    resp = client.get(f"/meetings/{MEETING_ID}/media", headers={"Authorization": ""})
    assert resp.status_code == 401


def test_media_list_empty_when_no_media_files_in_card(tmp_path: Path) -> None:
    make_meeting(tmp_path)
    resp = make_client(tmp_path).get(f"/meetings/{MEETING_ID}/media")
    assert resp.status_code == 200
    assert resp.json()["media"] == []


def test_media_list_returns_metadata(tmp_path: Path) -> None:
    meeting_dir = make_meeting(tmp_path)
    p = make_media_file(meeting_dir, "audio.wav")
    card = json.loads((meeting_dir / "meeting.json").read_text())
    card["source"]["media_files"] = [
        {"path": "source/audio.wav", "media_type": "audio", "sha256": "abc123"}
    ]
    (meeting_dir / "meeting.json").write_text(json.dumps(card))
    resp = make_client(tmp_path).get(f"/meetings/{MEETING_ID}/media")
    assert resp.status_code == 200
    body = resp.json()
    assert body["meeting_id"] == MEETING_ID
    items = body["media"]
    assert len(items) == 1
    item = items[0]
    assert item["media_id"] == "0"
    assert item["filename"] == "audio.wav"
    assert item["media_type"] == "audio/wav"
    assert item["size_bytes"] == p.stat().st_size
    assert item["sha256"] == "abc123"
    assert "path" not in item  # no filesystem path exposed


def test_media_list_404_unknown_meeting(tmp_path: Path) -> None:
    resp = make_client(tmp_path).get("/meetings/9999-99-99__ghost/media")
    assert resp.status_code == 404


def test_media_list_skips_unsupported_extension(tmp_path: Path) -> None:
    meeting_dir = make_meeting(tmp_path)
    (meeting_dir / "source").mkdir(exist_ok=True)
    (meeting_dir / "source" / "video.avi").write_bytes(b"avi data")
    card = json.loads((meeting_dir / "meeting.json").read_text())
    card["source"]["media_files"] = [
        {"path": "source/video.avi", "media_type": "video"}
    ]
    (meeting_dir / "meeting.json").write_text(json.dumps(card))
    resp = make_client(tmp_path).get(f"/meetings/{MEETING_ID}/media")
    assert resp.status_code == 200
    assert resp.json()["media"] == []  # .avi not listed


def test_media_list_path_traversal_in_card_skipped(tmp_path: Path) -> None:
    meeting_dir = make_meeting(tmp_path)
    card = json.loads((meeting_dir / "meeting.json").read_text())
    card["source"]["media_files"] = [
        {"path": "../../../etc/passwd", "media_type": "audio"}
    ]
    (meeting_dir / "meeting.json").write_text(json.dumps(card))
    resp = make_client(tmp_path).get(f"/meetings/{MEETING_ID}/media")
    assert resp.status_code == 200
    assert resp.json()["media"] == []  # traversal silently skipped


def test_media_list_path_traversal_in_meeting_id_404(tmp_path: Path) -> None:
    resp = make_client(tmp_path).get("/meetings/../etc/media")
    # FastAPI decodes %2F but rejects literal /, so slug-with-slash is 404
    assert resp.status_code in (404, 422)


# ------------------------------------------------------------------
# GET /meetings/{id}/media/{media_id} — stream
# ------------------------------------------------------------------

def test_media_stream_returns_bytes(tmp_path: Path) -> None:
    meeting_dir = make_meeting(tmp_path)
    make_media_file(meeting_dir, "audio.wav")
    card = json.loads((meeting_dir / "meeting.json").read_text())
    card["source"]["media_files"] = [{"path": "source/audio.wav", "media_type": "audio"}]
    (meeting_dir / "meeting.json").write_text(json.dumps(card))
    resp = make_client(tmp_path).get(f"/meetings/{MEETING_ID}/media/0")
    assert resp.status_code == 200
    assert "audio" in resp.headers["content-type"]
    assert len(resp.content) > 0


def test_media_stream_no_auth(tmp_path: Path) -> None:
    meeting_dir = make_meeting(tmp_path)
    make_media_file(meeting_dir)
    card = json.loads((meeting_dir / "meeting.json").read_text())
    card["source"]["media_files"] = [{"path": "source/audio.wav", "media_type": "audio"}]
    (meeting_dir / "meeting.json").write_text(json.dumps(card))
    client = make_client(tmp_path)
    resp = client.get(f"/meetings/{MEETING_ID}/media/0", headers={"Authorization": ""})
    assert resp.status_code == 401


def test_media_stream_404_out_of_range(tmp_path: Path) -> None:
    make_meeting(tmp_path)
    resp = make_client(tmp_path).get(f"/meetings/{MEETING_ID}/media/0")
    assert resp.status_code == 404


def test_media_stream_404_negative_id(tmp_path: Path) -> None:
    meeting_dir = make_meeting(tmp_path)
    make_media_file(meeting_dir)
    card = json.loads((meeting_dir / "meeting.json").read_text())
    card["source"]["media_files"] = [{"path": "source/audio.wav", "media_type": "audio"}]
    (meeting_dir / "meeting.json").write_text(json.dumps(card))
    resp = make_client(tmp_path).get(f"/meetings/{MEETING_ID}/media/-1")
    assert resp.status_code == 404


def test_media_stream_404_non_integer_id(tmp_path: Path) -> None:
    meeting_dir = make_meeting(tmp_path)
    make_media_file(meeting_dir)
    resp = make_client(tmp_path).get(f"/meetings/{MEETING_ID}/media/foo")
    assert resp.status_code == 404


def test_media_stream_path_traversal_in_media_id(tmp_path: Path) -> None:
    meeting_dir = make_meeting(tmp_path)
    make_media_file(meeting_dir)
    card = json.loads((meeting_dir / "meeting.json").read_text())
    card["source"]["media_files"] = [{"path": "source/audio.wav", "media_type": "audio"}]
    (meeting_dir / "meeting.json").write_text(json.dumps(card))
    resp = make_client(tmp_path).get(f"/meetings/{MEETING_ID}/media/../../etc/passwd")
    assert resp.status_code in (404, 422)


def test_media_stream_correct_mime_type_mp4(tmp_path: Path) -> None:
    meeting_dir = make_meeting(tmp_path)
    source = meeting_dir / "source"
    source.mkdir(exist_ok=True)
    (source / "video.mp4").write_bytes(b"\x00\x00\x00\x20ftypmp42")
    card = json.loads((meeting_dir / "meeting.json").read_text())
    card["source"]["media_files"] = [{"path": "source/video.mp4", "media_type": "video"}]
    (meeting_dir / "meeting.json").write_text(json.dumps(card))
    resp = make_client(tmp_path).get(f"/meetings/{MEETING_ID}/media/0")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("video/mp4")


# ------------------------------------------------------------------
# GET /meetings/{id}/transcript/segments — normalized
# ------------------------------------------------------------------

def test_transcript_segments_no_transcript(tmp_path: Path) -> None:
    make_meeting(tmp_path)
    resp = make_client(tmp_path).get(f"/meetings/{MEETING_ID}/transcript/segments")
    assert resp.status_code == 200
    body = resp.json()
    assert body["meeting_id"] == MEETING_ID
    assert body["segments"] == []


def test_transcript_segments_jsonl(tmp_path: Path) -> None:
    meeting_dir = make_meeting(tmp_path)
    seg_dir = meeting_dir / "transcript"
    seg_dir.mkdir()
    segs = [
        {"start": 0.0, "end": 5.0, "speaker": "SPEAKER_01", "text": "Hello"},
        {"start": 5.5, "end": 10.0, "speaker_id": "SPEAKER_02", "text": "World"},
    ]
    (seg_dir / "segments.jsonl").write_text(
        "\n".join(json.dumps(s) for s in segs), encoding="utf-8"
    )
    card = json.loads((meeting_dir / "meeting.json").read_text())
    card["artifacts"] = {"segments": "transcript/segments.jsonl"}
    (meeting_dir / "meeting.json").write_text(json.dumps(card))

    resp = make_client(tmp_path).get(f"/meetings/{MEETING_ID}/transcript/segments")
    assert resp.status_code == 200
    body = resp.json()
    segs_out = body["segments"]
    assert len(segs_out) == 2
    assert segs_out[0]["segment_id"] == "seg-000001"
    assert segs_out[0]["start_sec"] == 0.0
    assert segs_out[0]["end_sec"] == 5.0
    assert segs_out[0]["speaker"] == "SPEAKER_01"
    assert segs_out[0]["text"] == "Hello"
    # speaker_id falls back to speaker field
    assert segs_out[1]["speaker"] == "SPEAKER_02"
    assert segs_out[1]["segment_id"] == "seg-000002"


def test_transcript_segments_requires_auth(tmp_path: Path) -> None:
    make_meeting(tmp_path)
    client = make_client(tmp_path)
    resp = client.get(f"/meetings/{MEETING_ID}/transcript/segments", headers={"Authorization": ""})
    assert resp.status_code == 401


def test_transcript_segments_404_unknown(tmp_path: Path) -> None:
    resp = make_client(tmp_path).get("/meetings/9999-99-99__ghost/transcript/segments")
    assert resp.status_code == 404


def test_transcript_segments_text_format_returns_empty(tmp_path: Path) -> None:
    meeting_dir = make_meeting(tmp_path)
    (meeting_dir / "transcript.md").write_text("Hello world", encoding="utf-8")
    card = json.loads((meeting_dir / "meeting.json").read_text())
    card["artifacts"] = {"transcript_txt": "transcript.md"}
    (meeting_dir / "meeting.json").write_text(json.dumps(card))
    resp = make_client(tmp_path).get(f"/meetings/{MEETING_ID}/transcript/segments")
    assert resp.status_code == 200
    assert resp.json()["segments"] == []


# ------------------------------------------------------------------
# GET /meetings/{id}/workspace — UI page
# ------------------------------------------------------------------

def test_workspace_returns_html(tmp_path: Path) -> None:
    make_meeting(tmp_path)
    resp = make_client(tmp_path).get(f"/meetings/{MEETING_ID}/workspace")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    body = resp.text
    assert MEETING_ID in body
    assert "media-player" in body or "audio" in body
    assert "transcript-list" in body
    assert "artifacts-panel" in body


def test_workspace_404_unknown_meeting(tmp_path: Path) -> None:
    resp = make_client(tmp_path).get("/meetings/9999-99-99__ghost/workspace")
    assert resp.status_code == 404


def test_workspace_404_invalid_id(tmp_path: Path) -> None:
    resp = make_client(tmp_path).get("/meetings/../etc/workspace")
    assert resp.status_code in (404, 422)
