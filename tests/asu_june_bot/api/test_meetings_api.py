from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[4]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.api.app import create_app  # noqa: E402
from asu_june_bot.meetings.service import MeetingsService  # noqa: E402


VALID_CARD = {
    "schema_version": 1,
    "meeting_id": "2026-01-15__kickoff",
    "title": "Kickoff Meeting",
    "date": "2026-01-15",
    "processing_status": "indexed",
    "participants": ["Alice"],
    "source": {"kind": "offline_record"},
    "artifacts": {},
    "classification": {},
    "links": {},
    "retention": {"policy": "default"},
    "rag": {"index_policy": "structured_artifacts_and_final_transcript"},
    "created_at": "2026-01-15T10:00:00",
    "updated_at": "2026-01-15T11:00:00",
}


@dataclass(slots=True)
class FakeState:
    meetings_service: MeetingsService


def make_client(meetings_root: Path) -> TestClient:
    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)
    # Inject fake state with only meetings_service (other services unused for these tests)
    app.state.asu_june_bot = FakeState(meetings_service=MeetingsService(meetings_root))
    return client


def make_meeting(tmp_path: Path, meeting_id: str = "2026-01-15__kickoff", extra: dict | None = None) -> Path:
    data = dict(VALID_CARD)
    data["meeting_id"] = meeting_id
    if extra:
        data.update(extra)
    d = tmp_path / meeting_id
    d.mkdir(parents=True)
    (d / "meeting.json").write_text(json.dumps(data), encoding="utf-8")
    return d


# ------------------------------------------------------------------
# GET /meetings
# ------------------------------------------------------------------

def test_list_empty(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    resp = client.get("/meetings")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0


def test_list_one_meeting(tmp_path: Path) -> None:
    make_meeting(tmp_path)
    client = make_client(tmp_path)
    resp = client.get("/meetings")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["meeting_id"] == "2026-01-15__kickoff"
    assert items[0]["title"] == "Kickoff Meeting"


def test_list_pagination(tmp_path: Path) -> None:
    for i in range(3):
        make_meeting(tmp_path, f"2026-0{i+1}-01__m{i}")
    client = make_client(tmp_path)
    resp = client.get("/meetings?limit=2&offset=1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2


# ------------------------------------------------------------------
# GET /meetings/{meeting_id}
# ------------------------------------------------------------------

def test_get_existing(tmp_path: Path) -> None:
    make_meeting(tmp_path)
    client = make_client(tmp_path)
    resp = client.get("/meetings/2026-01-15__kickoff")
    assert resp.status_code == 200
    assert resp.json()["meeting_id"] == "2026-01-15__kickoff"


def test_get_missing_404(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    resp = client.get("/meetings/2099-99-99__gone")
    assert resp.status_code == 404


# ------------------------------------------------------------------
# Path traversal
# ------------------------------------------------------------------

@pytest.mark.parametrize("bad_id", ["..%2Fetc", "%2Fetc%2Fpasswd", "foo%2Fbar"])
def test_traversal_rejected(tmp_path: Path, bad_id: str) -> None:
    client = make_client(tmp_path)
    # FastAPI will decode %2F → '/' in path segments → 404 or blocked
    resp = client.get(f"/meetings/{bad_id}")
    assert resp.status_code in (400, 404, 422)


# ------------------------------------------------------------------
# GET /meetings/{meeting_id}/artifacts
# ------------------------------------------------------------------

def test_artifacts_list(tmp_path: Path) -> None:
    d = make_meeting(tmp_path, extra={"artifacts": {"transcript": "t.md", "memo": "memo.md"}})
    (d / "t.md").write_text("text", encoding="utf-8")
    client = make_client(tmp_path)
    resp = client.get("/meetings/2026-01-15__kickoff/artifacts")
    assert resp.status_code == 200
    arts = {a["key"]: a for a in resp.json()["artifacts"]}
    assert arts["transcript"]["exists"] is True
    assert arts["memo"]["exists"] is False


def test_artifacts_missing_meeting(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    assert client.get("/meetings/no-such/artifacts").status_code == 404


# ------------------------------------------------------------------
# GET /meetings/{meeting_id}/transcript
# ------------------------------------------------------------------

def test_transcript_missing_artifact(tmp_path: Path) -> None:
    make_meeting(tmp_path)
    client = make_client(tmp_path)
    resp = client.get("/meetings/2026-01-15__kickoff/transcript")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("available") is False or body.get("content") is None


def test_transcript_present(tmp_path: Path) -> None:
    d = make_meeting(tmp_path, extra={"artifacts": {"transcript_txt": "t.txt"}})
    (d / "t.txt").write_text("Hello transcript", encoding="utf-8")
    client = make_client(tmp_path)
    resp = client.get("/meetings/2026-01-15__kickoff/transcript")
    assert resp.status_code == 200
    assert "Hello transcript" in resp.json()["content"]


def test_transcript_missing_meeting(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    assert client.get("/meetings/no-such/transcript").status_code == 404


# ------------------------------------------------------------------
# GET /meetings/{meeting_id}/artifacts/{artifact_name}
# ------------------------------------------------------------------

def test_artifact_content(tmp_path: Path) -> None:
    d = make_meeting(tmp_path, extra={"artifacts": {"memo": "memo.md"}})
    (d / "memo.md").write_text("## Summary", encoding="utf-8")
    client = make_client(tmp_path)
    resp = client.get("/meetings/2026-01-15__kickoff/artifacts/memo")
    assert resp.status_code == 200
    assert "Summary" in resp.json()["content"]


def test_artifact_binary_returns_415(tmp_path: Path) -> None:
    d = make_meeting(tmp_path, extra={"artifacts": {"video": "rec.mp4"}})
    (d / "rec.mp4").write_bytes(b"\x00\x01")
    client = make_client(tmp_path)
    resp = client.get("/meetings/2026-01-15__kickoff/artifacts/video")
    assert resp.status_code == 415


def test_artifact_not_found(tmp_path: Path) -> None:
    make_meeting(tmp_path)
    client = make_client(tmp_path)
    assert client.get("/meetings/2026-01-15__kickoff/artifacts/phantom").status_code == 404
