from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
from asu_june_bot.api.app import create_app
from asu_june_bot.auth.repository import AuthRepository
from asu_june_bot.auth.service import AdminService, LocalAuthService
from asu_june_bot.auth.throttle import LoginThrottle
from meeting_agent.jobs.readiness import _stage_done
from meeting_agent.jobs.runner import PIPELINE_PROFILES, JobRunner, _read_meeting_status
from meeting_agent.meetings.service import MeetingsService
from meeting_agent.meetings.qa import MeetingQAService
from meeting_agent.speakers.rebuild import rebuild_status


ROOT = Path(__file__).resolve().parents[3]
MEETING_ID = "2026-07-31__speaker-rebuild"
TOKEN = "speaker-rebuild-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@dataclass(slots=True)
class _State:
    meetings_service: MeetingsService
    job_runner: JobRunner
    local_auth_service: LocalAuthService
    admin_service: AdminService
    login_throttle: LoginThrottle = field(default_factory=LoginThrottle)


def _client(tmp_path: Path) -> tuple[TestClient, JobRunner]:
    os.environ["MEETINGAGENT_API_TOKEN"] = TOKEN
    repo = AuthRepository(tmp_path / "auth.db")
    repo.initialize()
    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)
    runner = JobRunner()
    app.state.asu_june_bot = _State(
        meetings_service=MeetingsService(tmp_path / "meetings"),
        job_runner=runner,
        local_auth_service=LocalAuthService(repo),
        admin_service=AdminService(repo),
    )
    return client, runner


def _card() -> dict:
    return {
        "schema_version": 1,
        "meeting_id": MEETING_ID,
        "title": "Speaker rebuild",
        "date": "2026-07-31",
        "language": "ru",
        "processing_status": "transcribed",
        "participants": [],
        "source": {"kind": "offline_record"},
        "artifacts": {
            "speaker_transcript": "transcript/speaker_transcript.jsonl",
        },
        "classification": {},
        "links": {},
        "retention": {"policy": "default"},
        "rag": {
            "index_policy": "structured_artifacts_and_final_transcript",
            "indexed_artifacts": [
                "transcript/chunks.jsonl",
                "artifacts/enriched_chunks.jsonl",
                "artifacts/decisions.json",
                "artifacts/tasks.json",
                "artifacts/risks.json",
                "artifacts/open_questions.json",
            ],
        },
        "created_at": "2026-07-31T09:00:00+03:00",
        "updated_at": "2026-07-31T09:00:00+03:00",
    }


