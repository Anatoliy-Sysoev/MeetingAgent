from __future__ import annotations

import json
from pathlib import Path

import pytest

from meeting_agent.speakers.overrides import SpeakerOverrideError, SpeakerOverrideStore


def test_store_persists_audited_events_and_reset(tmp_path: Path) -> None:
    path = tmp_path / "speaker_overrides.json"
    store = SpeakerOverrideStore(path, "2026-01-01__demo")
    automatic = {"utt-1": "SPEAKER_01", "utt-2": "SPEAKER_02"}

    result = store.set(["utt-1", "utt-2"], "SPEAKER_02", automatic, "user-1")
    assert result["events_count"] == 1
    assert {row["segment_id"] for row in result["overrides"]} == {"utt-1", "utt-2"}
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["events"][0]["actor_id"] == "user-1"
    assert document["events"][0]["corrections"][0] == {
        "segment_id": "utt-1",
        "old_speaker_label": "SPEAKER_01",
        "new_speaker_label": "SPEAKER_02",
    }
    result = store.reset(["utt-1"], automatic, "user-1")
    assert [row["segment_id"] for row in result["overrides"]] == ["utt-2"]
    assert result["events_count"] == 2


def test_store_rejects_corrupt_or_cross_meeting_document(tmp_path: Path) -> None:
    path = tmp_path / "speaker_overrides.json"
    path.write_text(
        json.dumps({"schema_version": 1, "meeting_id": "other", "events": []}),
        encoding="utf-8",
    )
    store = SpeakerOverrideStore(path, "2026-01-01__demo")

    with pytest.raises(SpeakerOverrideError, match="meeting identity"):
        store.snapshot()


def test_store_rejects_unknown_segment_and_invalid_actor(tmp_path: Path) -> None:
    store = SpeakerOverrideStore(tmp_path / "speaker_overrides.json", "2026-01-01__demo")
    with pytest.raises(SpeakerOverrideError, match="does not exist"):
        store.set(["missing"], "SPEAKER_01", {"utt-1": "SPEAKER_01"}, "user-1")
    with pytest.raises(SpeakerOverrideError, match="actor"):
        store.set(["utt-1"], "SPEAKER_01", {"utt-1": "SPEAKER_01"}, "bad actor")
