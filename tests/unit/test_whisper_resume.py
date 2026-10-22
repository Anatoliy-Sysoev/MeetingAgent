from __future__ import annotations

import wave
from dataclasses import replace
from types import SimpleNamespace

import pytest

from meeting_agent.transcription import faster_whisper_backend as backend
from meeting_agent.transcription.checkpoints import CheckpointError, CheckpointStore
from meeting_agent.transcription.publication import (
    begin_publication, complete_publication, transcript_is_complete,
)
from meeting_agent.jobs.readiness import _stage_done, _stage_blocked_reason
from meeting_agent.jobs.runner import stage_base_args


def audio_file(tmp_path, seconds=5):
    path = tmp_path / "audio.wav"
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\0\0" * (16000 * seconds))
    return path


def fake_segment():
    return SimpleNamespace(start=0.1, end=0.9, text="phrase", avg_logprob=-0.1, no_speech_prob=0.1)


def test_resume_skips_committed_blocks_and_loads_model_once_per_attempt(tmp_path, monkeypatch):
    audio = audio_file(tmp_path)
    config = backend.FasterWhisperConfig(block_seconds=2)
    calls = []
    loads = []
    class Model:
        def transcribe(self, samples, **kwargs):
            calls.append(len(samples))
            assert kwargs["vad_filter"] is True
            if len(calls) == 2:
                raise RuntimeError("simulated crash")
            return iter([fake_segment()]), SimpleNamespace()
    monkeypatch.setattr(backend, "load_model", lambda cfg: (loads.append(cfg), Model())[1])
    with pytest.raises(RuntimeError):
        backend.transcribe_faster_whisper(audio, config, meeting_dir=tmp_path)
    progress = []
    result = backend.transcribe_faster_whisper(
        audio, config, meeting_dir=tmp_path, resume=True,
        progress_callback=lambda current, total: progress.append((current, total)),
    )
    assert calls == [32000, 32000, 32000, 16000]
    assert len(loads) == 2
    assert [s["start"] for s in result.segments] == [0.1, 2.1, 4.1]
    assert progress[0] == (2, 5)
    assert result.metrics["blocks_reused"] == 1
    # All blocks exist: a publication retry must not even load the ASR model.
    backend.transcribe_faster_whisper(audio, config, meeting_dir=tmp_path, resume=True)
    assert len(loads) == 2


def test_silence_is_committed_and_mismatch_does_not_overwrite(tmp_path, monkeypatch):
    audio = audio_file(tmp_path)
    config = backend.FasterWhisperConfig(block_seconds=2)
    monkeypatch.setattr(backend, "load_model", lambda cfg: SimpleNamespace(
        transcribe=lambda *a, **k: (iter([]), SimpleNamespace())))
    result = backend.transcribe_faster_whisper(audio, config, meeting_dir=tmp_path)
    assert result.segments == []
    original = CheckpointStore(tmp_path).current.read_bytes()
    with pytest.raises(CheckpointError, match="changed"):
        backend.transcribe_faster_whisper(audio, replace(config, language="en"),
                                         meeting_dir=tmp_path, resume=True)
    assert CheckpointStore(tmp_path).current.read_bytes() == original
    result = backend.transcribe_faster_whisper(audio, config, meeting_dir=tmp_path, resume=True)
    assert result.metrics["blocks_reused"] == 3


def test_changed_audio_requires_new_generation(tmp_path, monkeypatch):
    audio = audio_file(tmp_path)
    config = backend.FasterWhisperConfig()
    monkeypatch.setattr(backend, "load_model", lambda cfg: SimpleNamespace(
        transcribe=lambda *a, **k: (iter([fake_segment()]), SimpleNamespace())))
    first = backend.transcribe_faster_whisper(audio, config, meeting_dir=tmp_path)
    with audio.open("ab") as handle:
        handle.write(b"changed")
    with pytest.raises(CheckpointError):
        backend.transcribe_faster_whisper(audio, config, meeting_dir=tmp_path, resume=True)
    second = backend.transcribe_faster_whisper(audio, config, meeting_dir=tmp_path)
    assert first.metrics["checkpoint_generation"] != second.metrics["checkpoint_generation"]


def test_partial_publication_never_unblocks_downstream(tmp_path):
    (tmp_path / "meeting.json").write_text("{}")
    assert transcript_is_complete(tmp_path)  # legacy
    begin_publication(tmp_path)
    segments = tmp_path / "transcript/segments.jsonl"
    segments.write_text('{"text":"partial"}\n')
    assert not _stage_done("transcribe", tmp_path, {})
    assert "incomplete" in _stage_blocked_reason("merge", tmp_path)
    report = tmp_path / "transcript/transcription_report.json"
    report.write_text("{}")
    complete_publication(tmp_path, dict(segments=segments, report=report))
    assert _stage_done("transcribe", tmp_path, {})
    report.unlink()
    assert not transcript_is_complete(tmp_path)


@pytest.mark.parametrize("force", [False, True])
def test_retry_engine_and_command_contract(force):
    from meeting_agent.api.routes_jobs import RetryRequest, _stage_options
    options = _stage_options("transcribe", RetryRequest(force=force, asr_engine="gigaam"))
    args = stage_base_args("transcribe", options)
    assert args[args.index("--engine") + 1] == "gigaam"
    assert ("--force" in args) == force
    assert ("--resume" in args) != force


def test_default_retry_has_resume():
    from meeting_agent.api.routes_jobs import _stage_options
    assert "--resume" in stage_base_args("transcribe", _stage_options("transcribe", None))
