"""Explicit opt-in: use a private local WAV, never download models in CI."""
from __future__ import annotations

import os
import shutil
import wave
from pathlib import Path

import pytest

from meeting_agent.transcription.faster_whisper_backend import (
    FasterWhisperConfig, transcribe_faster_whisper,
)


@pytest.mark.skipif(not os.environ.get("MEETINGAGENT_ASR_SMOKE_WAV"),
                    reason="Set MEETINGAGENT_ASR_SMOKE_WAV for an explicit real ASR smoke")
def test_real_whisper_blocks_and_cached_resume(tmp_path):
    pytest.importorskip("faster_whisper")
    source = Path(os.environ["MEETINGAGENT_ASR_SMOKE_WAV"])
    with wave.open(str(source), "rb") as wav:
        assert wav.getnchannels() == 1 and wav.getsampwidth() == 2 and wav.getframerate() == 16000
        assert 60 < wav.getnframes() / 16000 <= 180, "Use a 61–180 second Russian speech sample"
    media = tmp_path / "sample.wav"
    shutil.copyfile(source, media)
    model = os.environ.get("MEETINGAGENT_ASR_SMOKE_MODEL", "large-v3-turbo")
    config = FasterWhisperConfig(model=model, block_seconds=30)
    first = transcribe_faster_whisper(media, config, meeting_dir=tmp_path)
    resumed = transcribe_faster_whisper(media, config, meeting_dir=tmp_path, resume=True)
    assert first.segments and first.segments == resumed.segments
    assert resumed.metrics["blocks_reused"] == resumed.metrics["blocks_total"]
    assert all(0 <= row["start"] < row["end"] <= first.metrics["duration"] + 0.002 for row in first.segments)
