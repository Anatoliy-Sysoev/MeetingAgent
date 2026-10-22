from __future__ import annotations

import json
from pathlib import Path

import pytest

from meeting_agent.transcription.checkpoints import CheckpointError, CheckpointStore


def begin(store, resume=False, **changes):
    options = dict(identity={"audio_sha256": "a" * 64, "model": "turbo"},
                   total_frames=40, sample_rate=10, block_frames=20, resume=resume)
    options.update(changes)
    return store.begin(**options)


def test_prefix_survives_new_store_and_empty_blocks(tmp_path):
    store = CheckpointStore(tmp_path)
    header = begin(store)
    store.commit(header, 0, [{"start": 0, "end": 1, "text": "test"}])
    store.commit(header, 1, [])
    other = CheckpointStore(tmp_path)
    assert other.prefix(begin(other, True)) == ([{"start": 0, "end": 1, "text": "test"}], 2)


@pytest.mark.parametrize("changed", [{"identity": {"audio_sha256": "b"}},
                                      {"block_frames": 10}, {"total_frames": 41}])
def test_identity_mismatch_is_read_only(tmp_path, changed):
    store = CheckpointStore(tmp_path)
    begin(store)
    original = store.current.read_bytes()
    with pytest.raises(CheckpointError, match="changed"):
        begin(store, True, **changed)
    assert store.current.read_bytes() == original


def test_corruption_or_gap_stops_at_last_safe_block(tmp_path):
    store = CheckpointStore(tmp_path)
    header = begin(store)
    store.commit(header, 1, [])
    assert store.prefix(header) == ([], 0)
    store.commit(header, 0, [])
    envelope = json.loads(store.block_path(header, 1).read_text())
    envelope["payload"]["end_frame"] = 45
    store.block_path(header, 1).write_text(json.dumps(envelope))
    assert store.prefix(header) == ([], 1)


def test_failed_replace_keeps_previous_generation_and_cleans_temp(tmp_path, monkeypatch):
    store = CheckpointStore(tmp_path)
    first = begin(store)
    def fail(*args):
        raise OSError("disk failure")
    monkeypatch.setattr("meeting_agent.transcription.checkpoints.os.replace", fail)
    with pytest.raises(OSError):
        begin(store)
    assert store.header() == first
    assert not list(tmp_path.rglob("*.tmp"))


def test_force_preserves_old_generation(tmp_path):
    store = CheckpointStore(tmp_path)
    first = begin(store)
    store.commit(first, 0, [])
    second = begin(store)
    assert first["generation"] != second["generation"]
    assert store.block_path(first, 0).is_file()
    assert store.prefix(second) == ([], 0)


def test_corrupt_header_requires_explicit_new_run(tmp_path):
    store = CheckpointStore(tmp_path)
    begin(store)
    store.current.write_text("{")
    with pytest.raises(CheckpointError):
        begin(store, True)
    assert begin(store)["version"] == 1


def test_read_missing_does_not_create_directories(tmp_path):
    store = CheckpointStore(tmp_path)
    assert store.header() is None
    assert list(tmp_path.iterdir()) == []


def test_second_worker_cannot_lock_same_store(tmp_path):
    from meeting_agent.meetings.ingest_lock import IngestLockTimeoutError
    store = CheckpointStore(tmp_path)
    with store.lock():
        with pytest.raises(IngestLockTimeoutError):
            with CheckpointStore(tmp_path).lock():
                pytest.fail("second worker acquired lock")


def test_oversized_manifest_rejected(tmp_path):
    store = CheckpointStore(tmp_path)
    begin(store)
    store.current.write_bytes(b" " * (64 * 1024 + 1))
    with pytest.raises(CheckpointError):
        store.header()


@pytest.mark.parametrize("row", [{"start": -1, "end": 1, "text": "x"},
                                  {"start": 0, "end": 3, "text": "x"},
                                  {"start": 1, "end": 1, "text": "x"},
                                  {"start": 0, "end": float("nan"), "text": "x"}])
def test_bad_timestamps_rejected(tmp_path, row):
    store = CheckpointStore(tmp_path)
    with pytest.raises(CheckpointError):
        store.commit(begin(store), 0, [row])
