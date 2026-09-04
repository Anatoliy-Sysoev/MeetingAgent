from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.meetings.service import (  # noqa: E402
    DEFAULT_MAX_TEXT_ARTIFACT_BYTES,
    DEFAULT_MAX_UPLOAD_BYTES,
    ArtifactTooLargeError,
    MeetingCardError,
    MeetingsService,
    parse_max_text_artifact_bytes,
    parse_max_upload_bytes,
)


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


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


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


def test_list_summary_fields(tmp_path: Path) -> None:
    make_card(tmp_path, data={"artifacts": {"transcript": "t.md", "memo": "m.md"}})
    svc = MeetingsService(tmp_path)
    item = svc.list_meetings()["items"][0]
    assert item["artifacts_count"] == 2
    assert set(item["artifact_keys"]) == {"transcript", "memo"}


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
    with pytest.raises(MeetingCardError):
        svc.get_meeting("2026-03-01__broken")


# ------------------------------------------------------------------
# Path traversal protection
# ------------------------------------------------------------------

@pytest.mark.parametrize("bad_id", [
    "../etc", "../../secret", "/etc/passwd", "foo/bar", "foo\\bar",
])
def test_get_meeting_traversal_rejected(tmp_path: Path, bad_id: str) -> None:
    svc = MeetingsService(tmp_path)
    assert svc.get_meeting(bad_id) is None


@pytest.mark.parametrize("bad_id", ["../etc", "/etc/passwd", "foo/bar"])
def test_list_artifacts_traversal_rejected(tmp_path: Path, bad_id: str) -> None:
    svc = MeetingsService(tmp_path)
    assert svc.list_artifacts(bad_id) is None


@pytest.mark.parametrize("bad_name", ["../secret.txt", "/etc/passwd", "foo/bar.md"])
def test_get_artifact_content_traversal_rejected(tmp_path: Path, bad_name: str) -> None:
    make_card(tmp_path)
    svc = MeetingsService(tmp_path)
    assert svc.get_artifact_content("2026-01-15__kickoff", bad_name) is None


# ------------------------------------------------------------------
# list_artifacts
# ------------------------------------------------------------------

def test_list_artifacts_exists_and_missing(tmp_path: Path) -> None:
    meeting_dir = make_card(tmp_path, data={
        "artifacts": {"transcript": "transcript.md", "memo": "memo.md"}
    })
    (meeting_dir / "transcript.md").write_text("# Transcript", encoding="utf-8")

    svc = MeetingsService(tmp_path)
    arts = svc.list_artifacts("2026-01-15__kickoff")
    assert arts is not None
    by_key = {a["key"]: a for a in arts}
    assert by_key["transcript"]["exists"] is True
    assert by_key["transcript"]["size_bytes"] > 0
    assert "T" in by_key["transcript"]["modified_at"]  # ISO-8601
    assert by_key["memo"]["exists"] is False
    assert by_key["memo"]["size_bytes"] is None
    assert by_key["memo"]["view_url"] is None


def test_list_artifacts_missing_meeting(tmp_path: Path) -> None:
    svc = MeetingsService(tmp_path)
    assert svc.list_artifacts("no-such-meeting") is None


# ------------------------------------------------------------------
# get_transcript — priority order
# ------------------------------------------------------------------

def test_get_transcript_missing_returns_available_false(tmp_path: Path) -> None:
    make_card(tmp_path, data={"artifacts": {}})
    svc = MeetingsService(tmp_path)
    result = svc.get_transcript("2026-01-15__kickoff")
    assert result is not None
    assert result.get("available") is False


def test_get_transcript_txt(tmp_path: Path) -> None:
    meeting_dir = make_card(tmp_path, data={"artifacts": {"transcript_txt": "transcript.txt"}})
    (meeting_dir / "transcript.txt").write_text("Hello world", encoding="utf-8")
    svc = MeetingsService(tmp_path)
    result = svc.get_transcript("2026-01-15__kickoff")
    assert result is not None
    assert result["format"] == "text"
    assert "Hello world" in result["content"]


