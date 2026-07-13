from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from meeting_agent.transcription.refinement import (
    LiveRefinementError,
    begin_live_refinement,
    can_resume_live_refinement,
    complete_live_refinement,
    fail_live_refinement,
    live_refinement_status,
    prepare_live_refinement,
)


MEETING_ID = "2026-07-13__live-refinement"
NOW = "2026-07-13T12:00:00+03:00"


def _write(path: Path, content: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _fixture(tmp_path: Path, source: str = "MIC") -> tuple[Path, dict]:
    meeting_dir = tmp_path / MEETING_ID
    audio_rel = f"source/live_audio.{source}.wav"
    segments_rel = f"transcript/live/live_segments.{source}.jsonl"
    report_rel = f"transcript/live/live_report.{source}.json"
    _write(meeting_dir / audio_rel, "pcm")
    _write(meeting_dir / segments_rel, '{"text":"draft"}\n')
    _write(
        meeting_dir / report_rel,
        json.dumps(
            {
                "engine": "vosk",
                "model": r"C:\Users\private\vosk-model",
                "duration_seconds": 10.0,
                "elapsed_seconds": 9.0,
                "segments_count": 2,
                "chars_count": 20,
                "started_at": NOW,
                "finished_at": NOW,
                "backend_metrics": {"private_path": r"C:\Users\private"},
            }
        ),
    )
    suffix = source.lower()
    card = {
        "schema_version": 1,
        "meeting_id": MEETING_ID,
        "title": "Live refinement",
        "date": "2026-07-13",
        "processing_status": "processing",
        "participants": [],
        "source": {
            "kind": "live_session",
            "media_files": [{"path": audio_rel, "media_type": "audio"}],
            "audio_tracks": [source],
        },
        "artifacts": {
            f"live_audio_{suffix}": audio_rel,
            f"live_segments_{suffix}": segments_rel,
            f"live_report_{suffix}": report_rel,
        },
        "classification": {},
        "links": {},
        "retention": {"policy": "default"},
        "rag": {
            "index_policy": "structured_artifacts_and_final_transcript",
            "no_index_artifacts": [audio_rel, segments_rel, report_rel],
        },
        "created_at": NOW,
        "updated_at": NOW,
    }
    return meeting_dir, card


def _validate(card: dict) -> None:
    schema = json.loads(
        (Path(__file__).resolve().parents[2] / "configs/schemas/meeting.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator(schema).validate(card)


def test_prepare_refinement_requires_registered_no_index_live_contract(tmp_path: Path) -> None:
    meeting_dir, card = _fixture(tmp_path)

    prepared = prepare_live_refinement(meeting_dir, card, "MIC")

    assert prepared["media_path"] == "source/live_audio.MIC.wav"
    assert prepared["live"]["engine"] == "vosk"
    assert prepared["live"]["model"] is None
    assert "backend_metrics" not in prepared["live"]
    assert "private" not in json.dumps(prepared)


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda card: card["source"].update(media_files=[]), "live_audio_not_registered"),
        (lambda card: card["rag"].update(no_index_artifacts=[]), "live_draft_index_policy_invalid"),
        (
            lambda card: card["artifacts"].update(live_audio_mic="../private.wav"),
            "live_audio_missing",
        ),
    ],
)
def test_prepare_refinement_fails_closed_on_unsafe_card(
    tmp_path: Path,
    mutation,
    code: str,
) -> None:
    meeting_dir, card = _fixture(tmp_path)
    mutation(card)

    with pytest.raises(LiveRefinementError) as exc:
        prepare_live_refinement(meeting_dir, card, "MIC")

    assert exc.value.code == code


def test_failed_refinement_reuses_only_new_verified_partial_segments(tmp_path: Path) -> None:
    meeting_dir, card = _fixture(tmp_path)
    canonical = meeting_dir / "transcript/segments.jsonl"
    _write(canonical, '{"text":"old canonical"}\n')
    card["artifacts"]["segments"] = "transcript/segments.jsonl"
    begin_live_refinement(
        card,
        meeting_dir,
        source="MIC",
        engine="faster-whisper",
        model="large-v3-turbo",
        started_at=NOW,
    )
    assert not can_resume_live_refinement(
        card, meeting_dir, source="MIC", engine="faster-whisper"
    )

    _write(canonical, '{"text":"new partial"}\n')
    fail_live_refinement(
        card,
        meeting_dir,
        source="MIC",
        error_code="refinement_artifact_validation",
        finished_at=NOW,
    )

    assert can_resume_live_refinement(
        card, meeting_dir, source="MIC", engine="faster-whisper"
    )
    assert not can_resume_live_refinement(card, meeting_dir, source="MIC", engine="gigaam")
    _write(canonical, '{"text":"tampered"}\n')
    assert not can_resume_live_refinement(
        card, meeting_dir, source="MIC", engine="faster-whisper"
    )


