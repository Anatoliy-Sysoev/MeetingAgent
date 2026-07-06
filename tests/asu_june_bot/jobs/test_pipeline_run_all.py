"""Tests for the one-click sequential pipeline job (MA-MEETING-PIPELINE-RUN-ALL, #115)."""
from __future__ import annotations

import asyncio
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

import asu_june_bot.jobs.runner as runner_mod  # noqa: E402
from asu_june_bot.api.app import create_app  # noqa: E402
from asu_june_bot.auth.repository import AuthRepository  # noqa: E402
from asu_june_bot.auth.service import AdminService, LocalAuthService  # noqa: E402
from asu_june_bot.auth.throttle import LoginThrottle  # noqa: E402
from asu_june_bot.jobs.runner import (  # noqa: E402
    PIPELINE_PROFILES,
    JobAlreadyRunning,
    JobRunner,
    PipelineJobState,
)
from asu_june_bot.meetings.service import MeetingsService  # noqa: E402

TOKEN = "test-runall-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
MEETING_ID = "2026-03-02__runall"

CARD = {
    "schema_version": 1,
    "meeting_id": MEETING_ID,
    "title": "Run-all Meeting",
    "date": "2026-03-02",
    "processing_status": "new",
    "source": {
        "kind": "offline_record",
        "media_files": [{"path": "source/video.mp4", "media_type": "video"}],
    },
    "artifacts": {},
    "rag": {"index_policy": "structured_artifacts_and_final_transcript"},
}

# Stage → done-marker the fake subprocess writes on success.
_MARKERS = {
    "21_extract_audio.py": "source/audio_16k_mono.wav",
    "22_transcribe_meeting.py": "transcript/segments.jsonl",
    "23_diarize_meeting.py": "transcript/diarization.jsonl",
    "24_merge_transcript_speakers.py": "transcript/speaker_transcript.jsonl",
    "26_chunk_meeting.py": "transcript/chunks.jsonl",
    "27_enrich_meeting_chunks.py": "artifacts/enriched_chunks.jsonl",
    "28_index_meeting_chunks.py": None,  # writes rag.indexed_artifacts instead
    "29_analyze_meeting.py": "artifacts/summary.md",
}


def _make_meeting(root: Path) -> Path:
    d = root / MEETING_ID
    d.mkdir(parents=True, exist_ok=True)
    (d / "source").mkdir(exist_ok=True)
    (d / "source" / "video.mp4").write_bytes(b"fake")
    (d / "meeting.json").write_text(json.dumps(CARD), encoding="utf-8")
    return d


class _StageProcess:
    """Fake subprocess: succeeds (or fails) and writes the stage's done marker."""

    def __init__(self, meeting_dir: Path, script_name: str, returncode: int = 0) -> None:
        self.returncode = returncode
        self.pid = 22222
        self._meeting_dir = meeting_dir
        self._script = script_name

    async def communicate(self) -> tuple[bytes, bytes]:
        if self.returncode == 0:
            marker = _MARKERS.get(self._script)
            if marker:
                target = self._meeting_dir / marker
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("x", encoding="utf-8")
            elif self._script == "28_index_meeting_chunks.py":
                card_path = self._meeting_dir / "meeting.json"
                card = json.loads(card_path.read_text(encoding="utf-8"))
                card.setdefault("rag", {})["indexed_artifacts"] = [
                    "artifacts/enriched_chunks.jsonl"
                ]
                card_path.write_text(json.dumps(card), encoding="utf-8")
            return b"", b""
        return b"", b"stage failed"

    def terminate(self) -> None:
        self.returncode = -15


