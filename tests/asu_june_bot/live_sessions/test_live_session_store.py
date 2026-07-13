from __future__ import annotations

import json
from pathlib import Path

import pytest

from asu_june_bot.live_sessions.store import (
    LiveSessionStore,
    LiveSessionStoreConflict,
    LiveSessionStoreError,
)


def _record(
    session_id: str,
    *,
    meeting_id: str = "2026-07-13__live-test",
    source: str = "MIC",
    status: str = "starting",
    event_count: int = 1,
) -> dict:
    return {
        "session_id": session_id,
        "meeting_id": meeting_id,
        "source": source,
        "status": status,
        "created_at": "2026-07-13T10:00:00+00:00",
        "updated_at": "2026-07-13T10:00:00+00:00",
        "finished_at": None,
        "last_event_id": event_count,
        "events": [
            {
                "event_id": index,
                "type": "status",
                "timestamp": "2026-07-13T10:00:00+00:00",
                "status": status,
            }
            for index in range(1, event_count + 1)
        ],
        "warnings": [],
        "error": None,
        "artifact_keys": [],
    }


def test_store_reserve_update_and_load_are_atomic(tmp_path: Path) -> None:
    path = tmp_path / "runtime" / "live.json"
    store = LiveSessionStore(path, events_max=10)
    record = _record("s1")

    store.reserve(record)
    record["status"] = "completed"
    record["updated_at"] = "2026-07-13T10:01:00+00:00"
    record["finished_at"] = "2026-07-13T10:01:00+00:00"
    store.update(record)

    loaded = store.load()
    assert loaded["sessions"][0]["status"] == "completed"
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == 1
    assert not list(path.parent.glob(f".{path.name}.*.tmp"))


def test_store_rejects_duplicate_active_meeting_source(tmp_path: Path) -> None:
    store = LiveSessionStore(tmp_path / "live.json", active_sessions_max=2)
    store.reserve(_record("s1"))

    with pytest.raises(LiveSessionStoreConflict, match="already active"):
        store.reserve(_record("s2"))

    store.reserve(_record("s3", source="SYS"))
    assert {row["source"] for row in store.load()["sessions"]} == {"MIC", "SYS"}


def test_store_enforces_global_active_session_capacity(tmp_path: Path) -> None:
    store = LiveSessionStore(tmp_path / "live.json", active_sessions_max=2)
    store.reserve(_record("s1", meeting_id="meeting-one", source="MIC"))
    store.reserve(_record("s2", meeting_id="meeting-two", source="MIC"))

    with pytest.raises(LiveSessionStoreConflict, match="capacity"):
        store.reserve(_record("s3", meeting_id="meeting-three", source="MIC"))


def test_store_bounds_terminal_history_and_events(tmp_path: Path) -> None:
    store = LiveSessionStore(
        tmp_path / "live.json",
        sessions_max=2,
        events_max=3,
    )
    for index in range(3):
        store.reserve(
            _record(
                f"s{index}",
                meeting_id=f"2026-07-1{index}__live-test",
                status="completed",
                event_count=3,
            )
        )

    loaded = store.load()
    assert [row["session_id"] for row in loaded["sessions"]] == ["s1", "s2"]
    assert all(len(row["events"]) == 3 for row in loaded["sessions"])


def test_store_recovers_active_sessions_as_stale(tmp_path: Path) -> None:
    store = LiveSessionStore(tmp_path / "live.json", events_max=10)
    store.reserve(_record("s1", status="running"))

    recovered = store.recover_active()

    assert recovered[0]["status"] == "stale"
    assert recovered[0]["error"] == {
        "code": "api_restart",
        "message": "Live session stopped after API restart",
    }
    assert recovered[0]["events"][-1]["reason"] == "api_restart"
    assert store.load()["sessions"][0]["status"] == "stale"


@pytest.mark.parametrize(
    "payload",
    [
        b"not-json",
        b'{"schema_version": 99, "sessions": []}',
        b'{"schema_version": 1, "sessions": "bad"}',
    ],
)
def test_store_fails_closed_on_malformed_state(tmp_path: Path, payload: bytes) -> None:
    path = tmp_path / "live.json"
    path.write_bytes(payload)

    with pytest.raises(LiveSessionStoreError):
        LiveSessionStore(path).load()


def test_store_rejects_unknown_or_diagnostic_event_fields(tmp_path: Path) -> None:
    path = tmp_path / "live.json"
    record = _record("s1")
    record["events"][0]["device_path"] = r"C:\private\device"
    path.write_text(
        json.dumps({"schema_version": 1, "sessions": [record]}),
        encoding="utf-8",
    )

    with pytest.raises(LiveSessionStoreError, match="invalid events"):
        LiveSessionStore(path).load()


def test_store_rejects_oversized_state_before_json_decode(tmp_path: Path) -> None:
    path = tmp_path / "live.json"
    path.write_bytes(b"x" * (64 * 1024 + 1))

    with pytest.raises(LiveSessionStoreError, match="size limit"):
        LiveSessionStore(path, max_state_bytes=64 * 1024).load()


def test_store_compacts_old_events_to_fit_byte_budget(tmp_path: Path) -> None:
    path = tmp_path / "live.json"
    store = LiveSessionStore(path, events_max=100, max_state_bytes=64 * 1024)
    record = _record("s1", status="completed", event_count=30)
    record["events"] = [
        {
            "event_id": index,
            "type": "final",
            "timestamp": "2026-07-13T10:00:00+00:00",
            "source": "MIC",
            "segment_id": f"segment-{index}",
            "text": "x" * 4_000,
            "start": float(index),
            "end": float(index + 1),
            "is_final": True,
        }
        for index in range(1, 31)
    ]

    store.reserve(record)

    loaded = store.load()
    assert path.stat().st_size <= 64 * 1024
    assert 1 <= len(loaded["sessions"][0]["events"]) < 30
    assert loaded["sessions"][0]["events"][-1]["event_id"] == 30


def test_store_normalizes_existing_state_after_limits_are_lowered(tmp_path: Path) -> None:
    path = tmp_path / "live.json"
    original = LiveSessionStore(path, sessions_max=3, events_max=5)
    for index in range(3):
        original.reserve(
            _record(
                f"s{index}",
                meeting_id=f"meeting-{index}",
                status="completed",
                event_count=5,
            )
        )

    lowered = LiveSessionStore(
        path,
        sessions_max=1,
        active_sessions_max=1,
        events_max=2,
    )
    lowered.recover_active()
    loaded = lowered.load()

    assert [record["session_id"] for record in loaded["sessions"]] == ["s2"]
    assert [event["event_id"] for event in loaded["sessions"][0]["events"]] == [4, 5]
