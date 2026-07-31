from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from meeting_agent.jobs.progress import (
    ProgressReporter,
    normalize_progress_snapshot,
    read_progress_snapshot,
    resolve_progress_path,
)
from meeting_agent.jobs.runner import JobState, PipelineJobState


def test_progress_reporter_writes_atomic_bounded_snapshot(tmp_path: Path) -> None:
    path = tmp_path / "runtime" / "progress" / "job.json"
    reporter = ProgressReporter(path, phase="transcribe:gigaam", unit="chunks")

    result = reporter.emit(3, 10, force=True)

    assert result["percent"] == 30.0
    assert read_progress_snapshot(path) == result
    assert path.stat().st_size < 32 * 1024
    assert not list(path.parent.glob(f".{path.name}.*.tmp"))


def test_progress_snapshot_marks_old_running_value_stale() -> None:
    old = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()

    result = normalize_progress_snapshot(
        {
            "phase": "transcribe:faster-whisper",
            "current": 12,
            "total": 120,
            "unit": "seconds",
            "updated_at": old,
        },
        running=True,
    )

    assert result is not None
    assert result["percent"] == 10.0
    assert result["stale"] is True


def test_progress_path_must_stay_inside_meeting(tmp_path: Path) -> None:
    meeting_dir = tmp_path / "meeting"
    meeting_dir.mkdir()

    assert resolve_progress_path(meeting_dir, "runtime/progress/job.json") == (
        meeting_dir / "runtime" / "progress" / "job.json"
    ).resolve()
    with pytest.raises(ValueError, match="inside the meeting"):
        resolve_progress_path(meeting_dir, tmp_path / "outside.json")


def test_invalid_or_oversized_progress_is_not_exposed(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text('{"phase":"x","current":"secret","unit":"seconds"}', encoding="utf-8")
    oversized = tmp_path / "oversized.json"
    oversized.write_text("x" * (32 * 1024 + 1), encoding="utf-8")

    assert read_progress_snapshot(invalid) is None
    assert read_progress_snapshot(oversized) is None


def test_job_state_exposes_sanitized_progress(tmp_path: Path) -> None:
    path = tmp_path / "runtime" / "progress" / "job.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "phase": "transcribe:faster-whisper",
                "current": 30,
                "total": 120,
                "unit": "seconds",
                "private_path": "C:/secret/video.mp4",
            }
        ),
        encoding="utf-8",
    )
    job = JobState(
        job_id="job",
        meeting_id="meeting",
        stage="transcribe",
        status="running",
        started_at="2026-07-31T10:00:00+00:00",
        _progress_path=path,
        _meeting_dir=tmp_path,
    )

    progress = job.as_dict()["progress"]

    assert progress["percent"] == 25.0
    assert "private_path" not in progress


def test_pipeline_exposes_child_and_aggregate_progress(tmp_path: Path) -> None:
    child = JobState(
        job_id="child",
        meeting_id="meeting",
        stage="transcribe",
        status="running",
        started_at="2026-07-31T10:00:00+00:00",
        _progress={
            "phase": "transcribe:gigaam",
            "current": 5,
            "total": 10,
            "unit": "chunks",
        },
    )
    pipeline = PipelineJobState(
        job_id="pipeline",
        meeting_id="meeting",
        profile="transcript_only",
        force=False,
        status="running",
        started_at="2026-07-31T10:00:00+00:00",
        current_stage="transcribe",
        stages=[
            {"stage": "extract_audio", "status": "completed"},
            {"stage": "transcribe", "status": "running"},
        ],
        _current_job=child,
        _meeting_dir=tmp_path,
    )

    payload = pipeline.as_dict()

    assert payload["progress"]["percent"] == 50.0
    assert payload["pipeline_progress"]["percent"] == 75.0


def test_pipeline_does_not_count_failure_skips_as_completed() -> None:
    pipeline = PipelineJobState(
        job_id="pipeline",
        meeting_id="meeting",
        profile="full",
        force=False,
        status="failed",
        started_at="2026-07-31T10:00:00+00:00",
        stages=[
            {"stage": "extract_audio", "status": "completed"},
            {"stage": "transcribe", "status": "failed"},
            {
                "stage": "diarize",
                "status": "skipped",
                "reason": "pipeline stopped on earlier failure",
            },
        ],
    )

    assert pipeline.as_dict()["pipeline_progress"]["percent"] == 33.3
