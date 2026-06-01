from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from meeting_agent.transcription import (
    TranscriptDocument,
    build_markdown_transcript,
    build_plain_text_transcript,
    build_srt_transcript,
    build_transcription_report,
    build_vtt_transcript,
    normalize_segments,
    write_transcript_exports,
)


def test_normalize_segments_sorts_filters_and_generates_ids() -> None:
    result = normalize_segments(
        [
            {"start": 10, "end": 12, "text": " Второй   сегмент ", "avg_logprob": "-0.2"},
            {"start": 0, "end": 1, "text": ""},
            {"start": 2, "end": 2, "text": "битый"},
            {"start": 1.2, "end": 3.4567, "text": "Первый сегмент", "source": "SYS"},
        ],
        engine="faster-whisper",
        language="ru",
    )

    assert result.empty_dropped == 1
    assert result.invalid_dropped == 1
    assert len(result.segments) == 2
    assert [segment.segment_id for segment in result.segments] == ["seg-000001", "seg-000002"]
    assert [segment.segment_index for segment in result.segments] == [1, 2]
    assert result.segments[0].text == "Первый сегмент"
    assert result.segments[0].source == "SYS"
    assert result.segments[1].text == "Второй сегмент"
    assert result.segments[1].avg_logprob == -0.2
    assert any("end must be greater than start" in warning for warning in result.warnings)


def test_exporters_generate_txt_md_srt_vtt_and_json(tmp_path) -> None:
    normalization = normalize_segments(
        [
            {"start": 0.0, "end": 1.234, "text": "Первая фраза."},
            {"start": 65.5, "end": 67.0, "text": "Вторая фраза."},
        ],
        engine="gigaam",
        language="ru",
    )
    document = TranscriptDocument(
        meeting_id="2026-05-26__support-scheme",
        title="Схема уровня поддержки",
        engine="gigaam",
        model="gigaam/v3_e2e_rnnt",
        language="ru",
        segments=normalization.segments,
    )

    assert build_plain_text_transcript(document.segments) == "Первая фраза.\nВторая фраза.\n"
    assert "[00:01:05] Вторая фраза." in build_markdown_transcript(document)
    assert "00:00:00,000 --> 00:00:01,234" in build_srt_transcript(document.segments)
    assert build_vtt_transcript(document.segments).startswith("WEBVTT\n\n")

    written = write_transcript_exports(tmp_path, document)

    assert set(written) == {
        "segments",
        "transcript_json",
        "transcript_txt",
        "transcript_md",
        "transcript_srt",
        "transcript_vtt",
    }
    assert (tmp_path / "segments.jsonl").exists()
    rows = [json.loads(line) for line in (tmp_path / "segments.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows[0]["segment_id"] == "seg-000001"
    transcript_json = json.loads((tmp_path / "transcript.json").read_text(encoding="utf-8"))
    assert transcript_json["segments_count"] == 2


def test_transcription_report_counts_duration_chars_and_warnings() -> None:
    normalization = normalize_segments(
        [
            {"start": 2, "end": 5, "text": "abc"},
            {"start": 7, "end": 8, "text": "абвг"},
            {"start": 1, "end": 0, "text": "bad"},
            {"start": 9, "end": 10, "text": ""},
        ],
        engine="from-segments",
        language="ru",
    )

    report = build_transcription_report(
        normalization,
        engine="from-segments",
        model=None,
        language="ru",
        started_at="2026-06-01T10:00:00+03:00",
        finished_at="2026-06-01T10:00:03+03:00",
        elapsed_seconds=3.2,
    )

    data = report.to_dict()
    assert data["duration_seconds"] == 6.0
    assert data["segments_count"] == 2
    assert data["chars_count"] == 7
    assert data["empty_segments_dropped"] == 1
    assert "invalid_segments_dropped=1" in data["warnings"]
