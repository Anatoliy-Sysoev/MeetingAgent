from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.meetings.service import MeetingsService  # noqa: E402


VALID_CARD = {
    "schema_version": 1,
    "meeting_id": "2026-01-15__kickoff",
    "title": "Kickoff Meeting",
    "date": "2026-01-15",
    "processing_status": "indexed",
    "participants": ["Alice", "Bob"],
    "source": {"kind": "offline_record", "media_files": []},
    "artifacts": {},
    "classification": {},
    "links": {},
    "retention": {"policy": "default"},
    "rag": {"index_policy": "structured_artifacts_and_final_transcript"},
    "created_at": "2026-01-15T10:00:00",
    "updated_at": "2026-01-15T11:00:00",
}


def make_card(tmp_path: Path, meeting_id: str = "2026-01-15__kickoff", data: dict | None = None) -> Path:
    card_data = dict(VALID_CARD)
    card_data["meeting_id"] = meeting_id
    if data:
        card_data.update(data)
    meeting_dir = tmp_path / meeting_id
    meeting_dir.mkdir(parents=True)
    (meeting_dir / "meeting.json").write_text(json.dumps(card_data), encoding="utf-8")
    return meeting_dir


# ------------------------------------------------------------------
# list_meetings
# ------------------------------------------------------------------

def test_list_empty_root(tmp_path: Path) -> None:
    svc = MeetingsService(tmp_path)
    result = svc.list_meetings()
    assert result["items"] == []
    assert result["total"] == 0


def test_list_nonexistent_root(tmp_path: Path) -> None:
    svc = MeetingsService(tmp_path / "does-not-exist")
    result = svc.list_meetings()
    assert result["items"] == []
    assert result["total"] == 0


def test_list_one_valid_card(tmp_path: Path) -> None:
    make_card(tmp_path)
    svc = MeetingsService(tmp_path)
    result = svc.list_meetings()
    assert result["total"] == 1
    assert result["items"][0]["meeting_id"] == "2026-01-15__kickoff"
    assert result["items"][0]["title"] == "Kickoff Meeting"
    assert result["items"][0]["processing_status"] == "indexed"


def test_list_broken_card_skips_with_error(tmp_path: Path) -> None:
    make_card(tmp_path)
    bad_dir = tmp_path / "2026-02-01__bad"
    bad_dir.mkdir()
    (bad_dir / "meeting.json").write_text("not json!!!", encoding="utf-8")
    svc = MeetingsService(tmp_path)
    result = svc.list_meetings()
    assert result["total"] == 1
    assert "errors" in result
    assert any("2026-02-01__bad" in e["meeting_id"] for e in result["errors"])


def test_list_pagination(tmp_path: Path) -> None:
    for i in range(5):
        make_card(tmp_path, f"2026-0{i+1}-01__mtg{i}")
    svc = MeetingsService(tmp_path)
    result = svc.list_meetings(offset=2, limit=2)
    assert len(result["items"]) == 2
    assert result["total"] == 5
    assert result["offset"] == 2
    assert result["limit"] == 2


# ------------------------------------------------------------------
# get_meeting
# ------------------------------------------------------------------

def test_get_existing_meeting(tmp_path: Path) -> None:
    make_card(tmp_path)
    svc = MeetingsService(tmp_path)
    data = svc.get_meeting("2026-01-15__kickoff")
    assert data is not None
    assert data["meeting_id"] == "2026-01-15__kickoff"


def test_get_missing_meeting_returns_none(tmp_path: Path) -> None:
    svc = MeetingsService(tmp_path)
    assert svc.get_meeting("2026-99-99__missing") is None


def test_get_broken_meeting_raises(tmp_path: Path) -> None:
    bad_dir = tmp_path / "2026-03-01__broken"
    bad_dir.mkdir()
    (bad_dir / "meeting.json").write_text("{bad json", encoding="utf-8")
    svc = MeetingsService(tmp_path)
    with pytest.raises(Exception):
        svc.get_meeting("2026-03-01__broken")


# ------------------------------------------------------------------
# Path traversal protection
# ------------------------------------------------------------------

@pytest.mark.parametrize("bad_id", [
    "../etc",
    "../../secret",
    "/etc/passwd",
    "foo/bar",
    "foo\\bar",
])
def test_get_meeting_traversal_rejected(tmp_path: Path, bad_id: str) -> None:
    svc = MeetingsService(tmp_path)
    assert svc.get_meeting(bad_id) is None


@pytest.mark.parametrize("bad_id", [
    "../etc",
    "/etc/passwd",
    "foo/bar",
])
def test_list_artifacts_traversal_rejected(tmp_path: Path, bad_id: str) -> None:
    svc = MeetingsService(tmp_path)
    assert svc.list_artifacts(bad_id) is None