def _patch_subprocess(
    monkeypatch: pytest.MonkeyPatch,
    meeting_dir: Path,
    fail_scripts: set[str] | None = None,
) -> list[str]:
    """Replace _create_subprocess with an instant fake; returns launch log."""
    launched: list[str] = []
    fail = fail_scripts or set()

    async def fake_subprocess(*args, stdout, stderr):
        script_name = Path(args[1]).name
        is_dry_run = "--dry-run" in args
        if not is_dry_run:
            launched.append(script_name)
        rc = 1 if (script_name in fail and not is_dry_run) else 0
        return _StageProcess(meeting_dir, script_name, returncode=rc)

    monkeypatch.setattr(runner_mod, "_create_subprocess", fake_subprocess)
    monkeypatch.setattr(runner_mod.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    return launched


async def _run_and_wait(
    runner: JobRunner, meeting_dir: Path, **kwargs
) -> PipelineJobState:
    pipeline = await runner.submit_pipeline(
        meeting_id=MEETING_ID, meeting_dir=meeting_dir, **kwargs
    )
    for _ in range(300):
        if pipeline.status != "running":
            break
        await asyncio.sleep(0.05)
    return pipeline


def _stage_statuses(pipeline: PipelineJobState) -> dict[str, str]:
    return {item["stage"]: item["status"] for item in pipeline.stages}


# ---------------------------------------------------------------------------
# Unit — sequential execution, skip, force, stop-on-error, cancel
# ---------------------------------------------------------------------------

def test_profiles_defined() -> None:
    assert set(PIPELINE_PROFILES) == {"default", "full", "transcript_only", "qa_ready"}
    assert PIPELINE_PROFILES["default"] == [
        "extract_audio",
        "transcribe",
        "merge",
        "chunk",
        "enrich",
        "index",
    ]
    assert PIPELINE_PROFILES["qa_ready"] == PIPELINE_PROFILES["default"]
    assert PIPELINE_PROFILES["full"][-1] == "analyze"


def test_pipeline_runs_stages_in_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    d = _make_meeting(tmp_path)
    launched = _patch_subprocess(monkeypatch, d)
    runner = JobRunner()
    pipeline = asyncio.run(_run_and_wait(runner, d, profile="transcript_only"))
    assert pipeline.status == "completed"
    assert _stage_statuses(pipeline) == {"extract_audio": "completed", "transcribe": "completed"}
    assert launched == ["21_extract_audio.py", "22_transcribe_meeting.py"]
    assert pipeline.finished_at is not None
    assert runner.active_pipeline is None


def test_full_profile_completes_chain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    d = _make_meeting(tmp_path)
    _patch_subprocess(monkeypatch, d)
    runner = JobRunner()
    pipeline = asyncio.run(_run_and_wait(runner, d, profile="full"))
    assert pipeline.status == "completed"
    assert all(s == "completed" for s in _stage_statuses(pipeline).values())


def test_default_profile_reaches_index_after_enrich(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    d = _make_meeting(tmp_path)
    launched = _patch_subprocess(monkeypatch, d)
    runner = JobRunner()
    pipeline = asyncio.run(_run_and_wait(runner, d, profile="default"))
    assert pipeline.status == "completed"
    statuses = _stage_statuses(pipeline)
    assert statuses["enrich"] == "completed"
    assert statuses["index"] == "completed"
    assert launched[-2:] == ["27_enrich_meeting_chunks.py", "28_index_meeting_chunks.py"]


def test_pipeline_skips_done_stages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    d = _make_meeting(tmp_path)
    (d / "source" / "audio_16k_mono.wav").write_text("x", encoding="utf-8")
    launched = _patch_subprocess(monkeypatch, d)
    runner = JobRunner()
    pipeline = asyncio.run(_run_and_wait(runner, d, profile="transcript_only"))
    assert pipeline.status == "completed"
    statuses = _stage_statuses(pipeline)
    assert statuses["extract_audio"] == "skipped"
    assert statuses["transcribe"] == "completed"
    assert "21_extract_audio.py" not in launched
    skipped = next(i for i in pipeline.stages if i["stage"] == "extract_audio")
    assert skipped["reason"] == "already_done"


def test_force_reruns_done_stages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    d = _make_meeting(tmp_path)
    (d / "source" / "audio_16k_mono.wav").write_text("x", encoding="utf-8")
    launched = _patch_subprocess(monkeypatch, d)
    runner = JobRunner()
    pipeline = asyncio.run(_run_and_wait(runner, d, profile="transcript_only", force=True))
    assert pipeline.status == "completed"
    assert _stage_statuses(pipeline)["extract_audio"] == "completed"
    assert "21_extract_audio.py" in launched


def test_pipeline_stops_on_first_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    d = _make_meeting(tmp_path)
    launched = _patch_subprocess(monkeypatch, d, fail_scripts={"22_transcribe_meeting.py"})
    runner = JobRunner()
    pipeline = asyncio.run(_run_and_wait(runner, d, profile="default"))
    assert pipeline.status == "failed"
    statuses = _stage_statuses(pipeline)
    assert statuses["extract_audio"] == "completed"
    assert statuses["transcribe"] == "failed"
    # downstream never launched
    assert statuses["merge"] == "skipped"
    assert statuses["chunk"] == "skipped"
    assert "24_merge_transcript_speakers.py" not in launched


def test_pipeline_conflicts_with_active_job(tmp_path: Path) -> None:
    d = _make_meeting(tmp_path)
    runner = JobRunner()
    runner.active_pipeline = PipelineJobState(
        job_id="p1", meeting_id=MEETING_ID, profile="default", force=False,
        status="running", started_at="now",
    )
    with pytest.raises(JobAlreadyRunning):
        asyncio.run(runner.submit_pipeline(meeting_id=MEETING_ID, meeting_dir=d))
    # single-stage submit is also rejected while a pipeline is active
    with pytest.raises(JobAlreadyRunning):
        asyncio.run(runner.submit(meeting_id=MEETING_ID, stage="chunk", meeting_dir=d))


def test_pipeline_unknown_profile_raises(tmp_path: Path) -> None:
    d = _make_meeting(tmp_path)
    runner = JobRunner()
    with pytest.raises(ValueError):
        asyncio.run(runner.submit_pipeline(
            meeting_id=MEETING_ID, meeting_dir=d, profile="nope"
        ))


def test_pipeline_unknown_stage_raises(tmp_path: Path) -> None:
    d = _make_meeting(tmp_path)
    runner = JobRunner()
    with pytest.raises(ValueError):
        asyncio.run(runner.submit_pipeline(
            meeting_id=MEETING_ID, meeting_dir=d, stages=["chunk", "rm_rf"]
        ))


def test_cancel_pipeline_stops_remaining(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    d = _make_meeting(tmp_path)
    release = asyncio.Event()

    class _SlowProcess(_StageProcess):
        async def communicate(self):
            await release.wait()
            return await super().communicate()

    async def fake_subprocess(*args, stdout, stderr):
        script_name = Path(args[1]).name
        if "--dry-run" in args:
            return _StageProcess(d, script_name)  # instant dry-run OK
        return _SlowProcess(d, script_name)

    monkeypatch.setattr(runner_mod, "_create_subprocess", fake_subprocess)
    monkeypatch.setattr(runner_mod.shutil, "which", lambda name: "/usr/bin/ffmpeg")

    async def scenario() -> PipelineJobState:
        runner = JobRunner()
        pipeline = await runner.submit_pipeline(
            meeting_id=MEETING_ID, meeting_dir=d, profile="default"
        )
        # wait until the first child stage is running
        for _ in range(100):
            if runner.active_job is not None:
                break
            await asyncio.sleep(0.02)
        cancelled = await runner.cancel(pipeline.job_id)
        assert cancelled.status == "cancelled"
        release.set()  # let the terminated child exit
        for _ in range(200):
            if pipeline.finished_at is not None:
                break
            await asyncio.sleep(0.02)
        return pipeline

    pipeline = asyncio.run(scenario())
    assert pipeline.status == "cancelled"
    statuses = _stage_statuses(pipeline)
    assert statuses["extract_audio"] == "cancelled"
    assert all(s == "cancelled" for s in list(statuses.values())[1:])


# ---------------------------------------------------------------------------
# API — validation, RBAC, response shape
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


def test_api_returns_single_job_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    d = _make_meeting(tmp_path)
    _patch_subprocess(monkeypatch, d)
    client, _runner = _make_client(tmp_path)
    resp = client.post(
        f"/meetings/{MEETING_ID}/jobs/pipeline",
        headers=AUTH,
        json={"profile": "transcript_only", "force": False, "stages": None},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["kind"] == "pipeline"
    assert body["job_id"]
    assert body["profile"] == "transcript_only"
    assert [s["stage"] for s in body["stages"]] == ["extract_audio", "transcribe"]
    # status endpoint resolves the pipeline job_id
    status = client.get(f"/meetings/{MEETING_ID}/jobs/{body['job_id']}", headers=AUTH)
    assert status.status_code == 200
    assert status.json()["kind"] == "pipeline"


def test_api_invalid_profile_422(tmp_path: Path) -> None:
    _make_meeting(tmp_path)
    client, _ = _make_client(tmp_path)
    resp = client.post(
        f"/meetings/{MEETING_ID}/jobs/pipeline", headers=AUTH, json={"profile": "nope"}
    )
    assert resp.status_code == 422


def test_api_arbitrary_stage_rejected(tmp_path: Path) -> None:
    _make_meeting(tmp_path)
    client, _ = _make_client(tmp_path)
    resp = client.post(
        f"/meetings/{MEETING_ID}/jobs/pipeline",
        headers=AUTH,
        json={"stages": ["chunk", "; rm -rf /"]},
    )
    assert resp.status_code == 422


def test_api_conflict_409_when_pipeline_active(tmp_path: Path) -> None:
    _make_meeting(tmp_path)
    client, runner = _make_client(tmp_path)
    runner.active_pipeline = PipelineJobState(
        job_id="busy", meeting_id=MEETING_ID, profile="default", force=False,
        status="running", started_at="now",
    )
    resp = client.post(
        f"/meetings/{MEETING_ID}/jobs/pipeline", headers=AUTH, json={}
    )
    assert resp.status_code == 409


def test_api_unknown_meeting_404(tmp_path: Path) -> None:
    client, _ = _make_client(tmp_path)
    resp = client.post("/meetings/missing__x/jobs/pipeline", headers=AUTH, json={})
    assert resp.status_code == 404


def test_api_requires_auth(tmp_path: Path) -> None:
    _make_meeting(tmp_path)
    client, _ = _make_client(tmp_path)
    resp = client.post(f"/meetings/{MEETING_ID}/jobs/pipeline", json={})
    assert resp.status_code == 401


def test_get_active_is_pipeline_aware(tmp_path: Path) -> None:
    """While a pipeline runs (even between child stages), get_active() and
    GET /jobs/active must report the pipeline aggregate, not None (#121)."""
    _make_meeting(tmp_path)
    client, runner = _make_client(tmp_path)
    pipeline = PipelineJobState(
        job_id="p-active", meeting_id=MEETING_ID, profile="default", force=False,
        status="running", started_at="now",
        stages=[{"stage": "chunk", "status": "running", "job_id": None,
                 "exit_code": None, "reason": None}],
    )
    runner.active_pipeline = pipeline
    assert runner.active_job is None  # gap between child stages
    assert runner.get_active() is pipeline
    resp = client.get("/jobs/active", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "pipeline"
    assert body["job_id"] == "p-active"
    assert body["status"] == "running"
    # child stage job takes precedence only when a pipeline is not active
    runner.active_pipeline = None
    assert runner.get_active() is None


def test_api_pipeline_not_captured_as_stage(tmp_path: Path) -> None:
    """POST /jobs/pipeline must hit the pipeline route, not /jobs/{stage}."""
    _make_meeting(tmp_path)
    client, _ = _make_client(tmp_path)
    resp = client.post(
        f"/meetings/{MEETING_ID}/jobs/pipeline", headers=AUTH, json={"profile": "bad"}
    )
    # pipeline route answers with profile error, not "Unknown stage 'pipeline'"
    assert resp.status_code == 422
    assert "profile" in resp.json()["detail"].lower()