def _meeting(tmp_path: Path) -> Path:
    meeting_dir = tmp_path / "meetings" / MEETING_ID
    (meeting_dir / "transcript").mkdir(parents=True)
    rows = [
        {
            "utterance_id": "utt-000001",
            "speaker": "SPEAKER_01",
            "source": "MIX",
            "start": 0.0,
            "end": 2.0,
            "text": "Согласовали выпуск.",
        },
        {
            "utterance_id": "utt-000002",
            "speaker": "SPEAKER_02",
            "source": "MIX",
            "start": 2.1,
            "end": 4.0,
            "text": "Нужно подготовить отчёт.",
        },
    ]
    (meeting_dir / "transcript" / "speaker_transcript.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    (meeting_dir / "meeting.json").write_text(
        json.dumps(_card(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return meeting_dir


def _run(script: str, *args: str) -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), *args],
        cwd=ROOT,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_speaker_edit_invalidates_only_dependent_outputs(tmp_path: Path) -> None:
    meeting_dir = _meeting(tmp_path)
    raw = meeting_dir / "transcript" / "speaker_transcript.jsonl"
    raw_hash = _sha(raw)
    service = MeetingsService(tmp_path / "meetings")

    service.update_speaker_mapping(
        MEETING_ID,
        {
            "SPEAKER_01": {"name": "Анна", "role": "PO"},
            "SPEAKER_02": {"name": "Борис", "role": "Аналитик"},
        },
    )
    service.set_speaker_overrides(
        MEETING_ID,
        ["utt-000002"],
        "SPEAKER_01",
        "editor-1",
    )

    card = service.get_meeting(MEETING_ID)
    assert card is not None
    assert card["speaker_curation"]["state"] == "stale"
    assert card["rag"]["indexed_artifacts"] == []
    assert _sha(raw) == raw_hash
    assert not _stage_done("chunk", meeting_dir, card)
    assert not _stage_done("index", meeting_dir, card)
    assert PIPELINE_PROFILES["speaker_rebuild"] == [
        "resolve_speakers",
        "chunk",
        "enrich",
        "index",
        "analyze",
        "index_artifacts",
    ]
    assert all(
        stage not in PIPELINE_PROFILES["speaker_rebuild"]
        for stage in ("extract_audio", "transcribe", "diarize", "merge")
    )


def test_fresh_pipeline_does_not_initialize_speaker_curation(
    tmp_path: Path,
) -> None:
    meeting_dir = _meeting(tmp_path)

    _run("25_resolve_speaker_transcript.py", "--meeting-dir", str(meeting_dir))

    card = json.loads((meeting_dir / "meeting.json").read_text(encoding="utf-8"))
    assert "speaker_curation" not in card
    assert (
        meeting_dir / "transcript" / "resolved_speaker_transcript.jsonl"
    ).is_file()
    assert MeetingsService(tmp_path / "meetings").get_speaker_rebuild_status(
        MEETING_ID
    ) == {
        "meeting_id": MEETING_ID,
        "state": "not_initialized",
        "needs_rebuild": False,
        "stages": [],
    }


def test_runner_keeps_reading_existing_meeting_status(tmp_path: Path) -> None:
    meeting_dir = _meeting(tmp_path)

    assert _read_meeting_status(meeting_dir) == "transcribed"


def test_targeted_rebuild_is_idempotent_and_updates_speakers(tmp_path: Path) -> None:
    meeting_dir = _meeting(tmp_path)
    service = MeetingsService(tmp_path / "meetings")
    service.update_speaker_mapping(
        MEETING_ID,
        {
            "SPEAKER_01": {"name": "Анна", "role": "PO"},
            "SPEAKER_02": {"name": "Борис", "role": "Аналитик"},
        },
    )
    service.set_speaker_overrides(
        MEETING_ID,
        ["utt-000002"],
        "SPEAKER_01",
        "editor-1",
    )
    service.prepare_speaker_rebuild(MEETING_ID)
    index_path = tmp_path / "meeting_chunks.jsonl"

    def rebuild() -> None:
        _run("25_resolve_speaker_transcript.py", "--meeting-dir", str(meeting_dir))
        _run("26_chunk_meeting.py", "--meeting-dir", str(meeting_dir), "--force")
        _run("27_enrich_meeting_chunks.py", "--meeting-dir", str(meeting_dir), "--force")
        _run(
            "28_index_meeting_chunks.py",
            "--meeting-dir",
            str(meeting_dir),
            "--output",
            str(index_path),
        )
        _run(
            "29_analyze_meeting.py",
            "--meeting-dir",
            str(meeting_dir),
            "--mode",
            "extractive",
            "--force",
        )
        _run(
            "32_index_meeting_artifacts.py",
            "--meeting-dir",
            str(meeting_dir),
            "--output",
            str(index_path),
        )

    raw_path = meeting_dir / "transcript" / "speaker_transcript.jsonl"
    raw_hash = _sha(raw_path)
    rebuild()
    rebuild()

    resolved = [
        json.loads(line)
        for line in (
            meeting_dir / "transcript" / "resolved_speaker_transcript.jsonl"
        ).read_text(encoding="utf-8").splitlines()
    ]
    assert [row["speaker"] for row in resolved] == ["SPEAKER_01", "SPEAKER_01"]
    assert all(row["speaker_name"] == "Анна" for row in resolved)
    assert _sha(raw_path) == raw_hash

    card = service.get_meeting(MEETING_ID)
    assert card is not None
    status = rebuild_status(card)
    assert status["state"] == "current"
    assert status["needs_rebuild"] is False
    assert all(item["current"] for item in status["stages"])

    index_rows = [
        json.loads(line)
        for line in index_path.read_text(encoding="utf-8").splitlines()
    ]
    keys = [
        (row["meeting_id"], row["source_type"], row["chunk_id"])
        for row in index_rows
    ]
    assert len(keys) == len(set(keys))
    assert any("Анна" in str(row.get("speaker_names")) for row in index_rows)


def test_workspace_exposes_explicit_rebuild_action() -> None:
    html = (
        ROOT / "src" / "meeting_agent" / "api" / "ui" / "templates" / "workspace.html"
    ).read_text(encoding="utf-8")
    js = (
        ROOT
        / "src"
        / "meeting_agent"
        / "api"
        / "ui"
        / "assets"
        / "v5"
        / "workspace.js"
    ).read_text(encoding="utf-8")
    assert 'id="speaker-rebuild-btn"' in html
    assert "/jobs/speaker-rebuild" in js
    assert "X-CSRF-Token" in js[js.index("async function startSpeakerRebuild") :]
    assert "extract_audio" not in js[
        js.index("async function startSpeakerRebuild") :
        js.index("async function createSpeakerProfile")
    ]


def test_rebuild_api_is_path_safe_and_uses_fixed_profile(tmp_path: Path) -> None:
    _meeting(tmp_path)
    service = MeetingsService(tmp_path / "meetings")
    service.update_speaker_mapping(
        MEETING_ID,
        {"SPEAKER_01": {"name": "Анна"}},
    )
    client, runner = _client(tmp_path)

    denied = client.get(f"/meetings/{MEETING_ID}/speakers/rebuild")
    assert denied.status_code == 401
    status = client.get(
        f"/meetings/{MEETING_ID}/speakers/rebuild",
        headers=AUTH,
    )
    assert status.status_code == 200
    body = status.json()
    assert body["state"] == "stale"
    assert body["needs_rebuild"] is True
    assert "source_revision" not in json.dumps(body)
    assert str(tmp_path) not in json.dumps(body)

    class _Pipeline:
        def as_dict(self) -> dict:
            return {
                "job_id": "rebuild-1",
                "meeting_id": MEETING_ID,
                "kind": "pipeline",
                "profile": "speaker_rebuild",
                "status": "running",
                "stages": [
                    {"stage": stage, "status": "pending"}
                    for stage in PIPELINE_PROFILES["speaker_rebuild"]
                ],
            }

    runner.submit_pipeline = AsyncMock(return_value=_Pipeline())  # type: ignore[method-assign]
    started = client.post(
        f"/meetings/{MEETING_ID}/jobs/speaker-rebuild",
        headers=AUTH,
        json={"resume": True},
    )
    assert started.status_code == 202, started.text
    assert [item["stage"] for item in started.json()["stages"]] == list(
        PIPELINE_PROFILES["speaker_rebuild"]
    )
    kwargs = runner.submit_pipeline.await_args.kwargs  # type: ignore[attr-defined]
    assert kwargs["profile"] == "speaker_rebuild"
    assert kwargs["force"] is False
    assert "stages" not in kwargs


def test_stale_speaker_index_is_not_used_by_search_or_chat(tmp_path: Path) -> None:
    _meeting(tmp_path)
    service = MeetingsService(tmp_path / "meetings")
    service.update_speaker_mapping(
        MEETING_ID,
        {"SPEAKER_01": {"name": "Анна"}},
    )
    index_path = tmp_path / "stale-index.jsonl"
    index_path.write_text(
        json.dumps(
            {
                "meeting_id": MEETING_ID,
                "source_type": "meeting_chunk",
                "chunk_id": "old",
                "text": "Старый спикер согласовал выпуск",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    qa = MeetingQAService(
        meetings_service=service,
        meeting_chunks_path=index_path,
    )

    search = qa.search(MEETING_ID, "кто согласовал")
    assert search is not None
    assert search["available"] is False
    assert search["stale_reason"] == "speaker_curation_changed"
    assert search["results"] == []

    chat = qa.chat(MEETING_ID, "кто согласовал")
    assert chat is not None
    assert chat["status"] == "stale"
    assert chat["retrieval_mode"] == "unavailable"
    assert chat["citations"] == []
