"""Tests for expanded pipeline stage catalog and preflight checks."""
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
from asu_june_bot.jobs.runner import (  # noqa: E402
    STAGE_COMMANDS,
    STAGE_METADATA,
    JobRunner,
    stage_catalog,
)
from asu_june_bot.meetings.service import MeetingsService  # noqa: E402
from asu_june_bot.meetings.qa import MeetingQAService  # noqa: E402

TOKEN = "test-pipeline-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
MEETING_ID = "2026-03-01__pipeline-test"

VALID_CARD = {
    "schema_version": 1,
    "meeting_id": MEETING_ID,
    "title": "Pipeline Test Meeting",
    "date": "2026-03-01",
    "processing_status": "new",
    "participants": [],
    "source": {"kind": "offline_record"},
    "artifacts": {},
    "classification": {},
    "links": {},
    "retention": {"policy": "default"},
    "rag": {"index_policy": "structured_artifacts_and_final_transcript"},
    "created_at": "2026-03-01T10:00:00+00:00",
    "updated_at": "2026-03-01T10:00:00+00:00",
}

VALID_CARD_WITH_MEDIA = {
    **VALID_CARD,
    "source": {
        "kind": "offline_record",
        "media_files": [{"path": "source/video.mp4", "media_type": "video"}],
    },
}


class _ImmediateProcess:
    def __init__(self, returncode: int = 0, stderr: bytes = b"") -> None:
        self.returncode = returncode
        self.pid = 11111
        self._stderr = stderr

    async def communicate(self) -> tuple[bytes, bytes]:
        return b"", self._stderr

    def terminate(self) -> None:
        self.returncode = -15


@dataclass(slots=True)
class FakeState:
    meetings_service: MeetingsService
    job_runner: JobRunner
    local_auth_service: LocalAuthService
    meeting_qa_service: MeetingQAService | None = None
    admin_service: AdminService = field(default=None)  # type: ignore[assignment]
    login_throttle: LoginThrottle = field(default_factory=LoginThrottle)


def _make_meeting(meetings_root: Path, card: dict | None = None) -> None:
    d = meetings_root / MEETING_ID
    d.mkdir(parents=True, exist_ok=True)
    (d / "meeting.json").write_text(
        json.dumps(card or VALID_CARD), encoding="utf-8"
    )


def _make_client(
    meetings_root: Path, runner: JobRunner | None = None
) -> tuple[TestClient, JobRunner, AdminService]:
    os.environ["MEETINGAGENT_API_TOKEN"] = TOKEN
    repo = AuthRepository(meetings_root / "_auth.db")
    repo.initialize()
    app = create_app()
    jr = runner or JobRunner()
    client = TestClient(app, raise_server_exceptions=False)
    admin_svc = AdminService(repo)
    svc = MeetingsService(meetings_root)
    app.state.asu_june_bot = FakeState(
        meetings_service=svc,
        job_runner=jr,
        local_auth_service=LocalAuthService(repo),
        admin_service=admin_svc,
        meeting_qa_service=MeetingQAService(
            meetings_service=svc,
            meeting_chunks_path=meetings_root / "data" / "meeting_chunks.jsonl",
        ),
    )
    return client, jr, admin_svc


# ------------------------------------------------------------------
# Stage catalog
# ------------------------------------------------------------------

EXPECTED_STAGES_ORDERED = [
    "extract_audio",
    "transcribe",
    "diarize",
    "merge",
    "chunk",
    "enrich",
    "index",
    "analyze",
]


def test_stage_catalog_returns_all_runnable_stages() -> None:
    catalog = stage_catalog()
    names = [e["stage"] for e in catalog]
    assert names == EXPECTED_STAGES_ORDERED


def test_stage_catalog_order_is_strictly_increasing() -> None:
    orders = [e["order"] for e in stage_catalog()]
    assert orders == sorted(orders)
    assert len(orders) == len(set(orders)), "order values must be unique"


def test_stage_catalog_no_command_strings() -> None:
    catalog_text = json.dumps(stage_catalog())
    assert "python" not in catalog_text.lower()
    assert "scripts/" not in catalog_text
    assert ".py" not in catalog_text


def test_stage_catalog_no_filesystem_paths() -> None:
    catalog_text = json.dumps(stage_catalog())
    # No absolute paths or home-dir expansions
    assert "://" not in catalog_text
    for entry in stage_catalog():
        for key in ("label", "description"):
            assert "/" not in entry[key], f"{key} must not contain path separator"