def test_get_transcript_jsonl_segments(tmp_path: Path) -> None:
    meeting_dir = make_card(tmp_path, data={"artifacts": {"segments": "segments.jsonl"}})
    lines = [json.dumps({"start": 0.0, "end": 1.0, "text": "Hi"})]
    (meeting_dir / "segments.jsonl").write_text("\n".join(lines), encoding="utf-8")
    svc = MeetingsService(tmp_path)
    result = svc.get_transcript("2026-01-15__kickoff")
    assert result is not None
    assert result["format"] == "jsonl"
    assert result["segments"][0]["text"] == "Hi"


def test_get_transcript_segments_priority_over_txt(tmp_path: Path) -> None:
    meeting_dir = make_card(tmp_path, data={
        "artifacts": {"segments": "segments.jsonl", "transcript_txt": "t.txt"}
    })
    (meeting_dir / "segments.jsonl").write_text(
        json.dumps({"start": 0.0, "end": 1.0, "text": "Seg"}), encoding="utf-8"
    )
    (meeting_dir / "t.txt").write_text("plain", encoding="utf-8")
    svc = MeetingsService(tmp_path)
    result = svc.get_transcript("2026-01-15__kickoff")
    assert result is not None
    assert result["artifact"] == "segments"


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


# ------------------------------------------------------------------
# Ingest methods regression
# ------------------------------------------------------------------

def test_ingest_methods_still_present(tmp_path: Path) -> None:
    svc = MeetingsService(tmp_path)
    assert callable(svc.find_by_sha256)
    assert callable(svc.unique_meeting_id)
    assert callable(svc.create_meeting)


def test_find_by_sha256_returns_none_on_empty(tmp_path: Path) -> None:
    svc = MeetingsService(tmp_path)
    assert svc.find_by_sha256("abc123") is None


def test_unique_meeting_id_generates_candidate(tmp_path: Path) -> None:
    svc = MeetingsService(tmp_path)
    mid = svc.unique_meeting_id("2026-01-01", "test")
    assert mid == "2026-01-01__test"


# ------------------------------------------------------------------
# parse_max_text_artifact_bytes — config validation
# ------------------------------------------------------------------

def test_parse_limit_absent_returns_default() -> None:
    assert parse_max_text_artifact_bytes({}) == DEFAULT_MAX_TEXT_ARTIFACT_BYTES
    assert parse_max_text_artifact_bytes(None) == DEFAULT_MAX_TEXT_ARTIFACT_BYTES
    assert DEFAULT_MAX_TEXT_ARTIFACT_BYTES == 10 * 1024 * 1024


def test_parse_limit_absent_key_returns_default() -> None:
    assert parse_max_text_artifact_bytes({"meetings": {}}) == DEFAULT_MAX_TEXT_ARTIFACT_BYTES


def test_parse_limit_valid_positive_int() -> None:
    assert parse_max_text_artifact_bytes({"meetings": {"max_text_artifact_bytes": 4096}}) == 4096


def test_parse_limit_rejects_bool() -> None:
    with pytest.raises(ValueError):
        parse_max_text_artifact_bytes({"meetings": {"max_text_artifact_bytes": True}})


def test_parse_limit_rejects_zero() -> None:
    with pytest.raises(ValueError):
        parse_max_text_artifact_bytes({"meetings": {"max_text_artifact_bytes": 0}})


def test_parse_limit_rejects_negative() -> None:
    with pytest.raises(ValueError):
        parse_max_text_artifact_bytes({"meetings": {"max_text_artifact_bytes": -1}})


def test_parse_limit_rejects_float() -> None:
    with pytest.raises(ValueError):
        parse_max_text_artifact_bytes({"meetings": {"max_text_artifact_bytes": 1.5}})


def test_parse_limit_rejects_string() -> None:
    with pytest.raises(ValueError):
        parse_max_text_artifact_bytes({"meetings": {"max_text_artifact_bytes": "10485760"}})


