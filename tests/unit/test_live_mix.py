from __future__ import annotations

import json
from pathlib import Path

import pytest

from meeting_agent.live_transcription.mix import (
    LiveMixError,
    build_derived_mix_artifacts,
    merge_live_source_segments,
    read_derived_mix_timeline,
)


def _segment(source: str, segment_id: str, start: float, end: float, text: str) -> dict:
    return {
        "segment_id": segment_id,
        "segment_index": 0,
        "start": start,
        "end": end,
        "text": text,
        "source": source,
        "engine": "vosk",
        "confidence": 0.9,
        "is_final": True,
    }


def _write_source(
    root: Path,
    source: str,
    rows: list[dict],
    *,
    started_at: str,
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / f"live_segments.{source}.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    (root / f"live_report.{source}.json").write_text(
        json.dumps(
            {
                "source": source,
                "started_at": started_at,
            }
        ),
        encoding="utf-8",
    )


def test_mix_aligns_independent_source_clocks_and_preserves_origin(tmp_path: Path) -> None:
    output = tmp_path / "live"
    _write_source(
        output,
        "MIC",
        [_segment("MIC", "mic-1", 10.0, 11.0, "Микрофон")],
        started_at="2026-07-13T10:00:00+00:00",
    )
    _write_source(
        output,
        "SYS",
        [_segment("SYS", "sys-1", 2.0, 3.0, "Система")],
        started_at="2026-07-13T10:00:05+00:00",
    )

    result = build_derived_mix_artifacts(
        output,
        generated_at="2026-07-13T10:01:00+00:00",
    )

    assert result is not None
    assert [segment.source for segment in result.segments] == ["SYS", "MIC"]
    assert [segment.start for segment in result.segments] == [7.0, 10.0]
    assert result.segments[0].metadata == {
        "derived_track": "MIX",
        "origin_source": "SYS",
        "origin_segment_id": "sys-1",
        "origin_start": 2.0,
        "origin_end": 3.0,
        "source_offset_seconds": 5.0,
        "source_started_at": "2026-07-13T10:00:05+00:00",
    }
    timeline = read_derived_mix_timeline(output)
    assert timeline["timeline_started_at"] == "2026-07-13T10:00:00+00:00"
    assert timeline["segments"][0]["origin_start"] == 2.0
    assert "path" not in json.dumps(timeline)


def test_mix_tie_breaks_by_source_then_stable_origin_id() -> None:
    mic = [
        _segment("MIC", "mic-b", 1.0, 3.0, "B"),
        _segment("MIC", "mic-a", 1.0, 2.0, "A"),
    ]
    sys = [_segment("SYS", "sys-a", 1.0, 1.5, "S")]

    merged, invalid = merge_live_source_segments(mic, sys)

    assert invalid == 0
    assert [row.metadata["origin_segment_id"] for row in merged] == [
        "mic-a",
        "mic-b",
        "sys-a",
    ]
    assert [row.segment_index for row in merged] == [0, 1, 2]


def test_mix_rebuild_is_idempotent_and_does_not_rewrite_sources(tmp_path: Path) -> None:
    output = tmp_path / "live"
    _write_source(
        output,
        "MIC",
        [_segment("MIC", "same", 0.0, 1.0, "Один")],
        started_at="2026-07-13T10:00:00Z",
    )
    source_before = (output / "live_segments.MIC.jsonl").read_bytes()

    first = build_derived_mix_artifacts(
        output,
        generated_at="2026-07-13T10:01:00Z",
    )
    second = build_derived_mix_artifacts(
        output,
        generated_at="2026-07-13T10:02:00Z",
    )

    assert first is not None and second is not None
    assert [row.segment_id for row in first.segments] == [
        row.segment_id for row in second.segments
    ]
    assert len(second.segments) == 1
    assert (output / "live_segments.MIC.jsonl").read_bytes() == source_before
    assert "sys_segments_missing" in second.warnings