def test_complete_refinement_preserves_draft_and_writes_safe_comparison(tmp_path: Path) -> None:
    meeting_dir, card = _fixture(tmp_path)
    draft_before = (meeting_dir / card["artifacts"]["live_segments_mic"]).read_bytes()
    begin_live_refinement(
        card,
        meeting_dir,
        source="MIC",
        engine="faster-whisper",
        model="large-v3-turbo",
        started_at=NOW,
    )

    report_path = complete_live_refinement(
        card,
        meeting_dir,
        source="MIC",
        offline_report={
            "engine": "faster-whisper",
            "model": "large-v3-turbo",
            "duration_seconds": 11.5,
            "elapsed_seconds": 22.0,
            "segments_count": 3,
            "chars_count": 35,
            "started_at": NOW,
            "finished_at": NOW,
            "backend_metrics": {"source_path": r"C:\private\audio.wav"},
        },
        finished_at=NOW,
    )

    assert (meeting_dir / card["artifacts"]["live_segments_mic"]).read_bytes() == draft_before
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["comparison"] == {
        "duration_delta_seconds": 1.5,
        "segments_count_delta": 1,
        "chars_count_delta": 15,
    }
    assert "backend_metrics" not in json.dumps(report)
    assert "private" not in json.dumps(report)
    assert card["live_refinements"]["MIC"]["state"] == "final"
    assert card["artifacts"]["live_refinement_mic"] in card["rag"]["no_index_artifacts"]
    _validate(card)


def test_status_distinguishes_draft_refining_interrupted_and_final(tmp_path: Path) -> None:
    meeting_dir, card = _fixture(tmp_path)
    assert live_refinement_status(meeting_dir, card, source="MIC")["state"] == "draft"

    begin_live_refinement(
        card,
        meeting_dir,
        source="MIC",
        engine="gigaam",
        model="gigaam/v3_e2e_rnnt",
        started_at=NOW,
    )
    active = {
        "job_id": "job-1",
        "meeting_id": MEETING_ID,
        "stage": "transcribe",
        "status": "running",
        "started_at": NOW,
        "stderr_tail": [r"C:\private\must-not-leak"],
        "operation": {"kind": "live_refinement", "source": "MIC"},
    }
    running = live_refinement_status(
        meeting_dir, card, source="MIC", active_job=active
    )
    assert running["state"] == "refining"
    assert running["job"] == {
        "job_id": "job-1",
        "status": "running",
        "started_at": NOW,
    }
    wrong_source_job = dict(active)
    wrong_source_job["operation"] = {"kind": "live_refinement", "source": "SYS"}
    assert live_refinement_status(
        meeting_dir, card, source="MIC", active_job=wrong_source_job
    )["state"] == "failed"
    interrupted = live_refinement_status(meeting_dir, card, source="MIC")
    assert interrupted["state"] == "failed"
    assert interrupted["reason"] == "refinement_interrupted"


def test_status_is_unavailable_without_complete_live_source(tmp_path: Path) -> None:
    meeting_dir, card = _fixture(tmp_path)
    (meeting_dir / "source/live_audio.MIC.wav").unlink()

    status = live_refinement_status(meeting_dir, card, source="MIC")

    assert status == {
        "source": "MIC",
        "state": "unavailable",
        "can_refine": False,
        "can_resume": False,
        "can_force": False,
        "reason": "live_audio_missing",
    }


def test_final_state_without_comparison_report_is_failed(tmp_path: Path) -> None:
    meeting_dir, card = _fixture(tmp_path)
    card["live_refinements"] = {
        "MIC": {
            "source": "MIC",
            "state": "final",
            "offline_engine": "faster-whisper",
            "offline_model": "large-v3-turbo",
            "started_at": NOW,
            "finished_at": NOW,
            "report_artifact_key": "live_refinement_mic",
        }
    }

    status = live_refinement_status(meeting_dir, card, source="MIC")

    assert status["state"] == "failed"
    assert status["reason"] == "refinement_report_missing"
    assert status["can_resume"] is True