def test_parse_limit_rejects_non_mapping_meetings() -> None:
    with pytest.raises(ValueError):
        parse_max_text_artifact_bytes({"meetings": ["not", "a", "map"]})


def test_parse_upload_limit_absent_returns_default() -> None:
    assert parse_max_upload_bytes({}) == DEFAULT_MAX_UPLOAD_BYTES
    assert parse_max_upload_bytes(None) == 2 * 1024 * 1024 * 1024


def test_parse_upload_limit_valid_positive_int() -> None:
    assert parse_max_upload_bytes({"meetings": {"max_upload_bytes": 4096}}) == 4096


@pytest.mark.parametrize("value", [True, False, 0, -1, 1.5, "4096"])
def test_parse_upload_limit_rejects_invalid_values(value) -> None:
    with pytest.raises(ValueError):
        parse_max_upload_bytes({"meetings": {"max_upload_bytes": value}})


def test_build_app_state_passes_limit_into_service(monkeypatch) -> None:
    import meeting_agent.api.dependencies as core_deps
    from asu_june_bot.api import dependencies as deps

    captured = {}
    real_service = core_deps.MeetingsService

    def spy(*args, **kwargs):
        captured.update(kwargs)
        return real_service(*args, **kwargs)

    monkeypatch.setattr(
        core_deps,
        "load_config",
        lambda: {
            "meetings": {
                "max_text_artifact_bytes": 2048,
                "max_upload_bytes": 8192,
            }
        },
    )
    monkeypatch.setattr(core_deps, "MeetingsService", spy)
    state = deps.build_app_state()
    try:
        assert captured.get("max_text_artifact_bytes") == 2048
        assert captured.get("max_upload_bytes") == 8192
        assert state.meetings_service.max_text_artifact_bytes == 2048
        assert state.meetings_service.max_upload_bytes == 8192
    finally:
        state.live_session_service.shutdown()


def test_build_app_state_wires_durable_job_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import meeting_agent.api.dependencies as core_deps
    from asu_june_bot.api import dependencies as deps

    monkeypatch.setattr(core_deps, "check_and_fail_if_unsafe", lambda _config: None)
    state = deps.build_app_state(
        {
            "work_root_path": tmp_path,
            "paths": {
                "auth_db": str(tmp_path / "auth.db"),
                "meetings_root": str(tmp_path / "meetings"),
                "jobs_state": "runtime/jobs.json",
                "live_sessions_state": "runtime/live.json",
                "meeting_work_lock": "runtime/meeting_work.lock",
            },
        }
    )

    try:
        assert state.job_runner.store is not None
        assert state.job_runner.store.path == (tmp_path / "runtime" / "jobs.json").resolve()
        assert state.job_runner.meetings_root == tmp_path / "meetings"
        assert state.live_session_service.store.path == (
            tmp_path / "runtime" / "live.json"
        ).resolve()
        assert state.job_runner.coordinator is state.live_session_service.coordinator
        assert state.job_runner.coordinator is not None
        assert state.job_runner.coordinator.job_store is state.job_runner.store
        assert state.job_runner.coordinator.live_store is state.live_session_service.store
        assert state.job_runner.coordinator.lock_path == (
            tmp_path / "runtime" / "meeting_work.lock"
        ).resolve()
    finally:
        state.live_session_service.shutdown()


def test_build_app_state_resolves_relative_meetings_root_under_work_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import meeting_agent.api.dependencies as core_deps
    from asu_june_bot.api import dependencies as deps

    work_root = tmp_path / "deployment"
    other_cwd = tmp_path / "other-cwd"
    work_root.mkdir()
    other_cwd.mkdir()
    monkeypatch.chdir(other_cwd)
    monkeypatch.setattr(core_deps, "check_and_fail_if_unsafe", lambda _config: None)

    state = deps.build_app_state(
        {
            "work_root_path": work_root,
            "paths": {
                "auth_db": "runtime/auth.db",
                "meetings_root": "runtime/meetings",
                "jobs_state": "runtime/jobs.json",
                "live_sessions_state": "runtime/live.json",
                "meeting_work_lock": "runtime/meeting_work.lock",
            },
        }
    )

    expected = (work_root / "runtime" / "meetings").resolve()
    try:
        assert state.meetings_service.root == expected
        assert state.job_runner.meetings_root == expected
        assert state.live_session_service.meetings_root == expected
        assert expected != (other_cwd / "runtime" / "meetings").resolve()
    finally:
        state.live_session_service.shutdown()


