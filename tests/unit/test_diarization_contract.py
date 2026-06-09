from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from meeting_agent.diarization import assign_speaker, normalize_intervals, overlap_seconds  # noqa: E402


def test_normalize_intervals_sorts_and_formats_speakers() -> None:
    intervals, warnings = normalize_intervals(
        [
            {"speaker": "1", "start": 10, "end": 12, "backend": "test"},
            {"speaker": "SPEAKER_0", "start": -1, "end": 1, "backend": "test"},
            {"speaker": "", "start": 20, "end": 18, "backend": "test"},
        ],
        backend="test",
    )

    assert [item.speaker for item in intervals] == ["SPEAKER_00", "SPEAKER_01"]
    assert intervals[0].start == 0.0
    assert any("start below zero" in item for item in warnings)
    assert any("end must be greater" in item for item in warnings)


def test_assign_speaker_uses_maximum_overlap_and_threshold() -> None:
    intervals, _ = normalize_intervals(
        [
            {"speaker": "SPEAKER_00", "start": 0, "end": 4, "backend": "test"},
            {"speaker": "SPEAKER_01", "start": 4, "end": 10, "backend": "test"},
        ],
        backend="test",
    )

    speaker, overlap, ratio = assign_speaker(
        {"start": 2, "end": 8},
        intervals,
        min_overlap_ratio=0.3,
    )

    assert speaker == "SPEAKER_01"
    assert overlap == 4.0
    assert ratio == 0.667


def test_assign_speaker_returns_unknown_when_overlap_is_too_small() -> None:
    intervals, _ = normalize_intervals(
        [{"speaker": "SPEAKER_00", "start": 0, "end": 1, "backend": "test"}],
        backend="test",
    )

    speaker, overlap, ratio = assign_speaker(
        {"start": 0, "end": 10},
        intervals,
        min_overlap_ratio=0.3,
    )

    assert speaker == "SPEAKER_UNKNOWN"
    assert overlap == 1.0
    assert ratio == 0.1


def test_overlap_seconds() -> None:
    assert overlap_seconds(0, 10, 5, 12) == 5
    assert overlap_seconds(0, 3, 3, 5) == 0
