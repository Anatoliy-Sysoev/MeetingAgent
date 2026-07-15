from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from meeting_agent.jobs.runner import JobRunner, PreflightFailed
from meeting_agent.jobs.runtimes import (
    WorkerRuntimeRegistry,
    build_worker_runtime_registry,
)
from meeting_agent.jobs.store import JobStore


MEETING_ID = "2026-07-15__runtime-test"


class _ImmediateProcess:
    def __init__(self, *, returncode: int = 0, stderr: bytes = b"") -> None:
        self.returncode = returncode
        self.pid = 12345
        self._stderr = stderr

    async def communicate(self) -> tuple[bytes, bytes]:
        return b"", self._stderr


def _python_stub(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"stub")
    path.chmod(0o755)
    return path.resolve()


def _meeting(root: Path) -> Path:
    meeting_dir = root / MEETING_ID
    meeting_dir.mkdir(parents=True)
    (meeting_dir / "meeting.json").write_text(
        json.dumps(
            {
                "meeting_id": MEETING_ID,
                "processing_status": "new",
                "artifacts": {},
                "source": {"kind": "offline_record"},
            }
        ),
        encoding="utf-8",
    )
    return meeting_dir


def test_registry_uses_api_python_by_default(tmp_path: Path) -> None:
    fallback = _python_stub(tmp_path / "api" / "python")
    selected = WorkerRuntimeRegistry(fallback=fallback).select("transcribe")

    assert selected.executable == fallback
    assert selected.key == "api"
    assert selected.configured is False
    assert selected.available is True


def test_registry_selects_engine_specific_runtimes(tmp_path: Path) -> None:
    transcription = _python_stub(tmp_path / "transcription" / "python.exe")
    gigaam = _python_stub(tmp_path / "gigaam" / "python.exe")
    diarization = _python_stub(tmp_path / "diarization" / "python.exe")
    registry = WorkerRuntimeRegistry(
        {
            "transcription": transcription,
            "gigaam": gigaam,
            "diarization": diarization,
        }
    )

    assert registry.select("transcribe").executable == transcription
    assert registry.select("transcribe", {"asr_engine": "gigaam"}).executable == gigaam
    assert registry.select("diarize").executable == diarization


def test_config_builder_resolves_relative_paths_and_env_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_runtime = _python_stub(tmp_path / "workers" / "python.exe")
    env_runtime = _python_stub(tmp_path / "env" / "python.exe")
    monkeypatch.setenv("MEETINGAGENT_TRANSCRIPTION_PYTHON", str(env_runtime))
    registry = build_worker_runtime_registry(
        {
            "work_root_path": tmp_path,
            "jobs": {"runtimes": {"transcription": "workers/python.exe"}},
        }
    )

    assert config_runtime.is_file()
    assert registry.select("transcribe").executable == env_runtime


@pytest.mark.parametrize(
    "runtimes",
    ["not-an-object", {"transcription": 123}, {"unknown": "python"}],
)
def test_config_builder_rejects_invalid_contract(
    tmp_path: Path,
    runtimes: object,
) -> None:
    with pytest.raises(ValueError):
        build_worker_runtime_registry(
            {"work_root_path": tmp_path, "jobs": {"runtimes": runtimes}}
        )


def test_runner_uses_configured_transcription_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    meeting_dir = _meeting(tmp_path)
    executable = _python_stub(tmp_path / "asr" / "python.exe")
    calls: list[tuple[str, ...]] = []

    async def fake_subprocess(*args: str, stdout: int, stderr: int) -> _ImmediateProcess:
        calls.append(args)
        return _ImmediateProcess()

    monkeypatch.setattr("meeting_agent.jobs.runner._create_subprocess", fake_subprocess)
    runner = JobRunner(
        worker_runtimes=WorkerRuntimeRegistry({"transcription": executable})
    )

    async def scenario() -> None:
        await runner.submit(
            meeting_id=MEETING_ID,
            stage="transcribe",
            meeting_dir=meeting_dir,
        )
        await asyncio.sleep(0)

    asyncio.run(scenario())

    assert len(calls) == 2
    assert all(call[0] == str(executable) for call in calls)
    assert "--dry-run" in calls[0]
    assert "--dry-run" not in calls[1]


