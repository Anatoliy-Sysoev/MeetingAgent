from __future__ import annotations

import pytest

from meeting_agent.speakers.turns import merge_resolved_turns, render_resolved_turns_text


def row(
    segment_id: str,
    speaker: str,
    start: float,
    end: float,
    *,
    source: str = "MIX",
    text: str = "text",
    overridden: bool = False,
) -> dict:
    return {
        "segment_id": segment_id,
        "speaker": speaker,
        "speaker_label": speaker,
        "speaker_role": None,
        "start_sec": start,
        "end_sec": end,
        "source": source,
        "text": text,
        "automatic_speaker_label": speaker,
        "speaker_overridden": overridden,
    }


def test_adjacent_same_resolved_speaker_merges_with_provenance() -> None:
    turns = merge_resolved_turns([
        row("utt-1", "SPEAKER_01", 0, 1, text="Один"),
        row("utt-2", "SPEAKER_01", 1.4, 2, text="Два", overridden=True),
    ])

    assert len(turns) == 1
    assert turns[0]["segment_ids"] == ["utt-1", "utt-2"]
    assert turns[0]["utterance_ids"] == ["utt-1", "utt-2"]
    assert turns[0]["start_sec"] == 0
    assert turns[0]["end_sec"] == 2
    assert turns[0]["text"] == "Один Два"
    assert turns[0]["speaker_overridden"] is True


@pytest.mark.parametrize(
    "second",
    [
        row("utt-2", "SPEAKER_02", 1.1, 2),
        row("utt-2", "SPEAKER_01", 3, 4),
        row("utt-2", "SPEAKER_01", 0.5, 2),
        row("utt-2", "SPEAKER_01", 1.1, 2, source="SYS"),
    ],
)
def test_merge_stops_on_speaker_pause_overlap_or_track(second: dict) -> None:
    assert len(merge_resolved_turns([row("utt-1", "SPEAKER_01", 0, 1), second])) == 2


def test_unknown_speakers_never_merge() -> None:
    rows = [
        row("utt-1", "SPEAKER_UNKNOWN", 0, 1),
        row("utt-2", "SPEAKER_UNKNOWN", 1.1, 2),
    ]
    assert len(merge_resolved_turns(rows)) == 2


def test_text_and_markdown_exports_use_resolved_turns() -> None:
    turns = merge_resolved_turns([row("utt-1", "SPEAKER_01", 65, 66, text="Решение")])
    assert "[00:01:05] SPEAKER_01: Решение" in render_resolved_turns_text(turns)
    assert "**[00:01:05] SPEAKER_01:** Решение" in render_resolved_turns_text(
        turns, markdown=True
    )


def test_invalid_gap_rejected() -> None:
    with pytest.raises(ValueError):
        merge_resolved_turns([], max_gap_sec=31)
