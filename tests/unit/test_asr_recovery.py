from __future__ import annotations

import json

import pytest

from meeting_agent.jobs.progress import ProgressReporter, normalize_progress_snapshot
from meeting_agent.transcription.checkpoints import CheckpointStore, atomic_json
from meeting_agent.transcription.recovery import recovery_summary


def checkpoint(tmp_path):
    audio = tmp_path / "source.wav"
    audio.write_bytes(b"synthetic audio")
    store = CheckpointStore(tmp_path)
    header = store.begin({"source": "source.wav", "settings": {}},
                         total_frames=100, sample_rate=1, block_frames=20, resume=False)
    stat = audio.stat()
    header["source_stat"] = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
    store.commit(header, 0, [])
    return audio, store, header


def test_recovery_is_bounded_read_only_and_path_free(tmp_path):
    _, store, _ = checkpoint(tmp_path)
    original = store.current.read_bytes()
    summary = recovery_summary(tmp_path)
    assert summary["saved_percent"] == 20
    assert summary["can_resume"]
    assert "source.wav" not in json.dumps(summary)
    assert str(tmp_path) not in json.dumps(summary)
    assert store.current.read_bytes() == original


def test_recovery_rejects_changed_source_and_corrupt_block(tmp_path):
    audio, store, header = checkpoint(tmp_path)
    audio.write_bytes(b"changed")
    assert recovery_summary(tmp_path)["state"] == "source_changed"
    store.block_path(header, 0).write_text("{")
    assert recovery_summary(tmp_path)["state"] == "unavailable"


@pytest.mark.parametrize("count", [-1, True, 6, "3"])
def test_bad_frontier_not_reported_as_saved(tmp_path, count):
    _, store, header = checkpoint(tmp_path)
    header["saved_blocks"] = count
    atomic_json(store.current, header)
    assert not recovery_summary(tmp_path)["can_resume"]


def test_eta_uses_new_attempt_speed_instead_of_previous_progress(tmp_path, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("meeting_agent.jobs.progress.time.monotonic", lambda: clock[0])
    reporter = ProgressReporter(tmp_path / "progress.json", phase="transcribe:faster-whisper", unit="seconds")
    reporter.checkpoint(80, 100, True)
    clock[0] = 160.0
    snapshot = reporter.emit(85, 100, force=True)
    assert snapshot["percent"] == 85
    assert snapshot["saved_percent"] == 80
    assert snapshot["elapsed_seconds"] == 60
    assert snapshot["eta_seconds"] == 180


def test_saved_progress_does_not_exceed_processed_progress():
    snapshot = normalize_progress_snapshot(dict(phase="asr", unit="seconds", current=30, total=100, saved_seconds=90))
    assert snapshot["saved_percent"] == 30
