"""Tests for stage errors, retry and pipeline resume (MA-MEETING-ERRORS-AND-RETRY, #120)."""
from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import asu_june_bot.jobs.runner as runner_mod  # noqa: E402
from asu_june_bot.api.app import create_app  # noqa: E402
from asu_june_bot.auth.repository import AuthRepository  # noqa: E402
from asu_june_bot.auth.service import AdminService, LocalAuthService  # noqa: E402
from asu_june_bot.auth.throttle import LoginThrottle  # noqa: E402
from asu_june_bot.jobs.readiness import pipeline_readiness  # noqa: E402
from asu_june_bot.jobs.runner import JobRunner, JobState  # noqa: E402
from asu_june_bot.meetings.service import MeetingsService  # noqa: E402

TOKEN = "test-retry-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
MEETING_ID = "2026-03-04__retry"

CARD = {
    "schema_version": 1,
    "meeting_id": MEETING_ID,
    "title": "Retry Meeting",
    "date": "2026-03-04",
    "processing_status": "new",
    "source": {
        "kind": "offline_record",
        "media_files": [{"path": "source/video.mp4", "media_type": "video"}],
    },
    "artifacts": {},
    "rag": {"index_policy": "structured_artifacts_and_final_transcript"},
}

_MARKERS = {
    "21_extract_audio.py": "source/audio_16k_mono.wav",
    "22_transcribe_meeting.py": "transcript/segments.jsonl",
    "24_merge_transcript_speakers.py": "transcript/speaker_transcript.jsonl",
    "26_chunk_meeting.py": "transcript/chunks.jsonl",
    "27_enrich_meeting_chunks.py": "artifacts/enriched_chunks.jsonl",
}


def _make_meeting(root: Path) -> Path:
    d = root / MEETING_ID
    d.mkdir(parents=True, exist_ok=True)
    (d / "source").mkdir(exist_ok=True)
    (d / "source" / "video.mp4").write_bytes(b"fake")
    (d / "meeting.json").write_text(json.dumps(CARD), encoding="utf-8")
    return d


def _read_card(meeting_dir: Path) -> dict:
    return json.loads((meeting_dir / "meeting.json").read_text(encoding="utf-8"))


class _StageProcess:
    def __init__(self, meeting_dir: Path, script: str, returncode: int = 0) -> None:
        self.returncode = returncode
        self.pid = 33333
        self._meeting_dir = meeting_dir
        self._script = script

    async def communicate(self) -> tuple[bytes, bytes]:
        if self.returncode == 0:
            marker = _MARKERS.get(self._script)
            if marker:
                target = self._meeting_dir / marker
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("x", encoding="utf-8")
            return b"", b""
        return b"", b"Traceback: secret /home/user/private/path failure"

    def terminate(self) -> None:
        self.returncode = -15


