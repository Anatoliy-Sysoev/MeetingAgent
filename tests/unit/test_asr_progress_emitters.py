from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
import sys

from meeting_agent.jobs.progress import read_progress_snapshot
from meeting_agent.transcription.faster_whisper_backend import (
    FasterWhisperConfig,
    transcribe_faster_whisper,
)
from scripts.gigaam_transcribe_chunks import transcribe_chunks


@dataclass
class _Segment:
    start: float
    end: float
    text: str
    avg_logprob: float = -0.1
    no_speech_prob: float = 0.01


@dataclass
class _Info:
    duration: float = 120.0
    language: str = "ru"
    language_probability: float = 0.99
    duration_after_vad: float = 110.0


class _Model:
    def transcribe(self, _path: str, **_kwargs):
        return iter(
            [
                _Segment(0.0, 12.0, "Первая реплика"),
                _Segment(25.0, 40.0, "Вторая реплика"),
            ]
        ), _Info()


def test_faster_whisper_reports_media_timestamp_progress(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "meeting_agent.transcription.faster_whisper_backend.load_model",
        lambda _config: _Model(),
    )
    events: list[tuple[float, float | None]] = []

    result = transcribe_faster_whisper(
        tmp_path / "audio.wav",
        FasterWhisperConfig(),
        progress_callback=lambda current, total: events.append((current, total)),
    )

    assert len(result.segments) == 2
    assert events == [(0.0, 120.0), (12.0, 120.0), (40.0, 120.0), (120.0, 120.0)]


def test_gigaam_worker_reports_completed_chunks(monkeypatch, tmp_path: Path) -> None:
    class _GigaModel:
        def transcribe(self, path: str) -> str:
            return Path(path).stem

    monkeypatch.setitem(
        sys.modules,
        "gigaam",
        SimpleNamespace(load_model=lambda *_args, **_kwargs: _GigaModel()),
    )
    meeting_dir = tmp_path / "meeting"
    chunks_dir = meeting_dir / "transcript" / "_gigaam" / "chunks_24s"
    chunks_dir.mkdir(parents=True)
    for index in range(3):
        (chunks_dir / f"chunk_{index:04d}.wav").write_bytes(b"RIFF")
    progress_path = meeting_dir / "runtime" / "progress" / "job.json"
    args = SimpleNamespace(
        chunks_dir=chunks_dir,
        output_dir=meeting_dir / "transcript" / "_gigaam",
        source_file=meeting_dir / "source" / "video.mp4",
        gigaam_root=tmp_path / "GigaAM",
        cache_root=tmp_path / "cache",
        model="v3_e2e_rnnt",
        chunk_seconds=24.0,
        progress_path=progress_path,
    )

    result = transcribe_chunks(args)

    progress = read_progress_snapshot(progress_path)
    assert result["chunks"] == 3
    assert progress is not None
    assert progress["current"] == 3
    assert progress["total"] == 3
    assert progress["percent"] == 100.0
