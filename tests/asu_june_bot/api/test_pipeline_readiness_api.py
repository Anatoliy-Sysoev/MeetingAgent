"""Tests for the pipeline readiness map (MA-MEETING-STAGE-READINESS, #114)."""
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
from asu_june_bot.jobs.readiness import pipeline_readiness  # noqa: E402
from asu_june_bot.jobs.runner import JobRunner, JobState  # noqa: E402
from asu_june_bot.meetings.service import MeetingsService  # noqa: E402

TOKEN = "test-readiness-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
MEETING_ID = "2026-02-02__ready"

CARD = {
    "schema_version": 1,
    "meeting_id": MEETING_ID,
    "title": "Readiness Meeting",
    "date": "2026-02-02",
    "status": "new",
    "participants": [],
    "source": {"kind": "offline_record", "media_files": []},
    "artifacts": {},
    "rag": {"index_policy": "structured_artifacts_and_final_transcript"},
}


@dataclass(slots=True)
class FakeState:
    meetings_service: MeetingsService
    job_runner: JobRunner
    local_auth_service: LocalAuthService
    admin_service: AdminService = field(default=None)  # type: ignore[assignment]
    login_throttle: LoginThrottle = field(default_factory=LoginThrottle)


def _make_meeting(root: Path, card_extra: dict | None = None) -> Path:
    d = root / MEETING_ID
    d.mkdir(parents=True, exist_ok=True)
    card = {**CARD, **(card_extra or {})}
    (d / "meeting.json").write_text(json.dumps(card), encoding="utf-8")
    return d


def _touch(meeting_dir: Path, rel: str) -> None:
    p = meeting_dir / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x", encoding="utf-8")


def _stage_map(payload: dict) -> dict[str, dict]:
    return {s["stage"]: s for s in payload["stages"]}


# ---------------------------------------------------------------------------
# Unit: pipeline_readiness()
# ---------------------------------------------------------------------------

def test_fresh_meeting_blocks_downstream_stages(tmp_path: Path) -> None:
    d = _make_meeting(tmp_path)
    stages = _stage_map(pipeline_readiness(MEETING_ID, d))
    # no audio → transcribe/diarize blocked
    assert stages["transcribe"]["state"] == "blocked"
    assert stages["transcribe"]["reason"] == "audio_missing"
    assert stages["diarize"]["state"] == "blocked"
    # no transcript → merge/chunk blocked
    assert stages["merge"]["state"] == "blocked"
    assert stages["merge"]["reason"] == "transcript_missing"
    assert stages["chunk"]["state"] == "blocked"
    # no chunks → enrich/index/analyze blocked
    assert stages["enrich"]["state"] == "blocked"
    assert stages["enrich"]["reason"] == "chunks_missing"
    assert stages["index"]["state"] == "blocked"
    assert stages["index"]["reason"] == "enriched_chunks_missing"
    assert stages["analyze"]["state"] == "blocked"
    assert all(not s["can_run"] for s in stages.values() if s["state"] == "blocked")


def test_audio_present_unblocks_transcribe(tmp_path: Path) -> None:
    d = _make_meeting(tmp_path)
    _touch(d, "source/audio_16k_mono.wav")
    stages = _stage_map(pipeline_readiness(MEETING_ID, d))
    assert stages["transcribe"]["state"] == "ready"
    assert stages["transcribe"]["can_run"] is True
    assert stages["transcribe"]["reason"] is None
    # extract_audio output exists → done, no re-run without force
    assert stages["extract_audio"]["state"] == "done"
    assert stages["extract_audio"]["can_run"] is False
    assert stages["extract_audio"]["reason"] == "already_done"


def test_diarize_blocked_when_optional_runtime_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = _make_meeting(tmp_path)
    _touch(d, "source/audio_16k_mono.wav")
    import asu_june_bot.jobs.runner as runner_mod

    monkeypatch.setitem(
        runner_mod.STAGE_COMMANDS["diarize"],
        "preflight",
        lambda _meeting_dir: (
            "sherpa-onnx diarization dependencies are not installed "
            "(sherpa_onnx). Install them in an isolated env with "
            "requirements-diarization.txt."
        ),
    )

    stages = _stage_map(pipeline_readiness(MEETING_ID, d))
    assert stages["diarize"]["state"] == "blocked"
    assert stages["diarize"]["can_run"] is False
    assert stages["diarize"]["reason"] == "diarization_runtime_missing"
    assert "requirements-diarization.txt" in stages["diarize"]["detail"]


def test_transcript_unblocks_merge(tmp_path: Path) -> None:
    d = _make_meeting(tmp_path)
    _touch(d, "transcript/segments.jsonl")
    stages = _stage_map(pipeline_readiness(MEETING_ID, d))
    assert stages["transcribe"]["state"] == "done"
    assert stages["merge"]["state"] == "ready"


