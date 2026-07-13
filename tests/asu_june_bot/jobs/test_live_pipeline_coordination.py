from __future__ import annotations

import multiprocessing
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from queue import Empty
from typing import Any

import pytest

from asu_june_bot.jobs.runner import JobRunner
from asu_june_bot.jobs.store import JobStore
from asu_june_bot.live_sessions.service import LiveSessionService
from asu_june_bot.live_sessions.store import LiveSessionStore, now_iso
from asu_june_bot.meeting_work import (
    MeetingWorkConflict,
    MeetingWorkCoordinator,
    MeetingWorkStateError,
)


MEETING_ID = "2026-07-13__coordination"


def _job_record(meeting_id: str = MEETING_ID) -> dict[str, Any]:
    return {
        "job_id": str(uuid.uuid4()),
        "meeting_id": meeting_id,
        "kind": "stage",
        "stage": "transcribe",
        "status": "starting",
        "started_at": now_iso(),
    }


def _pipeline_record(meeting_id: str = MEETING_ID) -> dict[str, Any]:
    return {
        "job_id": str(uuid.uuid4()),
        "meeting_id": meeting_id,
        "kind": "pipeline",
        "status": "running",
        "started_at": now_iso(),
    }


def _live_record(
    meeting_id: str = MEETING_ID,
    *,
    source: str = "MIC",
) -> dict[str, Any]:
    timestamp = now_iso()
    return {
        "session_id": str(uuid.uuid4()),
        "meeting_id": meeting_id,
        "source": source,
        "status": "starting",
        "engine": "vosk",
        "model": "synthetic",
        "vad": "silero",
        "created_at": timestamp,
        "started_at": timestamp,
        "updated_at": timestamp,
        "finished_at": None,
        "last_event_id": 1,
        "events": [
            {
                "event_id": 1,
                "type": "status",
                "timestamp": timestamp,
                "status": "starting",
            }
        ],
        "warnings": [],
        "error": None,
        "artifact_keys": [],
    }


def _coordinator(root: Path) -> tuple[MeetingWorkCoordinator, JobStore, LiveSessionStore]:
    job_store = JobStore(root / "jobs.json")
    live_store = LiveSessionStore(root / "live.json", active_sessions_max=2)
    coordinator = MeetingWorkCoordinator(
        root / "meeting_work.lock",
        job_store=job_store,
        live_store=live_store,
    )
    return coordinator, job_store, live_store


def _process_reserve(
    kind: str,
    root_value: str,
    start_event,
    result_queue,
) -> None:
    root = Path(root_value)
    coordinator, _job_store, _live_store = _coordinator(root)
    start_event.wait(timeout=10)
    try:
        if kind == "live":
            coordinator.reserve_live(_live_record())
        else:
            coordinator.reserve_job(_job_record())
        result_queue.put((kind, "reserved", None))
    except MeetingWorkConflict as exc:
        result_queue.put((kind, "conflict", exc.code))
    except Exception as exc:  # pragma: no cover - diagnostic for child failures
        result_queue.put((kind, "error", type(exc).__name__))


def test_live_rejected_when_stage_job_owns_same_meeting(tmp_path: Path) -> None:
    coordinator, _job_store, _live_store = _coordinator(tmp_path)
    coordinator.reserve_job(_job_record())

    with pytest.raises(MeetingWorkConflict) as caught:
        coordinator.reserve_live(_live_record())

    assert caught.value.code == "offline_job_active"
    assert str(tmp_path) not in caught.value.public_message


def test_live_rejected_when_pipeline_owns_same_meeting(tmp_path: Path) -> None:
    coordinator, _job_store, _live_store = _coordinator(tmp_path)
    coordinator.reserve_pipeline(_pipeline_record())

    with pytest.raises(MeetingWorkConflict) as caught:
        coordinator.reserve_live(_live_record())

    assert caught.value.code == "offline_job_active"


def test_stage_and_pipeline_rejected_when_live_owns_same_meeting(tmp_path: Path) -> None:
    coordinator, _job_store, _live_store = _coordinator(tmp_path)
    coordinator.reserve_live(_live_record())

    with pytest.raises(MeetingWorkConflict) as stage_conflict:
        coordinator.reserve_job(_job_record())
    with pytest.raises(MeetingWorkConflict) as pipeline_conflict:
        coordinator.reserve_pipeline(_pipeline_record())

    assert stage_conflict.value.code == "live_session_active"
    assert pipeline_conflict.value.code == "live_session_active"


def test_mic_and_sys_can_run_together(tmp_path: Path) -> None:
    coordinator, _job_store, live_store = _coordinator(tmp_path)

    coordinator.reserve_live(_live_record(source="MIC"))
    coordinator.reserve_live(_live_record(source="SYS"))

    active = [
        record
        for record in live_store.load()["sessions"]
        if record["status"] in {"starting", "running", "stopping"}
    ]
    assert {record["source"] for record in active} == {"MIC", "SYS"}


