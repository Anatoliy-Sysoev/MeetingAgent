"""Tests for SRT/VTT subtitle cue end timestamp clamping (#89)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from meeting_agent.transcription.exporters import (  # noqa: E402
    build_srt_transcript,
    build_vtt_transcript,
)
from meeting_agent.transcription.schema import CanonicalSegment  # noqa: E402


def _seg(start: float, end: float, text: str = "hello") -> CanonicalSegment:
    return CanonicalSegment(segment_id="s0", segment_index=0, start=start, end=end, text=text)


def _srt_timestamps(srt: str) -> list[tuple[str, str]]:
    """Return list of (start, end) timestamp strings from SRT blocks."""
    result = []
    for line in srt.splitlines():
        if " --> " in line:
            left, right = line.split(" --> ", 1)
            result.append((left.strip(), right.strip()))
    return result


def _vtt_timestamps(vtt: str) -> list[tuple[str, str]]:
    return _srt_timestamps(vtt)


# ---------------------------------------------------------------------------
# Equal start == end: must get +1 ms cue
# ---------------------------------------------------------------------------

def test_srt_equal_start_end_gets_positive_duration() -> None:
    srt = build_srt_transcript([_seg(1.0, 1.0)])
    pairs = _srt_timestamps(srt)
    assert len(pairs) == 1
    start, end = pairs[0]
    assert start != end, f"start and end must differ: {start!r}"


def test_vtt_equal_start_end_gets_positive_duration() -> None:
    vtt = build_vtt_transcript([_seg(1.0, 1.0)])
    pairs = _vtt_timestamps(vtt)
    assert len(pairs) == 1
    start, end = pairs[0]
    assert start != end, f"start and end must differ: {start!r}"


# ---------------------------------------------------------------------------
# Tiny sub-millisecond duration: rounds to same ms, must still differ
# ---------------------------------------------------------------------------

def test_srt_tiny_duration_rounding_gets_positive_duration() -> None:
    # 0.0001 s = 0.1 ms → both round to 0 ms; end must be clamped to 1 ms
    srt = build_srt_transcript([_seg(0.0, 0.0001)])
    pairs = _srt_timestamps(srt)
    start, end = pairs[0]
    assert start != end


def test_vtt_tiny_duration_rounding_gets_positive_duration() -> None:
    vtt = build_vtt_transcript([_seg(0.0, 0.0001)])
    pairs = _vtt_timestamps(vtt)
    start, end = pairs[0]
    assert start != end


# ---------------------------------------------------------------------------
# Normal positive duration: preserved unchanged
# ---------------------------------------------------------------------------

def test_srt_existing_positive_duration_preserved() -> None:
    srt = build_srt_transcript([_seg(1.0, 3.5)])
    pairs = _srt_timestamps(srt)
    start, end = pairs[0]
    assert start == "00:00:01,000"
    assert end == "00:00:03,500"


def test_vtt_existing_positive_duration_preserved() -> None:
    vtt = build_vtt_transcript([_seg(1.0, 3.5)])
    pairs = _vtt_timestamps(vtt)
    start, end = pairs[0]
    assert start == "00:00:01.000"
    assert end == "00:00:03.500"
