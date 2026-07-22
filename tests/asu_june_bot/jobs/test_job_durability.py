from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import asu_june_bot.jobs.processes as process_mod  # noqa: E402
import asu_june_bot.jobs.runner as runner_mod  # noqa: E402
import asu_june_bot.jobs.store as store_mod  # noqa: E402
from asu_june_bot.jobs.runner import (  # noqa: E402
    JobAlreadyRunning,
    JobRunner,
    JobState,
    PipelineJobState,
    _job_record,
    _pipeline_record,
)
from asu_june_bot.jobs.store import (  # noqa: E402
    JobStore,
    JobStoreConflict,
    JobStoreError,
)


MEETING_ID = "2026-07-11__durability"


def _meeting(root: Path) -> Path:
    meeting_dir = root / MEETING_ID
    meeting_dir.mkdir(parents=True, exist_ok=True)
    (meeting_dir / "meeting.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "meeting_id": MEETING_ID,
                "title": "Durability test",
                "status": "new",
                "processing_status": "processing",
                "source": {"kind": "offline_record", "media_files": []},
                "artifacts": {},
                "rag": {},
            }
        ),
        encoding="utf-8",
    )
    return meeting_dir


def _job(
    meeting_dir: Path,
    *,
    job_id: str = "job-1",
    status: str = "running",
    pid: int | None = 2_000_000_000,
    identity: str | None = "test:identity",
) -> JobState:
    return JobState(
        job_id=job_id,
        meeting_id=MEETING_ID,
        stage="chunk",
        status=status,
        started_at="2026-07-11T10:00:00+00:00",
        pid=pid,
        process_identity=identity,
        _meeting_dir=meeting_dir,
    )


def _pipeline(meeting_dir: Path, *, job_id: str = "pipeline-1") -> PipelineJobState:
    return PipelineJobState(
        job_id=job_id,
        meeting_id=MEETING_ID,
        profile="default",
        force=False,
        status="running",
        started_at="2026-07-11T10:00:00+00:00",
        current_stage="chunk",
        stages=[
            {
                "stage": "chunk",
                "status": "running",
                "job_id": "job-1",
                "exit_code": None,
                "reason": None,
            },
            {
                "stage": "enrich",
                "status": "pending",
                "job_id": None,
                "exit_code": None,
                "reason": None,
            },
        ],
        _meeting_dir=meeting_dir,
    )