def _patch_subprocess(
    monkeypatch: pytest.MonkeyPatch, meeting_dir: Path, fail_scripts: set[str] | None = None
) -> list[str]:
    launched: list[str] = []
    fail = fail_scripts or set()

    async def fake_subprocess(*args, stdout, stderr):
        script = Path(args[1]).name
        dry = "--dry-run" in args
        if not dry:
            launched.append(script)
        rc = 1 if (script in fail and not dry) else 0
        return _StageProcess(meeting_dir, script, returncode=rc)

    monkeypatch.setattr(runner_mod, "_create_subprocess", fake_subprocess)
    monkeypatch.setattr(runner_mod.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    return launched


async def _run_stage_and_wait(runner: JobRunner, meeting_dir: Path, stage: str) -> JobState:
    job = await runner.submit(meeting_id=MEETING_ID, stage=stage, meeting_dir=meeting_dir)
    for _ in range(200):
        if job.status not in ("starting", "running"):
            break
        await asyncio.sleep(0.02)
    return job


# ---------------------------------------------------------------------------
# last_error normalization
# ---------------------------------------------------------------------------

def test_failed_stage_writes_normalized_last_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = _make_meeting(tmp_path)
    _patch_subprocess(monkeypatch, d, fail_scripts={"21_extract_audio.py"})
    runner = JobRunner()
    job = asyncio.run(_run_stage_and_wait(runner, d, "extract_audio"))
    assert job.status == "failed"
    last = _read_card(d)["last_error"]
    assert last["stage"] == "extract_audio"
    assert last["code"] == "stage_failed"
    assert last["job_id"] == job.job_id
    assert last["timestamp"]
    assert "exit code" in last["message"]


def test_normalized_last_error_matches_meeting_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = _make_meeting(tmp_path)
    _patch_subprocess(monkeypatch, d, fail_scripts={"21_extract_audio.py"})
    runner = JobRunner()
    asyncio.run(_run_stage_and_wait(runner, d, "extract_audio"))
    schema = json.loads((ROOT / "configs" / "schemas" / "meeting.schema.json").read_text(encoding="utf-8"))
    card = _read_card(d)
    card.update(
        {
            "participants": [],
            "classification": {},
            "links": {},
            "retention": {"policy": "default"},
            "created_at": "2026-03-04T10:00:00+00:00",
            "updated_at": "2026-03-04T10:00:00+00:00",
        }
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(card)


def test_last_error_contains_no_paths_or_traces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = _make_meeting(tmp_path)
    _patch_subprocess(monkeypatch, d, fail_scripts={"21_extract_audio.py"})
    runner = JobRunner()
    asyncio.run(_run_stage_and_wait(runner, d, "extract_audio"))
    dumped = json.dumps(_read_card(d)["last_error"])
    assert "/home/user" not in dumped
    assert str(d) not in dumped
    assert "Traceback" not in dumped
    assert "secret" not in dumped


def test_successful_retry_clears_last_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = _make_meeting(tmp_path)
    _patch_subprocess(monkeypatch, d, fail_scripts={"21_extract_audio.py"})
    runner = JobRunner()
    asyncio.run(_run_stage_and_wait(runner, d, "extract_audio"))
    assert "last_error" in _read_card(d)
    # now the stage succeeds
    _patch_subprocess(monkeypatch, d)
    asyncio.run(_run_stage_and_wait(runner, d, "extract_audio"))
    assert "last_error" not in _read_card(d)


def test_other_stage_success_keeps_last_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = _make_meeting(tmp_path)
    (d / "transcript").mkdir()
    (d / "transcript" / "segments.jsonl").write_text("x", encoding="utf-8")
    _patch_subprocess(monkeypatch, d, fail_scripts={"21_extract_audio.py"})
    runner = JobRunner()
    asyncio.run(_run_stage_and_wait(runner, d, "extract_audio"))
    _patch_subprocess(monkeypatch, d)
    asyncio.run(_run_stage_and_wait(runner, d, "merge"))
    assert _read_card(d)["last_error"]["stage"] == "extract_audio"


# ---------------------------------------------------------------------------
# Readiness integration
# ---------------------------------------------------------------------------

def test_readiness_shows_ready_for_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = _make_meeting(tmp_path)
    _patch_subprocess(monkeypatch, d, fail_scripts={"21_extract_audio.py"})
    runner = JobRunner()
    asyncio.run(_run_stage_and_wait(runner, d, "extract_audio"))
    stages = {s["stage"]: s for s in pipeline_readiness(MEETING_ID, d)["stages"]}
    ea = stages["extract_audio"]
    assert ea["state"] == "ready_for_retry"
    assert ea["reason"] == "previous_failed"
    assert ea["can_run"] is True
    dumped = json.dumps(ea)
    assert str(d) not in dumped and "/home/user" not in dumped


def test_readiness_done_wins_over_previous_failed(tmp_path: Path) -> None:
    d = _make_meeting(tmp_path)
    (d / "source" / "audio_16k_mono.wav").write_text("x", encoding="utf-8")
    card = _read_card(d)
    card["last_error"] = {"stage": "extract_audio", "code": "stage_failed",
                          "message": "m", "timestamp": "t", "job_id": "j"}
    (d / "meeting.json").write_text(json.dumps(card), encoding="utf-8")
    stages = {s["stage"]: s for s in pipeline_readiness(MEETING_ID, d)["stages"]}
    assert stages["extract_audio"]["state"] == "done"


# ---------------------------------------------------------------------------
# API — retry endpoint
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class FakeState:
    meetings_service: MeetingsService
    job_runner: JobRunner
    local_auth_service: LocalAuthService
    admin_service: AdminService = field(default=None)  # type: ignore[assignment]
    login_throttle: LoginThrottle = field(default_factory=LoginThrottle)


def _make_client(root: Path) -> tuple[TestClient, JobRunner]:
    os.environ["MEETINGAGENT_API_TOKEN"] = TOKEN
    repo = AuthRepository(root / "_auth.db")
    repo.initialize()
    app = create_app()
    runner = JobRunner()
    client = TestClient(app, raise_server_exceptions=False)
    app.state.asu_june_bot = FakeState(
        meetings_service=MeetingsService(root),
        job_runner=runner,
        local_auth_service=LocalAuthService(repo),
        admin_service=AdminService(repo),
    )
    return client, runner


def test_retry_unknown_stage_422(tmp_path: Path) -> None:
    _make_meeting(tmp_path)
    client, _ = _make_client(tmp_path)
    resp = client.post(f"/meetings/{MEETING_ID}/jobs/nope/retry", headers=AUTH, json={})
    assert resp.status_code == 422


def test_retry_requires_auth(tmp_path: Path) -> None:
    _make_meeting(tmp_path)
    client, _ = _make_client(tmp_path)
    resp = client.post(f"/meetings/{MEETING_ID}/jobs/chunk/retry", json={})
    assert resp.status_code == 401


def test_retry_while_job_active_409(tmp_path: Path) -> None:
    d = _make_meeting(tmp_path)
    client, runner = _make_client(tmp_path)
    runner.active_job = JobState(
        job_id="busy", meeting_id=MEETING_ID, stage="chunk",
        status="running", started_at="now", _meeting_dir=d,
    )
    resp = client.post(f"/meetings/{MEETING_ID}/jobs/chunk/retry", headers=AUTH, json={})
    assert resp.status_code == 409


def test_retry_done_stage_requires_force(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = _make_meeting(tmp_path)
    (d / "source" / "audio_16k_mono.wav").write_text("x", encoding="utf-8")
    _patch_subprocess(monkeypatch, d)
    client, _ = _make_client(tmp_path)
    resp = client.post(f"/meetings/{MEETING_ID}/jobs/extract_audio/retry", headers=AUTH, json={})
    assert resp.status_code == 409
    assert "force" in resp.json()["detail"]
    # explicit force is accepted
    resp2 = client.post(
        f"/meetings/{MEETING_ID}/jobs/extract_audio/retry",
        headers=AUTH,
        json={"force": True},
    )
    assert resp2.status_code == 202
    assert resp2.json()["stage"] == "extract_audio"


def test_retry_failed_stage_starts_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = _make_meeting(tmp_path)
    _patch_subprocess(monkeypatch, d)
    client, _ = _make_client(tmp_path)
    resp = client.post(f"/meetings/{MEETING_ID}/jobs/extract_audio/retry", headers=AUTH, json={})
    assert resp.status_code == 202
    body = resp.json()
    assert body["stage"] == "extract_audio"
    assert body["job_id"]


def test_retry_cookie_session_without_csrf_403(tmp_path: Path) -> None:
    _make_meeting(tmp_path)
    client, _ = _make_client(tmp_path)
    # editor cookie session, no X-CSRF-Token header
    state = client.app.state.asu_june_bot
    state.admin_service.create_user(
        email="e@example.com", password="editorpass1", roles=["editor"], actor_id="system"
    )
    login = client.post(
        "/auth/local/login", json={"email": "e@example.com", "password": "editorpass1"}
    )
    assert login.status_code == 200
    cookie = login.cookies["ma_session"]
    resp = client.post(
        f"/meetings/{MEETING_ID}/jobs/chunk/retry",
        cookies={"ma_session": cookie},
        json={},
    )
    assert resp.status_code == 403


def test_retry_viewer_cookie_forbidden(tmp_path: Path) -> None:
    _make_meeting(tmp_path)
    client, _ = _make_client(tmp_path)
    state = client.app.state.asu_june_bot
    state.admin_service.create_user(
        email="v@example.com", password="viewerpass1", roles=["viewer"], actor_id="system"
    )
    login = client.post(
        "/auth/local/login", json={"email": "v@example.com", "password": "viewerpass1"}
    )
    cookie = login.cookies["ma_session"]
    csrf = login.json()["csrf_token"]
    resp = client.post(
        f"/meetings/{MEETING_ID}/jobs/chunk/retry",
        cookies={"ma_session": cookie},
        headers={"X-CSRF-Token": csrf},
        json={},
    )
    assert resp.status_code == 403


def test_retry_unknown_meeting_404(tmp_path: Path) -> None:
    client, _ = _make_client(tmp_path)
    resp = client.post("/meetings/missing__x/jobs/chunk/retry", headers=AUTH, json={})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# API — job status exposes last_error; pipeline resume/force
# ---------------------------------------------------------------------------

def test_job_status_includes_last_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = _make_meeting(tmp_path)
    _patch_subprocess(monkeypatch, d, fail_scripts={"21_extract_audio.py"})
    runner = JobRunner()
    job = asyncio.run(_run_stage_and_wait(runner, d, "extract_audio"))
    client, api_runner = _make_client(tmp_path)
    api_runner.history.append(job)
    resp = client.get(f"/meetings/{MEETING_ID}/jobs/{job.job_id}", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["last_error"]["stage"] == "extract_audio"
    assert body["last_error"]["code"] == "stage_failed"
    dumped = json.dumps(body["last_error"])
    assert str(d) not in dumped and "Traceback" not in dumped


def test_pipeline_resume_skips_done_and_reports_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = _make_meeting(tmp_path)
    # extract_audio + transcribe already done; merge will fail
    (d / "source" / "audio_16k_mono.wav").write_text("x", encoding="utf-8")
    (d / "transcript").mkdir()
    (d / "transcript" / "segments.jsonl").write_text("x", encoding="utf-8")
    _patch_subprocess(monkeypatch, d, fail_scripts={"24_merge_transcript_speakers.py"})
    runner = JobRunner()

    async def scenario():
        p = await runner.submit_pipeline(
            meeting_id=MEETING_ID, meeting_dir=d, profile="default", resume=True
        )
        for _ in range(300):
            if p.status != "running":
                break
            await asyncio.sleep(0.05)
        return p

    pipeline = asyncio.run(scenario())
    assert pipeline.status == "failed"
    d_map = {i["stage"]: i for i in pipeline.stages}
    assert d_map["extract_audio"]["status"] == "skipped"
    assert d_map["extract_audio"]["reason"] == "already_done"
    assert d_map["transcribe"]["status"] == "skipped"
    assert d_map["merge"]["status"] == "failed"
    assert d_map["chunk"]["status"] == "skipped"  # stopped after first failure
    payload = pipeline.as_dict()
    assert payload["resume"] is True
    # last_error recorded for the failed child stage
    assert _read_card(d)["last_error"]["stage"] == "merge"


def test_pipeline_force_overrides_skip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = _make_meeting(tmp_path)
    (d / "source" / "audio_16k_mono.wav").write_text("x", encoding="utf-8")
    launched = _patch_subprocess(monkeypatch, d)
    runner = JobRunner()

    async def scenario():
        p = await runner.submit_pipeline(
            meeting_id=MEETING_ID, meeting_dir=d, profile="transcript_only", force=True
        )
        for _ in range(300):
            if p.status != "running":
                break
            await asyncio.sleep(0.05)
        return p

    pipeline = asyncio.run(scenario())
    assert pipeline.status == "completed"
    assert "21_extract_audio.py" in launched
