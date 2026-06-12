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
from asu_june_bot.auth.repository import AuthRepository  # noqa: E402
from asu_june_bot.auth.service import LocalAuthService  # noqa: E402
from asu_june_bot.auth.throttle import LoginThrottle  # noqa: E402
from asu_june_bot.meetings.service import MeetingsService  # noqa: E402

TOKEN = "test-meetings-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


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

MEETING_ID = "2026-01-15__kickoff"


@dataclass(slots=True)
class FakeState:
    meetings_service: MeetingsService
    local_auth_service: LocalAuthService
    login_throttle: LoginThrottle = field(default_factory=LoginThrottle)


def make_client(meetings_root: Path, max_text_artifact_bytes: int | None = None) -> TestClient:
    import os
    os.environ["MEETINGAGENT_API_TOKEN"] = TOKEN
    repo = AuthRepository(meetings_root / "_auth.db")
    repo.initialize()
    app = create_app()
    client = TestClient(app, raise_server_exceptions=False, headers=AUTH)
    svc_kwargs = {}
    if max_text_artifact_bytes is not None:
        svc_kwargs["max_text_artifact_bytes"] = max_text_artifact_bytes
    app.state.asu_june_bot = FakeState(
        meetings_service=MeetingsService(meetings_root, **svc_kwargs),
        local_auth_service=LocalAuthService(repo),
    )
    return client


def make_meeting(
    tmp_path: Path, meeting_id: str = MEETING_ID, extra: dict | None = None
) -> Path:
    data = dict(VALID_CARD)
    data["meeting_id"] = meeting_id
    if extra:
        data.update(extra)
    d = tmp_path / meeting_id
    d.mkdir(parents=True)
    (d / "meeting.json").write_text(json.dumps(data), encoding="utf-8")
    return d


def make_broken(tmp_path: Path, meeting_id: str = "2026-03-01__broken") -> None:
    d = tmp_path / meeting_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "meeting.json").write_text("{bad json", encoding="utf-8")


# ------------------------------------------------------------------
# GET /meetings
# ------------------------------------------------------------------

def test_list_empty(tmp_path: Path) -> None:
    resp = make_client(tmp_path).get("/meetings")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0


def test_list_one_meeting(tmp_path: Path) -> None:
    make_meeting(tmp_path)
    resp = make_client(tmp_path).get("/meetings")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["meeting_id"] == MEETING_ID
    assert items[0]["title"] == "Kickoff Meeting"