def test_store_bounds_history_and_events(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs.json", history_max=2, events_max=3)
    meeting_dir = _meeting(tmp_path)
    for index in range(4):
        job = _job(
            meeting_dir,
            job_id=f"job-{index}",
            status="completed",
            pid=None,
            identity=None,
        )
        record = _job_record(job)
        store.reserve_job(record)
        store.finish_job(record, "completed")

    state = store.load()
    assert [item["job_id"] for item in state["history"]] == ["job-2", "job-3"]
    assert len(state["events"]) == 3


def test_store_atomic_replace_preserves_previous_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "jobs.json"
    store = JobStore(path)
    meeting_dir = _meeting(tmp_path)
    first = _job(
        meeting_dir,
        status="completed",
        pid=None,
        identity=None,
    )
    store.reserve_job(_job_record(first))
    store.finish_job(_job_record(first), "completed")
    before = path.read_bytes()

    def fail_replace(_source: Path, _target: Path) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(store_mod.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated replace failure"):
        store.reserve_job(
            _job_record(
                _job(
                    meeting_dir,
                    job_id="job-2",
                    status="starting",
                    pid=None,
                    identity=None,
                )
            )
        )

    assert path.read_bytes() == before
    assert not list(tmp_path.glob(".jobs.json.*.tmp"))


def test_corrupt_store_fails_closed_at_runner_startup(tmp_path: Path) -> None:
    path = tmp_path / "jobs.json"
    path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(JobStoreError, match="unreadable"):
        JobRunner(state_path=path, meetings_root=tmp_path)


def test_oversized_store_fails_before_json_decode(tmp_path: Path) -> None:
    path = tmp_path / "jobs.json"
    path.write_bytes(b"{" + b"x" * 64)
    store = JobStore(path, max_state_bytes=32)
    with pytest.raises(JobStoreError, match="size limit"):
        store.load()


def test_second_stale_runner_cannot_reserve_active_slot(tmp_path: Path) -> None:
    path = tmp_path / "jobs.json"
    meeting_dir = _meeting(tmp_path)
    first = JobRunner(state_path=path, meetings_root=tmp_path)
    second = JobRunner(state_path=path, meetings_root=tmp_path)
    assert first.store is not None
    first.store.reserve_job(
        _job_record(
            _job(
                meeting_dir,
                status="starting",
                pid=None,
                identity=None,
            )
        )
    )

    with pytest.raises(JobAlreadyRunning, match="durable"):
        asyncio.run(
            second.submit(
                meeting_id=MEETING_ID,
                meeting_dir=meeting_dir,
                stage="chunk",
            )
        )


def test_store_rejects_parallel_pipeline_reservation(tmp_path: Path) -> None:
    path = tmp_path / "jobs.json"
    meeting_dir = _meeting(tmp_path)
    store = JobStore(path)
    store.reserve_pipeline(_pipeline_record(_pipeline(meeting_dir)))
    with pytest.raises(JobStoreConflict):
        store.reserve_pipeline(_pipeline_record(_pipeline(meeting_dir, job_id="pipeline-2")))


def test_missing_process_recovers_as_failed_and_ready_for_retry(tmp_path: Path) -> None:
    path = tmp_path / "jobs.json"
    meeting_dir = _meeting(tmp_path)
    store = JobStore(path)
    store.reserve_job(_job_record(_job(meeting_dir)))

    runner = JobRunner(state_path=path, meetings_root=tmp_path)

    assert runner.active_job is None
    recovered = runner.history[-1]
    assert recovered.status == "failed"
    assert recovered.recovery_status == "orphaned_process_missing"
    assert runner.recovery_summary(MEETING_ID) == {
        "job_id": "job-1",
        "kind": "stage",
        "status": "failed",
        "recovery_status": "orphaned_process_missing",
        "can_cancel": False,
    }
    assert store.load()["active_job"] is None
    last_error = json.loads((meeting_dir / "meeting.json").read_text(encoding="utf-8"))[
        "last_error"
    ]
    assert last_error["stage"] == "chunk"
    assert last_error["job_id"] == "job-1"


def test_live_refinement_operation_survives_durable_recovery(tmp_path: Path) -> None:
    path = tmp_path / "jobs.json"
    meeting_dir = _meeting(tmp_path)
    job = JobState(
        job_id="refine-1",
        meeting_id=MEETING_ID,
        stage="transcribe",
        status="running",
        started_at="2026-07-11T10:00:00+00:00",
        pid=2_000_000_000,
        process_identity="test:identity",
        operation={"kind": "live_refinement", "source": "SYS"},
        _meeting_dir=meeting_dir,
    )
    store = JobStore(path)
    store.reserve_job(_job_record(job))

    runner = JobRunner(state_path=path, meetings_root=tmp_path)

    assert runner.history[-1].operation == {
        "kind": "live_refinement",
        "source": "SYS",
    }
    assert runner.history[-1].as_dict()["operation"] == {
        "kind": "live_refinement",
        "source": "SYS",
    }


def test_live_process_recovers_as_orphan_and_blocks_new_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "jobs.json"
    meeting_dir = _meeting(tmp_path)
    store = JobStore(path)
    store.reserve_job(_job_record(_job(meeting_dir)))
    monkeypatch.setattr(runner_mod, "process_matches", lambda pid, identity: True)

    runner = JobRunner(state_path=path, meetings_root=tmp_path)

    assert runner.active_job is not None
    assert runner.active_job.status == "orphaned"
    assert runner.active_job.recovery_status == "orphaned_process_alive"
    with pytest.raises(JobAlreadyRunning):
        asyncio.run(
            runner.submit(
                meeting_id=MEETING_ID,
                meeting_dir=meeting_dir,
                stage="chunk",
            )
        )


def test_recovered_orphan_cancel_is_idempotent_and_clears_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "jobs.json"
    meeting_dir = _meeting(tmp_path)
    store = JobStore(path)
    store.reserve_job(_job_record(_job(meeting_dir)))
    monkeypatch.setattr(runner_mod, "process_matches", lambda pid, identity: True)
    runner = JobRunner(state_path=path, meetings_root=tmp_path)
    calls: list[tuple[int | None, str | None]] = []

    async def terminate(**kwargs) -> bool:
        calls.append((kwargs["pid"], kwargs["identity"]))
        return True

    monkeypatch.setattr(runner_mod, "terminate_process_tree", terminate)

    first = asyncio.run(runner.cancel("job-1"))
    second = asyncio.run(runner.cancel("job-1"))

    assert first is second
    assert first.status == "cancelled"
    assert calls == [(2_000_000_000, "test:identity")]
    assert runner.active_job is None
    assert store.load()["active_job"] is None
    assert [item.job_id for item in runner.history].count("job-1") == 1


def test_recovered_orphan_that_exits_before_cancel_clears_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "jobs.json"
    meeting_dir = _meeting(tmp_path)
    store = JobStore(path)
    store.reserve_job(_job_record(_job(meeting_dir)))
    process_alive = True
    monkeypatch.setattr(
        runner_mod,
        "process_matches",
        lambda _pid, _identity: process_alive,
    )
    runner = JobRunner(state_path=path, meetings_root=tmp_path)
    process_alive = False

    async def must_not_terminate(**_kwargs) -> bool:
        raise AssertionError("an exited orphan must not be terminated")

    monkeypatch.setattr(runner_mod, "terminate_process_tree", must_not_terminate)

    cancelled = asyncio.run(runner.cancel("job-1"))

    assert cancelled.status == "cancelled"
    assert cancelled.recovery_status == "orphaned_process_missing"
    assert runner.active_job is None
    assert store.load()["active_job"] is None
    assert runner.history[-1].job_id == "job-1"


def test_identity_mismatch_never_targets_process_tree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(process_mod, "_pid_alive", lambda _pid: True)
    monkeypatch.setattr(process_mod, "process_identity", lambda _pid: "new-process")
    assert process_mod.process_matches(42, "old-process") is False
    assert (
        asyncio.run(
            process_mod.terminate_process_tree(
                pid=42,
                identity="old-process",
                process=None,
            )
        )
        is False
    )


def test_missing_pipeline_process_recovers_terminal_state(tmp_path: Path) -> None:
    path = tmp_path / "jobs.json"
    meeting_dir = _meeting(tmp_path)
    store = JobStore(path)
    store.reserve_pipeline(_pipeline_record(_pipeline(meeting_dir)))

    runner = JobRunner(state_path=path, meetings_root=tmp_path)

    assert runner.active_pipeline is None
    recovered = runner.pipeline_history[-1]
    assert recovered.status == "failed"
    assert recovered.recovery_status == "orphaned_process_missing"
    assert recovered.stages[0]["status"] == "failed"
    assert recovered.stages[1]["status"] == "skipped"
    assert store.load()["active_pipeline"] is None


def test_completed_active_pipeline_is_not_downgraded_after_crash(tmp_path: Path) -> None:
    path = tmp_path / "jobs.json"
    meeting_dir = _meeting(tmp_path)
    pipeline = _pipeline(meeting_dir)
    pipeline.status = "completed"
    pipeline.current_stage = None
    pipeline.finished_at = "2026-07-11T10:05:00+00:00"
    pipeline.stages[0]["status"] = "completed"
    pipeline.stages[1]["status"] = "completed"
    store = JobStore(path)
    store.reserve_pipeline(_pipeline_record(pipeline))

    runner = JobRunner(state_path=path, meetings_root=tmp_path)

    assert runner.active_pipeline is None
    recovered = runner.pipeline_history[-1]
    assert recovered.status == "completed"
    assert recovered.recovery_status == "terminal_state_recovered"
    assert all(item["status"] == "completed" for item in recovered.stages)


def test_pipeline_and_child_recover_and_cancel_together(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "jobs.json"
    meeting_dir = _meeting(tmp_path)
    pipeline = _pipeline(meeting_dir)
    child = _job(meeting_dir)
    store = JobStore(path)
    store.reserve_pipeline(_pipeline_record(pipeline))
    store.reserve_job(_job_record(child), pipeline_id=pipeline.job_id)
    monkeypatch.setattr(runner_mod, "process_matches", lambda pid, identity: True)
    runner = JobRunner(state_path=path, meetings_root=tmp_path)

    assert runner.active_pipeline is not None
    assert runner.active_pipeline.status == "orphaned"
    assert runner.active_job is not None
    assert runner.get_active() is runner.active_pipeline

    async def terminate(**_kwargs) -> bool:
        return True

    monkeypatch.setattr(runner_mod, "terminate_process_tree", terminate)
    cancelled = asyncio.run(runner.cancel(pipeline.job_id))

    assert cancelled.status == "cancelled"
    assert runner.active_pipeline is None
    assert runner.active_job is None
    persisted = store.load()
    assert persisted["active_pipeline"] is None
    assert persisted["active_job"] is None


def test_process_match_requires_persisted_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(process_mod, "_pid_alive", lambda _pid: True)
    monkeypatch.setattr(process_mod, "process_identity", lambda _pid: "current")
    assert process_mod.process_matches(7, None) is False


def test_wait_treats_asyncio_terminal_returncode_as_gone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ExitedProcess:
        returncode = 1

    monkeypatch.setattr(process_mod, "process_matches", lambda _pid, _identity: True)
    assert (
        asyncio.run(process_mod._wait_until_gone(7, "windows:old", 0.01, ExitedProcess())) is True
    )


def test_cancel_during_preflight_never_launches_real_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    meeting_dir = _meeting(tmp_path)
    preflight_started = asyncio.Event()
    preflight_released = asyncio.Event()
    launches: list[tuple[str, ...]] = []

    class BlockingPreflight:
        pid = 12345
        returncode: int | None = None

        async def communicate(self):
            preflight_started.set()
            await preflight_released.wait()
            return b"", b""

        def terminate(self) -> None:
            self.returncode = -15
            preflight_released.set()

    async def fake_subprocess(*args, stdout, stderr):
        launches.append(tuple(args))
        assert "--dry-run" in args
        return BlockingPreflight()

    monkeypatch.setattr(runner_mod, "_create_subprocess", fake_subprocess)

    async def scenario() -> JobState:
        runner = JobRunner(
            state_path=tmp_path / "jobs.json",
            meetings_root=tmp_path,
        )
        submit_task = asyncio.create_task(
            runner.submit(
                meeting_id=MEETING_ID,
                meeting_dir=meeting_dir,
                stage="transcribe",
            )
        )
        await preflight_started.wait()
        assert runner.active_job is not None
        await runner.cancel(runner.active_job.job_id)
        result = await submit_task
        assert runner.active_job is None
        return result

    result = asyncio.run(scenario())
    assert result.status == "cancelled"
    assert len(launches) == 1
    assert "--dry-run" in launches[0]


def test_completed_pipeline_survives_runner_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    meeting_dir = _meeting(tmp_path)
    path = tmp_path / "jobs.json"

    class ImmediateProcess:
        pid = 12346
        returncode = 0

        async def communicate(self):
            return b"", b""

        def terminate(self) -> None:
            self.returncode = -15

    async def fake_subprocess(*args, stdout, stderr):
        return ImmediateProcess()

    monkeypatch.setattr(runner_mod, "_create_subprocess", fake_subprocess)

    async def scenario() -> PipelineJobState:
        runner = JobRunner(state_path=path, meetings_root=tmp_path)
        pipeline = await runner.submit_pipeline(
            meeting_id=MEETING_ID,
            meeting_dir=meeting_dir,
            stages=["transcribe"],
        )
        assert pipeline._task is not None
        await pipeline._task
        return pipeline

    completed = asyncio.run(scenario())
    restarted = JobRunner(state_path=path, meetings_root=tmp_path)

    assert completed.status == "completed"
    assert restarted.active_job is None
    assert restarted.active_pipeline is None
    assert restarted.pipeline_history[-1].job_id == completed.job_id
    assert restarted.pipeline_history[-1].status == "completed"
    assert restarted.history[-1].status == "completed"