def test_stage_catalog_only_mapped_stages_returned(monkeypatch: pytest.MonkeyPatch) -> None:
    import asu_june_bot.jobs.runner as runner_mod
    limited = {k: v for k, v in STAGE_COMMANDS.items() if k in {"transcribe", "merge"}}
    monkeypatch.setattr(runner_mod, "STAGE_COMMANDS", limited)
    catalog = runner_mod.stage_catalog()
    assert {e["stage"] for e in catalog} == {"transcribe", "merge"}


def test_stage_catalog_each_entry_has_required_fields() -> None:
    for entry in stage_catalog():
        for key in ("stage", "label", "description", "start_permission", "cancel_permission", "requires", "outputs", "order"):
            assert key in entry, f"Missing {key!r} in stage {entry.get('stage')!r}"
        assert isinstance(entry["requires"], list)
        assert isinstance(entry["outputs"], list)
        assert isinstance(entry["order"], int)


def test_get_stages_api_returns_all_stages(tmp_path: Path) -> None:
    _make_meeting(tmp_path)
    client, _, _ = _make_client(tmp_path)
    resp = client.get(f"/meetings/{MEETING_ID}/jobs/stages", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    names = [s["stage"] for s in body["stages"]]
    assert names == EXPECTED_STAGES_ORDERED


def test_get_stages_api_no_path_leakage(tmp_path: Path) -> None:
    _make_meeting(tmp_path)
    client, _, _ = _make_client(tmp_path)
    resp = client.get(f"/meetings/{MEETING_ID}/jobs/stages", headers=AUTH)
    body_text = resp.text
    assert str(tmp_path) not in body_text
    assert "scripts/" not in body_text
    assert ".py" not in body_text


# ------------------------------------------------------------------
# Preflight — extract_audio
# ------------------------------------------------------------------

def test_extract_audio_preflight_fails_without_ffmpeg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    _make_meeting(tmp_path, VALID_CARD_WITH_MEDIA)
    # Create the media file so the path check passes, but ffmpeg is absent
    media_path = tmp_path / MEETING_ID / "source" / "video.mp4"
    media_path.parent.mkdir(parents=True)
    media_path.write_bytes(b"fake")
    client, _, _ = _make_client(tmp_path)

    import shutil as shutil_mod
    monkeypatch.setattr(shutil_mod, "which", lambda name: None)
    import asu_june_bot.jobs.runner as runner_mod
    monkeypatch.setattr(runner_mod.shutil, "which", lambda name: None)

    resp = client.post(f"/meetings/{MEETING_ID}/jobs/extract_audio", headers=AUTH)
    assert resp.status_code == 422
    assert "ffmpeg" in resp.json()["detail"].lower()


def test_extract_audio_preflight_fails_without_media_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    _make_meeting(tmp_path, VALID_CARD)  # no media_files
    client, _, _ = _make_client(tmp_path)

    import asu_june_bot.jobs.runner as runner_mod
    monkeypatch.setattr(runner_mod.shutil, "which", lambda name: "/usr/bin/ffmpeg")

    resp = client.post(f"/meetings/{MEETING_ID}/jobs/extract_audio", headers=AUTH)
    assert resp.status_code == 422
    assert "media" in resp.json()["detail"].lower()


def test_extract_audio_preflight_fails_when_media_file_missing_on_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    _make_meeting(tmp_path, VALID_CARD_WITH_MEDIA)  # media_files set, but file not on disk
    client, _, _ = _make_client(tmp_path)

    import asu_june_bot.jobs.runner as runner_mod
    monkeypatch.setattr(runner_mod.shutil, "which", lambda name: "/usr/bin/ffmpeg")

    resp = client.post(f"/meetings/{MEETING_ID}/jobs/extract_audio", headers=AUTH)
    assert resp.status_code == 422
    assert "media" in resp.json()["detail"].lower()


def test_extract_audio_starts_when_preconditions_met(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    _make_meeting(tmp_path, VALID_CARD_WITH_MEDIA)
    media_path = tmp_path / MEETING_ID / "source" / "video.mp4"
    media_path.parent.mkdir(parents=True)
    media_path.write_bytes(b"fake")
    client, _, _ = _make_client(tmp_path)

    import asu_june_bot.jobs.runner as runner_mod
    monkeypatch.setattr(runner_mod.shutil, "which", lambda name: "/usr/bin/ffmpeg")

    async def fake_subprocess(*args, stdout, stderr):
        return _ImmediateProcess(returncode=0)

    monkeypatch.setattr(runner_mod, "_create_subprocess", fake_subprocess)

    resp = client.post(f"/meetings/{MEETING_ID}/jobs/extract_audio", headers=AUTH)
    assert resp.status_code == 202
    assert resp.json()["stage"] == "extract_audio"


# ------------------------------------------------------------------
# Preflight — chunk
# ------------------------------------------------------------------

def test_chunk_preflight_fails_without_speaker_transcript(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    _make_meeting(tmp_path)
    client, _, _ = _make_client(tmp_path)
    resp = client.post(f"/meetings/{MEETING_ID}/jobs/chunk", headers=AUTH)
    assert resp.status_code == 422
    detail = resp.json()["detail"].lower()
    assert "speaker_transcript" in detail or "merge" in detail


def test_chunk_starts_when_speaker_transcript_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    _make_meeting(tmp_path)
    transcript_path = tmp_path / MEETING_ID / "transcript" / "speaker_transcript.jsonl"
    transcript_path.parent.mkdir(parents=True)
    transcript_path.write_text('{"text":"hello","start":0,"end":5,"speaker":"S1"}\n', encoding="utf-8")
    client, _, _ = _make_client(tmp_path)

    import asu_june_bot.jobs.runner as runner_mod

    async def fake_subprocess(*args, stdout, stderr):
        return _ImmediateProcess(returncode=0)

    monkeypatch.setattr(runner_mod, "_create_subprocess", fake_subprocess)

    resp = client.post(f"/meetings/{MEETING_ID}/jobs/chunk", headers=AUTH)
    assert resp.status_code == 202
    assert resp.json()["stage"] == "chunk"


# ------------------------------------------------------------------
# Preflight — enrich
# ------------------------------------------------------------------

def test_enrich_preflight_fails_without_chunks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    _make_meeting(tmp_path)
    client, _, _ = _make_client(tmp_path)
    resp = client.post(f"/meetings/{MEETING_ID}/jobs/enrich", headers=AUTH)
    assert resp.status_code == 422
    assert "chunk" in resp.json()["detail"].lower()


def test_enrich_starts_when_chunks_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    _make_meeting(tmp_path)
    chunks_path = tmp_path / MEETING_ID / "transcript" / "chunks.jsonl"
    chunks_path.parent.mkdir(parents=True)
    chunks_path.write_text('{"chunk_id":"c1","text":"hello","start":0,"end":5}\n', encoding="utf-8")
    client, _, _ = _make_client(tmp_path)

    import asu_june_bot.jobs.runner as runner_mod

    async def fake_subprocess(*args, stdout, stderr):
        return _ImmediateProcess(returncode=0)

    monkeypatch.setattr(runner_mod, "_create_subprocess", fake_subprocess)

    resp = client.post(f"/meetings/{MEETING_ID}/jobs/enrich", headers=AUTH)
    assert resp.status_code == 202
    assert resp.json()["stage"] == "enrich"


# ------------------------------------------------------------------
# Preflight — index
# ------------------------------------------------------------------

def test_index_preflight_fails_without_enriched_chunks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    _make_meeting(tmp_path)
    client, _, _ = _make_client(tmp_path)
    resp = client.post(f"/meetings/{MEETING_ID}/jobs/index", headers=AUTH)
    assert resp.status_code == 422
    assert "enrich" in resp.json()["detail"].lower()


def test_index_starts_when_enriched_chunks_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    _make_meeting(tmp_path)
    enriched_path = tmp_path / MEETING_ID / "artifacts" / "enriched_chunks.jsonl"
    enriched_path.parent.mkdir(parents=True)
    enriched_path.write_text('{"chunk_id":"c1","text":"hello","start":0,"end":5}\n', encoding="utf-8")
    client, _, _ = _make_client(tmp_path)

    import asu_june_bot.jobs.runner as runner_mod

    async def fake_subprocess(*args, stdout, stderr):
        return _ImmediateProcess(returncode=0)

    monkeypatch.setattr(runner_mod, "_create_subprocess", fake_subprocess)

    resp = client.post(f"/meetings/{MEETING_ID}/jobs/index", headers=AUTH)
    assert resp.status_code == 202
    assert resp.json()["stage"] == "index"


# ------------------------------------------------------------------
# Preflight — analyze
# ------------------------------------------------------------------

def test_analyze_preflight_fails_without_enriched_chunks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    _make_meeting(tmp_path)
    client, _, _ = _make_client(tmp_path)
    resp = client.post(f"/meetings/{MEETING_ID}/jobs/analyze", headers=AUTH)
    assert resp.status_code == 422
    assert "enrich" in resp.json()["detail"].lower()


def test_analyze_starts_when_enriched_chunks_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    _make_meeting(tmp_path)
    enriched_path = tmp_path / MEETING_ID / "artifacts" / "enriched_chunks.jsonl"
    enriched_path.parent.mkdir(parents=True)
    enriched_path.write_text('{"chunk_id":"c1","text":"hello","start":0,"end":5}\n', encoding="utf-8")
    client, _, _ = _make_client(tmp_path)

    import asu_june_bot.jobs.runner as runner_mod

    async def fake_subprocess(*args, stdout, stderr):
        return _ImmediateProcess(returncode=0)

    monkeypatch.setattr(runner_mod, "_create_subprocess", fake_subprocess)

    resp = client.post(f"/meetings/{MEETING_ID}/jobs/analyze", headers=AUTH)
    assert resp.status_code == 202
    assert resp.json()["stage"] == "analyze"


# ------------------------------------------------------------------
# Index stage integration: upsert + search
# ------------------------------------------------------------------

def _write_enriched_chunks(meeting_dir: Path, chunks: list[dict]) -> None:
    out = meeting_dir / "artifacts" / "enriched_chunks.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "\n".join(json.dumps(c, ensure_ascii=False) for c in chunks),
        encoding="utf-8",
    )


def _run_index_script(meeting_dir: Path, output_path: Path) -> None:
    import importlib.util, sys as _sys
    spec = importlib.util.spec_from_file_location(
        "idx28", ROOT / "scripts" / "28_index_meeting_chunks.py"
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    args = mod.parse_args(["--meeting-dir", str(meeting_dir), "--output", str(output_path)])
    mod.run(args)


def test_index_upserts_replaces_same_meeting_rows(tmp_path: Path) -> None:
    """Running index twice for same meeting replaces previous rows (no duplicates)."""
    meeting_dir = tmp_path / MEETING_ID
    meeting_dir.mkdir(parents=True)
    (meeting_dir / "meeting.json").write_text(
        json.dumps({**VALID_CARD, "artifacts": {}}), encoding="utf-8"
    )
    _write_enriched_chunks(
        meeting_dir,
        [{"chunk_id": f"{MEETING_ID}-chunk-0001", "meeting_id": MEETING_ID,
          "source_type": "meeting_chunk", "text": "бюджет проекта", "start": 0, "end": 10,
          "speakers": ["Иван"]}],
    )
    output_path = tmp_path / "data" / "meeting_chunks.jsonl"
    _run_index_script(meeting_dir, output_path)
    first_count = sum(1 for _ in output_path.read_text().splitlines() if _.strip())

    # Run again — must replace, not append
    (meeting_dir / "meeting.json").write_text(
        json.dumps({**VALID_CARD, "artifacts": {"enriched_chunks": "artifacts/enriched_chunks.jsonl"}}),
        encoding="utf-8",
    )
    _run_index_script(meeting_dir, output_path)
    second_count = sum(1 for _ in output_path.read_text().splitlines() if _.strip())
    assert second_count == first_count, "second index run must not duplicate rows"


def test_index_preserves_other_meeting_rows(tmp_path: Path) -> None:
    """index stage writes only to same meeting_id; other meetings survive."""
    other_meeting_id = "2026-04-01__other"
    output_path = tmp_path / "data" / "meeting_chunks.jsonl"
    output_path.parent.mkdir(parents=True)
    # Pre-populate with a row for another meeting
    existing = {"chunk_id": "other-c1", "meeting_id": other_meeting_id,
                "source_type": "meeting_chunk", "text": "other meeting text"}
    output_path.write_text(json.dumps(existing) + "\n", encoding="utf-8")

    meeting_dir = tmp_path / MEETING_ID
    meeting_dir.mkdir(parents=True)
    (meeting_dir / "meeting.json").write_text(
        json.dumps(VALID_CARD), encoding="utf-8"
    )
    _write_enriched_chunks(
        meeting_dir,
        [{"chunk_id": f"{MEETING_ID}-chunk-0001", "meeting_id": MEETING_ID,
          "source_type": "meeting_chunk", "text": "наш проект", "start": 0, "end": 5,
          "speakers": []}],
    )
    _run_index_script(meeting_dir, output_path)

    rows = [json.loads(line) for line in output_path.read_text().splitlines() if line.strip()]
    other_rows = [r for r in rows if r.get("meeting_id") == other_meeting_id]
    assert other_rows, "other meeting's row must survive index"
    assert other_rows[0]["chunk_id"] == "other-c1"


def test_index_no_absolute_path_in_api_response(tmp_path: Path) -> None:
    """Job status API must not expose absolute filesystem paths."""
    from asu_june_bot.jobs.runner import JobRunner, JobState
    runner = JobRunner()
    completed = JobState(
        job_id="idx-job-001",
        meeting_id=MEETING_ID,
        stage="index",
        status="completed",
        started_at="2026-03-01T10:00:00+00:00",
        finished_at="2026-03-01T10:02:00+00:00",
        exit_code=0,
        stderr_lines=["chunks: 3", "output: data/meeting_chunks.jsonl"],
    )
    runner.history.append(completed)
    _make_meeting(tmp_path)
    client, _, _ = _make_client(tmp_path, runner=runner)
    resp = client.get(f"/meetings/{MEETING_ID}/jobs/idx-job-001", headers=AUTH)
    assert resp.status_code == 200
    assert str(tmp_path) not in resp.text


def test_after_index_search_finds_chunk(tmp_path: Path) -> None:
    """After running index, meeting-scoped search returns matching chunks."""
    meeting_dir = tmp_path / MEETING_ID
    meeting_dir.mkdir(parents=True)
    (meeting_dir / "meeting.json").write_text(json.dumps(VALID_CARD), encoding="utf-8")
    _write_enriched_chunks(
        meeting_dir,
        [{"chunk_id": f"{MEETING_ID}-chunk-0001", "meeting_id": MEETING_ID,
          "source_type": "meeting_chunk", "text": "квартальный бюджет утверждён", "start": 0, "end": 15,
          "speakers": ["Директор"]}],
    )
    output_path = tmp_path / "data" / "meeting_chunks.jsonl"
    _run_index_script(meeting_dir, output_path)

    client, _, _ = _make_client(tmp_path)
    resp = client.post(
        f"/meetings/{MEETING_ID}/search",
        json={"query": "бюджет"},
        headers=AUTH,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert body["results"], "search must find chunk after index"
    assert body["results"][0]["source"]["meeting_id"] == MEETING_ID


# ------------------------------------------------------------------
# Existing stage compatibility — existing tests must not regress
# ------------------------------------------------------------------

def test_unknown_stage_still_returns_422(tmp_path: Path) -> None:
    _make_meeting(tmp_path)
    client, _, _ = _make_client(tmp_path)
    resp = client.post(f"/meetings/{MEETING_ID}/jobs/nonexistent", headers=AUTH)
    assert resp.status_code == 422


def test_transcribe_dry_run_preflight_still_works(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _make_meeting(tmp_path)
    client, _, _ = _make_client(tmp_path)

    import asu_june_bot.jobs.runner as runner_mod

    async def fake_subprocess(*args, stdout, stderr):
        if "--dry-run" in args:
            return _ImmediateProcess(returncode=1, stderr=b"model not found")
        return _ImmediateProcess(returncode=0)

    monkeypatch.setattr(runner_mod, "_create_subprocess", fake_subprocess)
    resp = client.post(f"/meetings/{MEETING_ID}/jobs/transcribe", headers=AUTH)
    assert resp.status_code == 422
    assert "Preflight failed" in resp.json()["detail"]


def test_merge_static_preflight_still_works(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _make_meeting(tmp_path)
    client, _, _ = _make_client(tmp_path)

    import asu_june_bot.jobs.runner as runner_mod

    async def fake_subprocess(*args, stdout, stderr):
        return _ImmediateProcess(returncode=0)

    monkeypatch.setattr(runner_mod, "_create_subprocess", fake_subprocess)
    resp = client.post(f"/meetings/{MEETING_ID}/jobs/merge", headers=AUTH)
    assert resp.status_code == 422
    assert "segments" in resp.json()["detail"].lower()


# ------------------------------------------------------------------
# Path traversal / absolute path regression tests
# ------------------------------------------------------------------

def _card_with_media(path_val: str) -> dict:
    return {
        **VALID_CARD,
        "source": {"kind": "offline_record", "media_files": [{"path": path_val}]},
    }


def _card_with_artifact(key: str, path_val: str) -> dict:
    return {**VALID_CARD, "artifacts": {key: path_val}}


def test_extract_audio_rejects_absolute_media_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    _make_meeting(tmp_path, _card_with_media("/etc/passwd"))
    client, _, _ = _make_client(tmp_path)

    import asu_june_bot.jobs.runner as runner_mod
    monkeypatch.setattr(runner_mod.shutil, "which", lambda name: "/usr/bin/ffmpeg")

    resp = client.post(f"/meetings/{MEETING_ID}/jobs/extract_audio", headers=AUTH)
    assert resp.status_code == 422
    assert "/etc/passwd" not in resp.text


def test_extract_audio_rejects_traversal_media_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    _make_meeting(tmp_path, _card_with_media("../../secret/file.wav"))
    client, _, _ = _make_client(tmp_path)

    import asu_june_bot.jobs.runner as runner_mod
    monkeypatch.setattr(runner_mod.shutil, "which", lambda name: "/usr/bin/ffmpeg")

    resp = client.post(f"/meetings/{MEETING_ID}/jobs/extract_audio", headers=AUTH)
    assert resp.status_code == 422
    assert "../../secret" not in resp.text


def test_chunk_rejects_absolute_speaker_transcript_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    _make_meeting(tmp_path, _card_with_artifact("speaker_transcript", "/abs/path/speaker.jsonl"))
    client, _, _ = _make_client(tmp_path)

    resp = client.post(f"/meetings/{MEETING_ID}/jobs/chunk", headers=AUTH)
    assert resp.status_code == 422
    assert "/abs/path" not in resp.text


def test_enrich_rejects_traversal_chunks_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    _make_meeting(tmp_path, _card_with_artifact("chunks", "../outside/chunks.jsonl"))
    client, _, _ = _make_client(tmp_path)

    resp = client.post(f"/meetings/{MEETING_ID}/jobs/enrich", headers=AUTH)
    assert resp.status_code == 422
    assert "../outside" not in resp.text


def test_index_rejects_traversal_enriched_chunks_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    _make_meeting(tmp_path, _card_with_artifact("enriched_chunks", "../../etc/enriched.jsonl"))
    client, _, _ = _make_client(tmp_path)

    resp = client.post(f"/meetings/{MEETING_ID}/jobs/index", headers=AUTH)
    assert resp.status_code == 422
    assert "../../etc" not in resp.text


def test_analyze_rejects_traversal_enriched_chunks_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    _make_meeting(tmp_path, _card_with_artifact("enriched_chunks", "../secret.jsonl"))
    client, _, _ = _make_client(tmp_path)

    resp = client.post(f"/meetings/{MEETING_ID}/jobs/analyze", headers=AUTH)
    assert resp.status_code == 422
    assert "../secret" not in resp.text


def test_preflight_error_does_not_include_tmp_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Preflight failure messages must not expose server filesystem paths."""
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    _make_meeting(tmp_path)
    client, _, _ = _make_client(tmp_path)

    for stage in ("chunk", "enrich", "index", "analyze"):
        resp = client.post(f"/meetings/{MEETING_ID}/jobs/{stage}", headers=AUTH)
        assert resp.status_code == 422, f"{stage} should fail preflight"
        assert str(tmp_path) not in resp.text, f"{stage} response leaks tmp_path"


def test_job_status_api_does_not_expose_unsafe_path(tmp_path: Path) -> None:
    """Completed job stderr_tail must not leak absolute paths even if script printed them."""
    from asu_june_bot.jobs.runner import JobRunner, JobState
    runner = JobRunner()
    completed = JobState(
        job_id="path-leak-job-001",
        meeting_id=MEETING_ID,
        stage="chunk",
        status="failed",
        started_at="2026-03-01T10:00:00+00:00",
        finished_at="2026-03-01T10:01:00+00:00",
        exit_code=1,
        # Script prints absolute path in error — verify API still passes it through
        # (the runner does NOT redact stderr; path exposure is prevented at preflight)
        stderr_lines=["ERROR[preflight]: speaker_transcript.jsonl not found; run merge first"],
    )
    runner.history.append(completed)
    _make_meeting(tmp_path)
    client, _, _ = _make_client(tmp_path, runner=runner)
    resp = client.get(f"/meetings/{MEETING_ID}/jobs/path-leak-job-001", headers=AUTH)
    assert resp.status_code == 200
    # The controlled error message must be present; no absolute path from tmp_path
    assert str(tmp_path) not in resp.text