def test_build_app_state_preserves_absolute_meetings_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import meeting_agent.api.dependencies as core_deps
    from asu_june_bot.api import dependencies as deps

    work_root = tmp_path / "deployment"
    absolute_root = tmp_path / "external-meetings"
    work_root.mkdir()
    monkeypatch.setattr(core_deps, "check_and_fail_if_unsafe", lambda _config: None)

    state = deps.build_app_state(
        {
            "work_root_path": work_root,
            "paths": {
                "auth_db": "runtime/auth.db",
                "meetings_root": str(absolute_root),
                "jobs_state": "runtime/jobs.json",
                "live_sessions_state": "runtime/live.json",
                "meeting_work_lock": "runtime/meeting_work.lock",
            },
        }
    )

    try:
        assert state.meetings_service.root == absolute_root.resolve()
        assert state.job_runner.meetings_root == absolute_root.resolve()
        assert state.live_session_service.meetings_root == absolute_root.resolve()
    finally:
        state.live_session_service.shutdown()


# ------------------------------------------------------------------
# Bounded text artifact reads
# ------------------------------------------------------------------

def test_artifact_below_limit_succeeds(tmp_path: Path) -> None:
    meeting_dir = make_card(tmp_path, data={"artifacts": {"memo": "memo.md"}})
    (meeting_dir / "memo.md").write_text("hello", encoding="utf-8")
    svc = MeetingsService(tmp_path, max_text_artifact_bytes=100)
    result = svc.get_artifact_content("2026-01-15__kickoff", "memo")
    assert result is not None
    assert result["content"] == "hello"


def test_artifact_exactly_at_limit_succeeds(tmp_path: Path) -> None:
    meeting_dir = make_card(tmp_path, data={"artifacts": {"memo": "memo.md"}})
    payload = "a" * 32
    (meeting_dir / "memo.md").write_text(payload, encoding="utf-8")
    svc = MeetingsService(tmp_path, max_text_artifact_bytes=32)
    result = svc.get_artifact_content("2026-01-15__kickoff", "memo")
    assert result is not None
    assert result["content"] == payload


def test_artifact_one_byte_above_limit_raises(tmp_path: Path) -> None:
    meeting_dir = make_card(tmp_path, data={"artifacts": {"memo": "memo.md"}})
    (meeting_dir / "memo.md").write_text("a" * 33, encoding="utf-8")
    svc = MeetingsService(tmp_path, max_text_artifact_bytes=32)
    with pytest.raises(ArtifactTooLargeError) as exc_info:
        svc.get_artifact_content("2026-01-15__kickoff", "memo")
    exc = exc_info.value
    assert exc.artifact == "memo"
    assert exc.size_bytes == 33
    assert exc.max_bytes == 32
    # No local filesystem path leaks into the public error surface.
    assert str(tmp_path) not in str(exc)


