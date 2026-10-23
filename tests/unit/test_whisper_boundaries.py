from __future__ import annotations

import struct
import wave
from types import SimpleNamespace

import pytest

from meeting_agent.transcription import faster_whisper_backend as backend
from meeting_agent.transcription import resumable
from meeting_agent.transcription.checkpoints import CheckpointError, CheckpointStore, atomic_json, digest
from meeting_agent.transcription.normalize import normalize_segments


def ramp_audio(root):
    path = root / "sample.wav"
    with wave.open(str(path), "wb") as handle:
        handle.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        for tenth in range(50):
            handle.writeframes(struct.pack("<h", 100 + tenth) * 1600)
    return path


WORDS = [("Before", 1.4, 1.8), (" seam", 1.85, 2.15),
         (" yes", 2.4, 2.6), (" yes", 2.7, 2.9), (" tail", 4.5, 4.8)]


class WindowModel:
    def __init__(self, fail=False):
        self.windows = []
        self.fail = fail

    def transcribe(self, samples, **kwargs):
        left = (round(float(samples[0]) * 32768) - 100) / 10
        right = left + len(samples) / 16000
        self.windows.append((left, right))
        assert kwargs["word_timestamps"] is True
        if self.fail and left == 1:
            raise RuntimeError("interrupted before commit")
        # A boundary-cut word is intentionally absent, just like the original bug.
        words = [SimpleNamespace(word=text, start=a-left, end=b-left, probability=0.9)
                 for text, a, b in WORDS if left <= a and b <= right]
        segments = [SimpleNamespace(text="".join(w.word for w in words), words=words)] if words else []
        return iter(segments), SimpleNamespace()


def test_context_keeps_cross_boundary_word_and_intentional_repetition(tmp_path, monkeypatch):
    audio = ramp_audio(tmp_path)
    model = WindowModel()
    monkeypatch.setattr(backend, "load_model", lambda config: model)
    result = backend.transcribe_faster_whisper(
        audio, backend.FasterWhisperConfig(block_seconds=2), meeting_dir=tmp_path)
    assert model.windows == [(0, 3), (1, 5), (3, 5)]
    assert " ".join(row["text"] for row in result.segments) == "Before seam yes yes tail"
    assert len(result.segments) == 3
    assert [row["start"] for row in result.segments] == [1.4, 2.0, 4.5]
    assert [row["end"] for row in result.segments] == [1.8, 2.9, 4.8]
    assert all(row["source"] == "MIX" and row["confidence"] == pytest.approx(0.9)
               for row in result.segments)
    assert [row["metadata"]["window_id"] for row in result.segments] == [0, 1, 2]
    normalized = normalize_segments(result.segments, engine="faster-whisper")
    assert [row.segment_id for row in normalized.segments] == ["seg-000001", "seg-000002", "seg-000003"]
    assert normalized.segments[1].metadata == {"window_id": 1, "raw_segment_index": 0}


def test_boundary_resume_equals_uninterrupted_including_segment_ids(tmp_path, monkeypatch):
    failed, reference = tmp_path / "failed", tmp_path / "reference"
    failed.mkdir()
    reference.mkdir()
    audio, other = ramp_audio(failed), ramp_audio(reference)
    config = backend.FasterWhisperConfig(block_seconds=2)
    model = WindowModel(fail=True)
    monkeypatch.setattr(backend, "load_model", lambda config: model)
    with pytest.raises(RuntimeError, match="interrupted"):
        backend.transcribe_faster_whisper(audio, config, meeting_dir=failed)
    model = WindowModel()
    resumed = backend.transcribe_faster_whisper(audio, config, meeting_dir=failed, resume=True)
    assert model.windows == [(1, 5), (3, 5)]
    assert resumed.metrics["blocks_reused"] == 1
    normal = backend.transcribe_faster_whisper(other, config, meeting_dir=reference)
    assert resumed.segments == normal.segments
    assert normalize_segments(resumed.segments, engine="faster-whisper") == normalize_segments(
        normal.segments, engine="faster-whisper")


@pytest.mark.parametrize("policy", [None, {"algorithm": "older", "context_seconds": 5.0},
                                   {**resumable.BOUNDARY_POLICY, "context_seconds": 1.0}])
def test_old_or_changed_boundary_policy_cannot_reuse_generation(tmp_path, monkeypatch, policy):
    audio = ramp_audio(tmp_path)
    config = backend.FasterWhisperConfig(block_seconds=2)
    monkeypatch.setattr(backend, "load_model", lambda config: WindowModel())
    backend.transcribe_faster_whisper(audio, config, meeting_dir=tmp_path)
    store = CheckpointStore(tmp_path)
    header = store.header()
    if policy is None:
        header["identity"].pop("boundary_policy")
    else:
        header["identity"]["boundary_policy"] = policy
    header["fingerprint"] = digest(header["identity"])
    atomic_json(store.current, header)
    before = store.current.read_bytes()
    with pytest.raises(CheckpointError, match="changed"):
        backend.transcribe_faster_whisper(audio, config, meeting_dir=tmp_path, resume=True)
    assert store.current.read_bytes() == before


def test_missing_word_alignment_fails_without_committing_lossy_fallback(tmp_path, monkeypatch):
    audio = ramp_audio(tmp_path)
    monkeypatch.setattr(backend, "load_model", lambda config: SimpleNamespace(
        transcribe=lambda *a, **k: (iter([SimpleNamespace(text="not aligned", words=None)]), None)))
    with pytest.raises(CheckpointError, match="Word timestamps are required"):
        backend.transcribe_faster_whisper(audio, backend.FasterWhisperConfig(), meeting_dir=tmp_path)
    store = CheckpointStore(tmp_path)
    assert store.prefix(store.header()) == ([], 0)


def test_zero_length_word_at_seam_has_one_owner_and_positive_span():
    segment = SimpleNamespace(text="yes", words=[SimpleNamespace(word="yes", start=2.0, end=2.0)])
    config = backend.FasterWhisperConfig()
    assert resumable._owned_segment(segment, offset=0, start=0, end=2,
        config=config, block=0, segment_index=0) is None
    row = resumable._owned_segment(segment, offset=0, start=2, end=4,
        config=config, block=1, segment_index=0)
    assert row["text"] == "yes" and row["start"] == 2 and row["end"] == 2.001


def test_unordered_word_alignment_is_rejected():
    segment = SimpleNamespace(text="out of order", words=[
        SimpleNamespace(word="later", start=2.0, end=2.5),
        SimpleNamespace(word=" earlier", start=1.0, end=1.5)])
    with pytest.raises(CheckpointError, match="Invalid word timestamps"):
        resumable._owned_segment(segment, offset=0, start=0, end=4,
            config=backend.FasterWhisperConfig(), block=0, segment_index=0)


def test_zero_length_word_at_audio_end_is_not_discarded():
    segment = SimpleNamespace(text="last.", words=[SimpleNamespace(word="last.", start=4.0, end=4.0)])
    row = resumable._owned_segment(segment, offset=0, start=2, end=4,
        config=backend.FasterWhisperConfig(), block=1, segment_index=0, final=True)
    assert row["text"] == "last." and row["start"] == 3.999 and row["end"] == 4.0