def test_work_for_different_meetings_does_not_conflict(tmp_path: Path) -> None:
    coordinator, job_store, live_store = _coordinator(tmp_path)

    coordinator.reserve_live(_live_record("meeting-live"))
    coordinator.reserve_job(_job_record("meeting-offline"))

    assert live_store.load()["sessions"][0]["meeting_id"] == "meeting-live"
    assert job_store.load()["active_job"]["meeting_id"] == "meeting-offline"


def test_thread_race_has_exactly_one_winner(tmp_path: Path) -> None:
    first, _job_store, _live_store = _coordinator(tmp_path)
    second, _other_job_store, _other_live_store = _coordinator(tmp_path)
    barrier = threading.Barrier(2)

    def attempt(kind: str, coordinator: MeetingWorkCoordinator) -> tuple[str, str | None]:
        barrier.wait(timeout=5)
        try:
            if kind == "live":
                coordinator.reserve_live(_live_record())
            else:
                coordinator.reserve_job(_job_record())
            return "reserved", None
        except MeetingWorkConflict as exc:
            return "conflict", exc.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        live_result = executor.submit(attempt, "live", first)
        job_result = executor.submit(attempt, "job", second)
        results = [live_result.result(timeout=10), job_result.result(timeout=10)]

    assert [status for status, _code in results].count("reserved") == 1
    assert [status for status, _code in results].count("conflict") == 1
    assert next(code for status, code in results if status == "conflict") in {
        "live_session_active",
        "offline_job_active",
    }


def test_process_race_has_exactly_one_winner(tmp_path: Path) -> None:
    context = multiprocessing.get_context("spawn")
    start_event = context.Event()
    result_queue = context.Queue()
    processes = [
        context.Process(
            target=_process_reserve,
            args=(kind, str(tmp_path), start_event, result_queue),
        )
        for kind in ("live", "job")
    ]
    for process in processes:
        process.start()
    start_event.set()
    results = []
    try:
        for _ in processes:
            results.append(result_queue.get(timeout=20))
    except Empty:
        pytest.fail("coordination child process did not report a result")
    finally:
        for process in processes:
            process.join(timeout=10)
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)

    assert all(process.exitcode == 0 for process in processes)
    assert [status for _kind, status, _code in results].count("reserved") == 1
    assert [status for _kind, status, _code in results].count("conflict") == 1


def test_stale_live_recovery_releases_offline_work(tmp_path: Path) -> None:
    coordinator, job_store, live_store = _coordinator(tmp_path)
    coordinator.reserve_live(_live_record())

    recovered = live_store.recover_active()
    coordinator.reserve_job(_job_record())

    assert recovered[0]["status"] == "stale"
    assert job_store.load()["active_job"]["meeting_id"] == MEETING_ID


@pytest.mark.parametrize("terminal_status", ["completed", "cancelled"])
def test_terminal_job_release_allows_live_start(
    tmp_path: Path,
    terminal_status: str,
) -> None:
    coordinator, job_store, live_store = _coordinator(tmp_path)
    record = _job_record()
    coordinator.reserve_job(record)

    record["status"] = terminal_status
    job_store.finish_job(record, f"job_{terminal_status}")
    coordinator.reserve_live(_live_record())

    assert job_store.load()["active_job"] is None
    assert live_store.load()["sessions"][-1]["status"] == "starting"


def test_unreadable_opposing_state_fails_closed_without_paths(tmp_path: Path) -> None:
    coordinator, _job_store, live_store = _coordinator(tmp_path)
    live_store.path.parent.mkdir(parents=True, exist_ok=True)
    live_store.path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(MeetingWorkStateError) as caught:
        coordinator.reserve_job(_job_record())

    assert caught.value.code == "meeting_work_state_unavailable"
    assert str(tmp_path) not in caught.value.public_message


def test_runner_rejects_coordinator_for_different_job_store(tmp_path: Path) -> None:
    coordinator, _job_store, _live_store = _coordinator(tmp_path / "first")

    with pytest.raises(ValueError, match="different job store"):
        JobRunner(
            store=JobStore(tmp_path / "second" / "jobs.json"),
            coordinator=coordinator,
        )


def test_live_service_rejects_mismatched_supplied_store_path(tmp_path: Path) -> None:
    _coordinator_value, _job_store, live_store = _coordinator(tmp_path / "first")

    with pytest.raises(ValueError, match="state_path does not match"):
        LiveSessionService(
            meetings_root=tmp_path / "meetings",
            state_path=tmp_path / "second" / "live.json",
            model_path=tmp_path / "model",
            store=live_store,
        )