@pytest.mark.parametrize("bad_name", [
    "../secret.txt",
    "/etc/passwd",
    "foo/bar.md",
])
def test_get_artifact_content_traversal_rejected(tmp_path: Path, bad_name: str) -> None:
    make_card(tmp_path)
    svc = MeetingsService(tmp_path)
    result = svc.get_artifact_content("2026-01-15__kickoff", bad_name)
    assert result is None


# ------------------------------------------------------------------
# list_artifacts
# ------------------------------------------------------------------

def test_list_artifacts_exists_and_missing(tmp_path: Path) -> None:
    meeting_dir = make_card(tmp_path, data={
        "artifacts": {
            "transcript": "transcript.md",
            "memo": "memo.md",
        }
    })
    (meeting_dir / "transcript.md").write_text("# Transcript", encoding="utf-8")
    # memo.md intentionally absent

    svc = MeetingsService(tmp_path)
    arts = svc.list_artifacts("2026-01-15__kickoff")
    assert arts is not None
    by_key = {a["key"]: a for a in arts}
    assert by_key["transcript"]["exists"] is True
    assert by_key["transcript"]["size_bytes"] > 0
    assert isinstance(by_key["transcript"]["modified_at"], str)
    assert "T" in by_key["transcript"]["modified_at"]  # ISO-8601
    assert by_key["memo"]["exists"] is False
    assert "size_bytes" not in by_key["memo"]


def test_list_artifacts_missing_meeting(tmp_path: Path) -> None:
    svc = MeetingsService(tmp_path)
    assert svc.list_artifacts("no-such-meeting") is None


# ------------------------------------------------------------------
# get_transcript
# ------------------------------------------------------------------

def test_get_transcript_missing_returns_available_false(tmp_path: Path) -> None:
    make_card(tmp_path, data={"artifacts": {}})
    svc = MeetingsService(tmp_path)
    result = svc.get_transcript("2026-01-15__kickoff")
    assert result is not None
    assert result.get("available") is False or result.get("content") is None


def test_get_transcript_txt(tmp_path: Path) -> None:
    meeting_dir = make_card(tmp_path, data={"artifacts": {"transcript_txt": "transcript.txt"}})
    (meeting_dir / "transcript.txt").write_text("Hello world", encoding="utf-8")
    svc = MeetingsService(tmp_path)
    result = svc.get_transcript("2026-01-15__kickoff")
    assert result is not None
    assert result["format"] == "text"
    assert "Hello world" in result["content"]


def test_get_transcript_jsonl(tmp_path: Path) -> None:
    meeting_dir = make_card(tmp_path, data={"artifacts": {"segments": "segments.jsonl"}})
    lines = [json.dumps({"start": 0.0, "end": 1.0, "text": "Hi"})]
    (meeting_dir / "segments.jsonl").write_text("\n".join(lines), encoding="utf-8")
    svc = MeetingsService(tmp_path)
    result = svc.get_transcript("2026-01-15__kickoff")
    assert result is not None
    assert result["format"] == "jsonl"
    assert result["segments"][0]["text"] == "Hi"


def test_get_transcript_missing_meeting_returns_none(tmp_path: Path) -> None:
    svc = MeetingsService(tmp_path)
    assert svc.get_transcript("no-such-id") is None


# ------------------------------------------------------------------
# get_artifact_content
# ------------------------------------------------------------------

def test_get_artifact_content_text(tmp_path: Path) -> None:
    meeting_dir = make_card(tmp_path, data={"artifacts": {"memo": "memo.md"}})
    (meeting_dir / "memo.md").write_text("## Memo content", encoding="utf-8")
    svc = MeetingsService(tmp_path)
    result = svc.get_artifact_content("2026-01-15__kickoff", "memo")
    assert result is not None
    assert "Memo content" in result["content"]


def test_get_artifact_binary_returns_error(tmp_path: Path) -> None:
    meeting_dir = make_card(tmp_path, data={"artifacts": {"video": "rec.mp4"}})
    (meeting_dir / "rec.mp4").write_bytes(b"\x00\x01\x02")
    svc = MeetingsService(tmp_path)
    result = svc.get_artifact_content("2026-01-15__kickoff", "video")
    assert result is not None
    assert result.get("error") == "binary_artifact"


def test_get_artifact_not_in_manifest(tmp_path: Path) -> None:
    make_card(tmp_path)
    svc = MeetingsService(tmp_path)
    assert svc.get_artifact_content("2026-01-15__kickoff", "nonexistent") is None