def test_transcript_json_below_limit_parses(tmp_path: Path) -> None:
    meeting_dir = make_card(tmp_path, data={"artifacts": {"transcript_json": "t.json"}})
    (meeting_dir / "t.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    svc = MeetingsService(tmp_path, max_text_artifact_bytes=10_000)
    result = svc.get_transcript("2026-01-15__kickoff")
    assert result is not None
    assert result["format"] == "json"
    assert result["content"] == {"ok": True}


def test_transcript_jsonl_below_limit_parses(tmp_path: Path) -> None:
    meeting_dir = make_card(tmp_path, data={"artifacts": {"segments": "s.jsonl"}})
    (meeting_dir / "s.jsonl").write_text(
        json.dumps({"text": "hi"}), encoding="utf-8"
    )
    svc = MeetingsService(tmp_path, max_text_artifact_bytes=10_000)
    result = svc.get_transcript("2026-01-15__kickoff")
    assert result is not None
    assert result["format"] == "jsonl"
    assert result["segments"][0]["text"] == "hi"


def test_oversized_malformed_json_raises_size_error_first(tmp_path: Path) -> None:
    meeting_dir = make_card(tmp_path, data={"artifacts": {"transcript_json": "t.json"}})
    # Invalid JSON and oversized — size error must win over parse error.
    (meeting_dir / "t.json").write_text("{not valid json " + "x" * 100, encoding="utf-8")
    svc = MeetingsService(tmp_path, max_text_artifact_bytes=16)
    with pytest.raises(ArtifactTooLargeError):
        svc.get_transcript("2026-01-15__kickoff")


def test_oversized_malformed_jsonl_raises_size_error_first(tmp_path: Path) -> None:
    meeting_dir = make_card(tmp_path, data={"artifacts": {"segments": "s.jsonl"}})
    (meeting_dir / "s.jsonl").write_text("not json line " + "y" * 100, encoding="utf-8")
    svc = MeetingsService(tmp_path, max_text_artifact_bytes=16)
    with pytest.raises(ArtifactTooLargeError):
        svc.get_transcript("2026-01-15__kickoff")


def test_oversized_primary_candidate_not_skipped_for_fallback(tmp_path: Path) -> None:
    meeting_dir = make_card(tmp_path, data={
        "artifacts": {"segments": "segments.jsonl", "transcript_txt": "t.txt"}
    })
    # Primary (segments) is oversized; fallback is small. Must NOT fall through.
    (meeting_dir / "segments.jsonl").write_text("x" * 200, encoding="utf-8")
    (meeting_dir / "t.txt").write_text("small", encoding="utf-8")
    svc = MeetingsService(tmp_path, max_text_artifact_bytes=32)
    with pytest.raises(ArtifactTooLargeError) as exc_info:
        svc.get_transcript("2026-01-15__kickoff")
    assert exc_info.value.artifact == "segments"


def test_multibyte_utf8_enforced_on_bytes(tmp_path: Path) -> None:
    meeting_dir = make_card(tmp_path, data={"artifacts": {"memo": "memo.md"}})
    # 20 cyrillic chars = 40 bytes in UTF-8; limit of 32 bytes must reject.
    (meeting_dir / "memo.md").write_text("я" * 20, encoding="utf-8")
    svc = MeetingsService(tmp_path, max_text_artifact_bytes=32)
    with pytest.raises(ArtifactTooLargeError) as exc_info:
        svc.get_artifact_content("2026-01-15__kickoff", "memo")
    assert exc_info.value.size_bytes == 40


def test_bounded_read_catches_stale_stat(tmp_path: Path, monkeypatch) -> None:
    meeting_dir = make_card(tmp_path, data={"artifacts": {"memo": "memo.md"}})
    real_size = 33
    (meeting_dir / "memo.md").write_text("a" * real_size, encoding="utf-8")
    svc = MeetingsService(tmp_path, max_text_artifact_bytes=32)

    # Simulate a stale/under-reported stat that passes the first check.
    import stat as stat_module

    class FakeStat:
        st_size = 10  # lies: claims file is within the limit
        st_mode = stat_module.S_IFREG | 0o644  # regular file

    orig_stat = Path.stat

    def fake_stat(self, *a, **k):
        if self.name == "memo.md":
            return FakeStat()
        return orig_stat(self, *a, **k)

    monkeypatch.setattr(Path, "stat", fake_stat)
    with pytest.raises(ArtifactTooLargeError) as exc_info:
        svc.get_artifact_content("2026-01-15__kickoff", "memo")
    # Bounded max+1 read detects the real oversize; reports max+1.
    assert exc_info.value.size_bytes == 33


def test_no_partial_content_returned_when_oversized(tmp_path: Path) -> None:
    meeting_dir = make_card(tmp_path, data={"artifacts": {"memo": "memo.md"}})
    (meeting_dir / "memo.md").write_text("a" * 100, encoding="utf-8")
    svc = MeetingsService(tmp_path, max_text_artifact_bytes=32)
    with pytest.raises(ArtifactTooLargeError):
        svc.get_artifact_content("2026-01-15__kickoff", "memo")


# ------------------------------------------------------------------
# is_file() guard — non-regular filesystem objects treated as absent
# ------------------------------------------------------------------

def test_artifact_directory_with_allowed_suffix_treated_as_absent(tmp_path: Path) -> None:
    meeting_dir = make_card(tmp_path, data={"artifacts": {"memo": "memo.md"}})
    # Create a directory where the artifact file is expected.
    (meeting_dir / "memo.md").mkdir()
    svc = MeetingsService(tmp_path)
    result = svc.get_artifact_content("2026-01-15__kickoff", "memo")
    assert result is None


def test_transcript_directory_with_allowed_suffix_treated_as_absent(tmp_path: Path) -> None:
    meeting_dir = make_card(tmp_path, data={"artifacts": {"transcript_txt": "t.txt"}})
    (meeting_dir / "t.txt").mkdir()
    svc = MeetingsService(tmp_path)
    result = svc.get_transcript("2026-01-15__kickoff")
    assert result == {"artifact": None, "format": None, "content": None, "available": False}


@pytest.mark.skipif(sys.platform == "win32", reason="FIFOs not available on Windows")
def test_artifact_fifo_with_allowed_suffix_treated_as_absent(tmp_path: Path) -> None:
    import os
    meeting_dir = make_card(tmp_path, data={"artifacts": {"memo": "memo.md"}})
    fifo_path = meeting_dir / "memo.md"
    os.mkfifo(fifo_path)
    svc = MeetingsService(tmp_path)
    result = svc.get_artifact_content("2026-01-15__kickoff", "memo")
    assert result is None


@pytest.mark.skipif(sys.platform == "win32", reason="FIFOs not available on Windows")
def test_transcript_fifo_with_allowed_suffix_treated_as_absent(tmp_path: Path) -> None:
    import os
    meeting_dir = make_card(tmp_path, data={"artifacts": {"transcript_txt": "t.txt"}})
    fifo_path = meeting_dir / "t.txt"
    os.mkfifo(fifo_path)
    svc = MeetingsService(tmp_path)
    result = svc.get_transcript("2026-01-15__kickoff")
    assert result == {"artifact": None, "format": None, "content": None, "available": False}


# ------------------------------------------------------------------
# MeetingsService constructor validation for max_text_artifact_bytes
# ------------------------------------------------------------------

def test_constructor_rejects_bool_true(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="bool"):
        MeetingsService(tmp_path, max_text_artifact_bytes=True)


def test_constructor_rejects_bool_false(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="bool"):
        MeetingsService(tmp_path, max_text_artifact_bytes=False)


def test_constructor_rejects_zero(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        MeetingsService(tmp_path, max_text_artifact_bytes=0)


def test_constructor_rejects_negative(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        MeetingsService(tmp_path, max_text_artifact_bytes=-1)


def test_constructor_rejects_float(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        MeetingsService(tmp_path, max_text_artifact_bytes=1.5)  # type: ignore[arg-type]


def test_constructor_rejects_string(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        MeetingsService(tmp_path, max_text_artifact_bytes="1048576")  # type: ignore[arg-type]


def test_max_text_artifact_bytes_property_is_read_only(tmp_path: Path) -> None:
    svc = MeetingsService(tmp_path, max_text_artifact_bytes=1024)
    assert svc.max_text_artifact_bytes == 1024
    with pytest.raises(AttributeError):
        svc.max_text_artifact_bytes = 99  # type: ignore[misc]


@pytest.mark.parametrize("value", [True, False, 0, -1, 1.5, "1048576"])
def test_constructor_rejects_invalid_max_upload_bytes(tmp_path: Path, value) -> None:
    with pytest.raises(ValueError):
        MeetingsService(tmp_path, max_upload_bytes=value)  # type: ignore[arg-type]


def test_max_upload_bytes_property_is_read_only(tmp_path: Path) -> None:
    svc = MeetingsService(tmp_path, max_upload_bytes=1024)
    assert svc.max_upload_bytes == 1024
    with pytest.raises(AttributeError):
        svc.max_upload_bytes = 99  # type: ignore[misc]


# ------------------------------------------------------------------
# _artifact_map: malformed artifacts values (#88)
# ------------------------------------------------------------------

def test_list_artifacts_null_artifacts(tmp_path: Path) -> None:
    make_card(tmp_path, data={"artifacts": None})
    svc = MeetingsService(tmp_path)
    result = svc.list_artifacts("2026-01-15__kickoff")
    assert result == []


def test_list_artifacts_list_artifacts(tmp_path: Path) -> None:
    make_card(tmp_path, data={"artifacts": ["foo", "bar"]})
    svc = MeetingsService(tmp_path)
    result = svc.list_artifacts("2026-01-15__kickoff")
    assert result == []


def test_list_artifacts_string_artifacts(tmp_path: Path) -> None:
    make_card(tmp_path, data={"artifacts": "bad-string"})
    svc = MeetingsService(tmp_path)
    result = svc.list_artifacts("2026-01-15__kickoff")
    assert result == []


def test_list_artifacts_missing_artifacts_key(tmp_path: Path) -> None:
    card = dict(VALID_CARD)
    card.pop("artifacts")
    meeting_dir = tmp_path / "2026-01-15__kickoff"
    meeting_dir.mkdir(parents=True)
    (meeting_dir / "meeting.json").write_text(json.dumps(card), encoding="utf-8")
    svc = MeetingsService(tmp_path)
    result = svc.list_artifacts("2026-01-15__kickoff")
    assert result == []


def test_get_artifact_content_list_artifacts_does_not_raise(tmp_path: Path) -> None:
    make_card(tmp_path, data={"artifacts": ["foo"]})
    svc = MeetingsService(tmp_path)
    result = svc.get_artifact_content("2026-01-15__kickoff", "foo")
    assert result is None


# ---------------------------------------------------------------------------
# Bug 2: _source_map / _media_files type guards
# ---------------------------------------------------------------------------

def test_summary_source_list_does_not_raise(tmp_path: Path) -> None:
    make_card(tmp_path, data={"source": ["bad", "list"]})
    svc = MeetingsService(tmp_path)
    result = svc.get_meeting("2026-01-15__kickoff")
    assert result is not None


def test_summary_source_string_does_not_raise(tmp_path: Path) -> None:
    make_card(tmp_path, data={"source": "bad-string"})
    svc = MeetingsService(tmp_path)
    result = svc.get_meeting("2026-01-15__kickoff")
    assert result is not None


def test_list_media_source_list_returns_empty(tmp_path: Path) -> None:
    make_card(tmp_path, data={"source": ["bad"]})
    svc = MeetingsService(tmp_path)
    result = svc.list_media("2026-01-15__kickoff")
    assert result == []


def test_list_media_media_files_string_returns_empty(tmp_path: Path) -> None:
    make_card(tmp_path, data={"source": {"media_files": "bad-string"}})
    svc = MeetingsService(tmp_path)
    result = svc.list_media("2026-01-15__kickoff")
    assert result == []


def test_get_media_path_source_list_returns_none(tmp_path: Path) -> None:
    make_card(tmp_path, data={"source": ["bad"]})
    svc = MeetingsService(tmp_path)
    result = svc.get_media_path("2026-01-15__kickoff", "0")
    assert result is None


def test_get_media_path_media_files_string_returns_none(tmp_path: Path) -> None:
    make_card(tmp_path, data={"source": {"media_files": "bad-string"}})
    svc = MeetingsService(tmp_path)
    result = svc.get_media_path("2026-01-15__kickoff", "0")
    assert result is None


def test_dedup_scan_malformed_source_does_not_raise(tmp_path: Path) -> None:
    make_card(tmp_path, data={"source": "not-a-dict"})
    svc = MeetingsService(tmp_path)
    result = svc.find_by_sha256("aabbccdd")
    assert result is None


# ------------------------------------------------------------------
# speaker mapping
# ------------------------------------------------------------------


def test_get_speakers_discovers_speaker_transcript_labels(tmp_path: Path) -> None:
    meeting_dir = make_card(tmp_path)
    _write_jsonl(
        meeting_dir / "transcript" / "speaker_transcript.jsonl",
        [
            {"utterance_id": "utt-1", "speaker": "SPEAKER_02", "start": 0, "end": 1, "text": "B"},
            {"utterance_id": "utt-2", "speaker": "SPEAKER_01", "start": 1, "end": 2, "text": "A"},
        ],
    )
    svc = MeetingsService(tmp_path)

    result = svc.get_speakers("2026-01-15__kickoff")

    assert result is not None
    assert [s["speaker_label"] for s in result["speakers"]] == ["SPEAKER_01", "SPEAKER_02"]
    assert result["speakers"][0]["display_name"] == "SPEAKER_01"


def test_update_speaker_mapping_persists_to_meeting_json(tmp_path: Path) -> None:
    meeting_dir = make_card(tmp_path)
    _write_jsonl(
        meeting_dir / "transcript" / "speaker_transcript.jsonl",
        [{"speaker": "SPEAKER_01", "start": 0, "end": 1, "text": "Hello"}],
    )
    svc = MeetingsService(tmp_path)

    result = svc.update_speaker_mapping(
        "2026-01-15__kickoff",
        {"SPEAKER_01": {"name": "Иван Иванов", "role": "PO"}},
    )

    assert result is not None
    assert result["mapping"] == {"SPEAKER_01": {"name": "Иван Иванов", "role": "PO"}}
    card = json.loads((meeting_dir / "meeting.json").read_text(encoding="utf-8"))
    assert card["speaker_mapping"]["SPEAKER_01"]["name"] == "Иван Иванов"
    assert card["speaker_mapping"]["SPEAKER_01"]["role"] == "PO"
    assert card["updated_at"] != VALID_CARD["updated_at"]


def test_update_speaker_mapping_rejects_unknown_label(tmp_path: Path) -> None:
    make_card(tmp_path)
    svc = MeetingsService(tmp_path)

    with pytest.raises(ValueError, match="Invalid speaker label"):
        svc.update_speaker_mapping("2026-01-15__kickoff", {"ADMIN": {"name": "Bad"}})


def test_transcript_segments_apply_speaker_mapping_and_preserve_label(tmp_path: Path) -> None:
    meeting_dir = make_card(
        tmp_path,
        data={"speaker_mapping": {"SPEAKER_01": {"name": "Алексей Петров", "role": "Lead"}}},
    )
    _write_jsonl(
        meeting_dir / "transcript" / "speaker_transcript.jsonl",
        [
            {
                "utterance_id": "utt-000001",
                "speaker": "SPEAKER_01",
                "start": 12.5,
                "end": 14.0,
                "text": "Коллеги, начинаем.",
            }
        ],
    )
    svc = MeetingsService(tmp_path)

    result = svc.get_transcript_segments("2026-01-15__kickoff")

    assert result is not None
    segment = result["segments"][0]
    assert segment["segment_id"] == "utt-000001"
    assert segment["speaker"] == "Алексей Петров"
    assert segment["speaker_label"] == "SPEAKER_01"
    assert segment["speaker_role"] == "Lead"
    assert segment["speaker_mapped"] is True