def test_chunks_unblock_enrich(tmp_path: Path) -> None:
    d = _make_meeting(tmp_path)
    _touch(d, "transcript/chunks.jsonl")
    stages = _stage_map(pipeline_readiness(MEETING_ID, d))
    assert stages["chunk"]["state"] == "done"
    assert stages["enrich"]["state"] == "ready"


def test_enriched_unblocks_index_and_analyze(tmp_path: Path) -> None:
    d = _make_meeting(tmp_path)
    _touch(d, "artifacts/enriched_chunks.jsonl")
    stages = _stage_map(pipeline_readiness(MEETING_ID, d))
    assert stages["index"]["state"] == "ready"
    assert stages["analyze"]["state"] == "ready"


def test_index_done_via_rag_indexed_artifacts(tmp_path: Path) -> None:
    d = _make_meeting(tmp_path, {"rag": {"indexed_artifacts": ["artifacts/enriched_chunks.jsonl"]}})
    stages = _stage_map(pipeline_readiness(MEETING_ID, d))
    assert stages["index"]["state"] == "done"
    assert stages["index"]["can_run"] is False


def test_analyze_done_via_summary(tmp_path: Path) -> None:
    d = _make_meeting(tmp_path)
    _touch(d, "artifacts/summary.md")
    stages = _stage_map(pipeline_readiness(MEETING_ID, d))
    assert stages["analyze"]["state"] == "done"


def test_payload_shape_and_no_paths(tmp_path: Path) -> None:
    d = _make_meeting(tmp_path)
    _touch(d, "source/audio_16k_mono.wav")
    payload = pipeline_readiness(MEETING_ID, d)
    assert payload["meeting_id"] == MEETING_ID
    assert payload["status"] == "new"
    dumped = json.dumps(payload, ensure_ascii=False)
    assert str(d) not in dumped
    assert str(tmp_path) not in dumped
    for stage in payload["stages"]:
        for key in ("stage", "label", "state", "can_run", "reason",
                    "required_artifacts", "produced_artifacts"):
            assert key in stage
        assert stage["state"] in ("done", "ready", "blocked")


def test_stages_sorted_by_order(tmp_path: Path) -> None:
    d = _make_meeting(tmp_path)
    payload = pipeline_readiness(MEETING_ID, d)
    orders = [s["order"] for s in payload["stages"]]
    assert orders == sorted(orders)
    assert [s["stage"] for s in payload["stages"]][0] == "extract_audio"


# ---------------------------------------------------------------------------
# API: GET /meetings/{id}/pipeline/readiness
# ---------------------------------------------------------------------------

def _make_client(root: Path) -> TestClient:
    os.environ["MEETINGAGENT_API_TOKEN"] = TOKEN
    repo = AuthRepository(root / "_auth.db")
    repo.initialize()
    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)
    app.state.asu_june_bot = FakeState(
        meetings_service=MeetingsService(root),
        job_runner=JobRunner(),
        local_auth_service=LocalAuthService(repo),
        admin_service=AdminService(repo),
    )
    return client


def test_api_returns_readiness_map(tmp_path: Path) -> None:
    d = _make_meeting(tmp_path)
    _touch(d, "source/audio_16k_mono.wav")
    client = _make_client(tmp_path)
    resp = client.get(f"/meetings/{MEETING_ID}/pipeline/readiness", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["meeting_id"] == MEETING_ID
    stages = _stage_map(body)
    assert stages["transcribe"]["state"] == "ready"
    assert body["job_recovery"] is None


def test_api_returns_path_safe_recovery_summary(tmp_path: Path) -> None:
    d = _make_meeting(tmp_path)
    _touch(d, "source/audio_16k_mono.wav")
    client = _make_client(tmp_path)
    runner = client.app.state.asu_june_bot.job_runner
    runner.history.append(
        JobState(
            job_id="recovered-1",
            meeting_id=MEETING_ID,
            stage="transcribe",
            status="failed",
            started_at="2026-07-11T10:00:00+00:00",
            finished_at="2026-07-11T10:01:00+00:00",
            recovery_status="orphaned_process_missing",
            _meeting_dir=d,
        )
    )

    resp = client.get(f"/meetings/{MEETING_ID}/pipeline/readiness", headers=AUTH)

    assert resp.status_code == 200
    assert resp.json()["job_recovery"] == {
        "job_id": "recovered-1",
        "kind": "stage",
        "status": "failed",
        "recovery_status": "orphaned_process_missing",
        "can_cancel": False,
    }
    assert str(tmp_path) not in resp.text


def test_api_unknown_meeting_404(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    resp = client.get("/meetings/nope__missing/pipeline/readiness", headers=AUTH)
    assert resp.status_code == 404


def test_api_unsafe_meeting_id_404(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    resp = client.get("/meetings/..%2Fetc/pipeline/readiness", headers=AUTH)
    assert resp.status_code == 404


def test_api_requires_auth(tmp_path: Path) -> None:
    _make_meeting(tmp_path)
    client = _make_client(tmp_path)
    resp = client.get(f"/meetings/{MEETING_ID}/pipeline/readiness")
    assert resp.status_code == 401