def test_list_pagination(tmp_path: Path) -> None:
    for i in range(3):
        make_meeting(tmp_path, f"2026-0{i+1}-01__m{i}")
    resp = make_client(tmp_path).get("/meetings?limit=2&offset=1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2


# ------------------------------------------------------------------
# GET /meetings/{meeting_id}
# ------------------------------------------------------------------

def test_get_existing(tmp_path: Path) -> None:
    make_meeting(tmp_path)
    resp = make_client(tmp_path).get(f"/meetings/{MEETING_ID}")
    assert resp.status_code == 200
    assert resp.json()["meeting_id"] == MEETING_ID


def test_get_missing_404(tmp_path: Path) -> None:
    resp = make_client(tmp_path).get("/meetings/2099-99-99__gone")
    assert resp.status_code == 404


def test_get_broken_card_422(tmp_path: Path) -> None:
    make_broken(tmp_path)
    assert make_client(tmp_path).get("/meetings/2026-03-01__broken").status_code == 422


# ------------------------------------------------------------------
# Malformed card — all sub-routes → 422
# ------------------------------------------------------------------

def test_transcript_broken_card_422(tmp_path: Path) -> None:
    make_broken(tmp_path)
    assert make_client(tmp_path).get("/meetings/2026-03-01__broken/transcript").status_code == 422


def test_artifacts_broken_card_422(tmp_path: Path) -> None:
    make_broken(tmp_path)
    assert make_client(tmp_path).get("/meetings/2026-03-01__broken/artifacts").status_code == 422


def test_artifact_content_broken_card_422(tmp_path: Path) -> None:
    make_broken(tmp_path)
    assert make_client(tmp_path).get("/meetings/2026-03-01__broken/artifacts/memo").status_code == 422


# ------------------------------------------------------------------
# GET /meetings/{meeting_id}/transcript
# ------------------------------------------------------------------

def test_transcript_missing_artifact_returns_available_false(tmp_path: Path) -> None:
    make_meeting(tmp_path)
    resp = make_client(tmp_path).get(f"/meetings/{MEETING_ID}/transcript")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("available") is False


def test_transcript_present(tmp_path: Path) -> None:
    d = make_meeting(tmp_path, extra={"artifacts": {"transcript_txt": "t.txt"}})
    (d / "t.txt").write_text("Hello transcript", encoding="utf-8")
    resp = make_client(tmp_path).get(f"/meetings/{MEETING_ID}/transcript")
    assert resp.status_code == 200
    assert "Hello transcript" in resp.json()["content"]


def test_transcript_missing_meeting_404(tmp_path: Path) -> None:
    assert make_client(tmp_path).get("/meetings/no-such/transcript").status_code == 404


# ------------------------------------------------------------------
# GET /meetings/{meeting_id}/artifacts
# ------------------------------------------------------------------

def test_artifacts_list(tmp_path: Path) -> None:
    d = make_meeting(tmp_path, extra={"artifacts": {"transcript": "t.md", "memo": "memo.md"}})
    (d / "t.md").write_text("text", encoding="utf-8")
    resp = make_client(tmp_path).get(f"/meetings/{MEETING_ID}/artifacts")
    assert resp.status_code == 200
    arts = {a["key"]: a for a in resp.json()["artifacts"]}
    assert arts["transcript"]["exists"] is True
    assert arts["memo"]["exists"] is False


def test_artifacts_missing_meeting(tmp_path: Path) -> None:
    assert make_client(tmp_path).get("/meetings/no-such/artifacts").status_code == 404


# ------------------------------------------------------------------
# GET /meetings/{meeting_id}/artifacts/{artifact_name}
# ------------------------------------------------------------------

def test_artifact_content(tmp_path: Path) -> None:
    d = make_meeting(tmp_path, extra={"artifacts": {"memo": "memo.md"}})
    (d / "memo.md").write_text("## Summary", encoding="utf-8")
    resp = make_client(tmp_path).get(f"/meetings/{MEETING_ID}/artifacts/memo")
    assert resp.status_code == 200
    assert "Summary" in resp.json()["content"]


def test_artifact_binary_415(tmp_path: Path) -> None:
    d = make_meeting(tmp_path, extra={"artifacts": {"video": "rec.mp4"}})
    (d / "rec.mp4").write_bytes(b"\x00\x01")
    resp = make_client(tmp_path).get(f"/meetings/{MEETING_ID}/artifacts/video")
    assert resp.status_code == 415


def test_artifact_not_found(tmp_path: Path) -> None:
    make_meeting(tmp_path)
    assert make_client(tmp_path).get(f"/meetings/{MEETING_ID}/artifacts/phantom").status_code == 404


# ------------------------------------------------------------------
# Size limits → 413
# ------------------------------------------------------------------

def test_oversized_transcript_returns_413(tmp_path: Path) -> None:
    d = make_meeting(tmp_path, extra={"artifacts": {"segments": "s.jsonl"}})
    (d / "s.jsonl").write_text("x" * 200, encoding="utf-8")
    resp = make_client(tmp_path, max_text_artifact_bytes=32).get(
        f"/meetings/{MEETING_ID}/transcript"
    )
    assert resp.status_code == 413
    detail = resp.json()["detail"]
    assert detail["error"] == "artifact_too_large"
    assert detail["artifact"] == "segments"
    assert detail["max_bytes"] == 32
    assert detail["size_bytes"] >= 33


def test_oversized_artifact_returns_413(tmp_path: Path) -> None:
    d = make_meeting(tmp_path, extra={"artifacts": {"memo": "memo.md"}})
    (d / "memo.md").write_text("a" * 200, encoding="utf-8")
    resp = make_client(tmp_path, max_text_artifact_bytes=32).get(
        f"/meetings/{MEETING_ID}/artifacts/memo"
    )
    assert resp.status_code == 413
    detail = resp.json()["detail"]
    assert detail["error"] == "artifact_too_large"
    assert detail["artifact"] == "memo"
    assert detail["size_bytes"] >= 33
    assert detail["max_bytes"] == 32


def test_413_detail_has_no_path_or_content(tmp_path: Path) -> None:
    d = make_meeting(tmp_path, extra={"artifacts": {"memo": "memo.md"}})
    (d / "memo.md").write_text("SECRETCONTENT" * 50, encoding="utf-8")
    resp = make_client(tmp_path, max_text_artifact_bytes=32).get(
        f"/meetings/{MEETING_ID}/artifacts/memo"
    )
    assert resp.status_code == 413
    body = resp.text
    assert str(tmp_path) not in body
    assert "SECRETCONTENT" not in body
    assert "memo.md" not in body  # local path/filename, only the API key is exposed


def test_exact_limit_artifact_returns_200(tmp_path: Path) -> None:
    d = make_meeting(tmp_path, extra={"artifacts": {"memo": "memo.md"}})
    (d / "memo.md").write_text("a" * 32, encoding="utf-8")
    resp = make_client(tmp_path, max_text_artifact_bytes=32).get(
        f"/meetings/{MEETING_ID}/artifacts/memo"
    )
    assert resp.status_code == 200
    assert resp.json()["content"] == "a" * 32


def test_unauthorized_oversized_artifact_fails_auth_not_size(tmp_path: Path) -> None:
    d = make_meeting(tmp_path, extra={"artifacts": {"memo": "memo.md"}})
    (d / "memo.md").write_text("a" * 200, encoding="utf-8")
    client = make_client(tmp_path, max_text_artifact_bytes=32)
    resp = client.get(
        f"/meetings/{MEETING_ID}/artifacts/memo", headers={"Authorization": ""}
    )
    assert resp.status_code == 401
    # No size metadata leaked to an unauthenticated caller.
    assert "artifact_too_large" not in resp.text


# ------------------------------------------------------------------
# Path traversal
# ------------------------------------------------------------------

@pytest.mark.parametrize("bad_id", ["..%2Fetc", "%2Fetc%2Fpasswd", "foo%2Fbar"])
def test_meeting_id_traversal_rejected(tmp_path: Path, bad_id: str) -> None:
    resp = make_client(tmp_path).get(f"/meetings/{bad_id}")
    assert resp.status_code in (400, 404, 422)


def test_artifact_name_traversal_rejected(tmp_path: Path) -> None:
    make_meeting(tmp_path)
    # artifact_name with ".." — service returns None → 404
    resp = make_client(tmp_path).get(f"/meetings/{MEETING_ID}/artifacts/..%2Fsecret")
    assert resp.status_code in (400, 404, 422)


# ------------------------------------------------------------------
# Regression: existing routes still registered
# ------------------------------------------------------------------

def test_ingest_route_still_registered(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    # POST /meetings/ingest without auth → 401 or 500 (env token not set), not 404
    resp = client.post("/meetings/ingest")
    assert resp.status_code != 404


def test_jobs_route_still_registered(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    # POST without auth → 401 or 500, not 404
    resp = client.post("/meetings/some-id/jobs/transcribe")
    assert resp.status_code != 404