def test_mix_tolerates_invalid_rows_and_one_empty_source(tmp_path: Path) -> None:
    output = tmp_path / "live"
    _write_source(
        output,
        "MIC",
        [_segment("MIC", "valid", 0.0, 1.0, "Валидная строка")],
        started_at="2026-07-13T10:00:00Z",
    )
    with (output / "live_segments.MIC.jsonl").open("a", encoding="utf-8") as handle:
        handle.write("not-json\n")
        handle.write(json.dumps({"source": "MIC", "segment_id": "bad"}) + "\n")
    _write_source(
        output,
        "SYS",
        [],
        started_at="2026-07-13T10:00:01Z",
    )

    result = build_derived_mix_artifacts(
        output,
        generated_at="2026-07-13T10:02:00Z",
    )

    assert result is not None
    assert len(result.segments) == 1
    assert "sys_segments_empty" in result.warnings
    assert "source_segments_invalid" in result.warnings


def test_mix_returns_none_without_source_artifacts(tmp_path: Path) -> None:
    assert build_derived_mix_artifacts(
        tmp_path / "live",
        generated_at="2026-07-13T10:00:00Z",
    ) is None
    assert read_derived_mix_timeline(tmp_path / "live")["segments"] == []


def test_mix_read_is_bounded_and_validates_pagination(tmp_path: Path, monkeypatch) -> None:
    output = tmp_path / "live"
    output.mkdir()
    (output / "live_segments.MIX.jsonl").write_bytes(b"{}" * 20)
    monkeypatch.setattr(
        "meeting_agent.live_transcription.mix.LIVE_MIX_DERIVED_MAX_BYTES",
        10,
    )

    with pytest.raises(LiveMixError, match="exceeds"):
        read_derived_mix_timeline(output)
    with pytest.raises(ValueError, match="pagination"):
        read_derived_mix_timeline(output, after=-1)


def test_mix_reports_clock_offsets_outside_product_bound(tmp_path: Path) -> None:
    output = tmp_path / "live"
    _write_source(
        output,
        "MIC",
        [_segment("MIC", "mic", 0, 1, "Микрофон")],
        started_at="2026-07-01T10:00:00Z",
    )
    _write_source(
        output,
        "SYS",
        [_segment("SYS", "sys", 0, 1, "Система")],
        started_at="2026-07-13T10:00:00Z",
    )

    result = build_derived_mix_artifacts(
        output,
        generated_at="2026-07-13T10:01:00Z",
    )

    assert result is not None
    assert "source_clock_out_of_range" in result.warnings
    assert [segment.start for segment in result.segments] == [0.0, 0.0]
    assert "source_clock_out_of_range" in read_derived_mix_timeline(output)["warnings"]


def test_mix_reader_accepts_combined_count_above_one_source_limit(tmp_path: Path) -> None:
    output = tmp_path / "live"
    output.mkdir()
    rows = []
    for index in range(10_001):
        source = "MIC" if index % 2 == 0 else "SYS"
        rows.append(
            {
                "segment_id": f"mix-{index}",
                "segment_index": index,
                "start": float(index),
                "end": float(index) + 0.5,
                "text": "x",
                "source": source,
                "engine": "derived-live-timeline",
                "is_final": True,
                "metadata": {
                    "origin_segment_id": f"origin-{index}",
                    "origin_start": float(index),
                    "origin_end": float(index) + 0.5,
                },
            }
        )
    (output / "live_segments.MIX.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )

    timeline = read_derived_mix_timeline(output, after=10_000, limit=1)

    assert timeline["total"] == 10_001
    assert timeline["segments"][0]["segment_id"] == "mix-10000"


def test_mix_rejects_symlinked_timeline_source(tmp_path: Path) -> None:
    output = tmp_path / "live"
    output.mkdir()
    private = tmp_path / "private.jsonl"
    private.write_text(json.dumps(_segment("MIC", "private", 0, 1, "secret")), encoding="utf-8")
    link = output / "live_segments.MIX.jsonl"
    try:
        link.symlink_to(private)
    except OSError:
        pytest.skip("symbolic links are unavailable in this Windows environment")

    with pytest.raises(LiveMixError, match="symbolic link"):
        read_derived_mix_timeline(output)