def test_diarization_dependency_preflight_runs_in_selected_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    meeting_dir = _meeting(tmp_path)
    audio = meeting_dir / "source" / "audio_16k_mono.wav"
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b"RIFF")
    executable = _python_stub(tmp_path / "diarization" / "python.exe")
    calls: list[tuple[str, ...]] = []

    async def fake_subprocess(*args: str, stdout: int, stderr: int) -> _ImmediateProcess:
        calls.append(args)
        return _ImmediateProcess()

    monkeypatch.setattr("meeting_agent.jobs.runner._create_subprocess", fake_subprocess)
    runner = JobRunner(
        worker_runtimes=WorkerRuntimeRegistry({"diarization": executable})
    )

    async def scenario() -> None:
        await runner.submit(
            meeting_id=MEETING_ID,
            stage="diarize",
            meeting_dir=meeting_dir,
        )
        await asyncio.sleep(0)

    asyncio.run(scenario())

    assert len(calls) == 2
    assert all(call[0] == str(executable) for call in calls)
    assert "--dry-run" in calls[0]


def test_missing_runtime_blocks_before_reservation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    meeting_dir = _meeting(tmp_path)
    store = JobStore(tmp_path / "jobs.json")
    called = False

    async def fake_subprocess(*args: str, stdout: int, stderr: int) -> _ImmediateProcess:
        nonlocal called
        called = True
        return _ImmediateProcess()

    monkeypatch.setattr("meeting_agent.jobs.runner._create_subprocess", fake_subprocess)
    runner = JobRunner(
        store=store,
        worker_runtimes=WorkerRuntimeRegistry(
            {"transcription": tmp_path / "missing" / "python.exe"}
        ),
    )

    with pytest.raises(PreflightFailed, match="worker runtime"):
        asyncio.run(
            runner.submit(
                meeting_id=MEETING_ID,
                stage="transcribe",
                meeting_dir=meeting_dir,
            )
        )

    assert called is False
    assert store.load()["active_job"] is None
    assert str(tmp_path) not in runner.worker_runtime_error("transcribe")


def test_failed_dry_run_is_retained_with_bounded_redacted_diagnostics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    meeting_dir = _meeting(tmp_path)
    executable = _python_stub(tmp_path / "asr" / "python.exe")
    store = JobStore(tmp_path / "jobs.json")
    stderr_payload = f"dependency missing at {meeting_dir / 'private-model'}".encode()

    async def fake_subprocess(*args: str, stdout: int, stderr: int) -> _ImmediateProcess:
        return _ImmediateProcess(returncode=7, stderr=stderr_payload)

    monkeypatch.setattr("meeting_agent.jobs.runner._create_subprocess", fake_subprocess)
    runner = JobRunner(
        meetings_root=tmp_path,
        store=store,
        worker_runtimes=WorkerRuntimeRegistry({"transcription": executable}),
    )

    with pytest.raises(PreflightFailed):
        asyncio.run(
            runner.submit(
                meeting_id=MEETING_ID,
                stage="transcribe",
                meeting_dir=meeting_dir,
            )
        )

    assert len(runner.history) == 1
    job = runner.history[0]
    assert job.status == "failed"
    assert job.exit_code == 7
    public = job.as_dict()
    assert str(tmp_path) not in json.dumps(public)
    assert "<path>" in public["stderr_tail"][0]
    persisted = store.load()
    assert persisted["active_job"] is None
    assert persisted["history"][0]["exit_code"] == 7
    assert persisted["events"][-1]["event"] == "job_preflight_failed"
