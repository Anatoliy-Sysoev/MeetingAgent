from __future__ import annotations

import sys
import wave
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

import meeting_agent.live_transcription.vosk_backend as vosk_backend
from meeting_agent.live_transcription.vad import (
    AcceptedAudioTimeline,
    SileroVadConfig,
    SpeechWindow,
    StreamingSileroVadFilter,
    TimedAudioBlock,
    VadBackendError,
)
from meeting_agent.live_transcription.vosk_backend import VoskLiveConfig
from meeting_agent.live_transcription.wasapi_loopback import (
    LoopbackDevice,
    OpenLoopbackStream,
)


class SequenceIterator:
    def __init__(self, events: list[dict | None]) -> None:
        self.events = list(events)
        self.calls: list[tuple[object, bool]] = []
        self.reset = False

    def __call__(self, tensor, *, return_seconds: bool):
        self.calls.append((tensor, return_seconds))
        if not self.events:
            raise AssertionError("unexpected VAD window")
        return self.events.pop(0)

    def reset_states(self) -> None:
        self.reset = True


def _window(value: int) -> bytes:
    return int(value).to_bytes(2, "little", signed=True) * 512


def _filter(
    events: list[dict | None],
    *,
    min_speech_ms: int = 64,
) -> tuple[StreamingSileroVadFilter, SequenceIterator]:
    iterator = SequenceIterator(events)
    vad_filter = StreamingSileroVadFilter(
        sample_rate=16_000,
        config=SileroVadConfig(
            threshold=0.5,
            min_speech_ms=min_speech_ms,
            min_silence_ms=64,
            speech_pad_ms=32,
        ),
        iterator=iterator,
        tensor_factory=lambda pcm: pcm,
    )
    return vad_filter, iterator


def test_streaming_filter_preserves_boundary_frames_and_wall_clock() -> None:
    vad_filter, iterator = _filter(
        [None, {"start": 512}, None, None, {"end": 2048}, None]
    )

    outputs: list[TimedAudioBlock] = []
    for index in range(6):
        outputs.extend(vad_filter.process(_window(index + 1)))
    outputs.extend(vad_filter.close())

    assert [(item.start_frame, item.end_frame) for item in outputs] == [
        (512, 1024),
        (1024, 1536),
        (1536, 2048),
        (2048, 2560),
    ]
    assert b"".join(item.data for item in outputs) == b"".join(
        _window(index) for index in range(2, 6)
    )
    assert vad_filter.input_frames == 3072
    assert vad_filter.accepted_frames == 2048
    assert vad_filter.filtered_frames == 1024
    assert [item.to_dict() for item in vad_filter.speech_windows] == [
        {"start": 0.032, "end": 0.16}
    ]
    assert vad_filter.warnings == []
    assert iterator.reset is True


def test_streaming_filter_drops_short_candidate_without_losing_next_window() -> None:
    vad_filter, _iterator = _filter(
        [None, {"start": 512}, {"end": 900}, {"start": 1536}, None],
        min_speech_ms=64,
    )

    outputs: list[TimedAudioBlock] = []
    for index in range(5):
        outputs.extend(vad_filter.process(_window(index + 1)))
    outputs.extend(vad_filter.close())

    assert [(item.start_frame, item.end_frame) for item in outputs] == [
        (1536, 2048),
        (2048, 2560),
    ]
    assert vad_filter.short_speech_dropped == 1
    assert vad_filter.warnings == ["vad_short_speech_dropped"]


def test_streaming_filter_accepts_fragmented_input_and_flushes_partial_window() -> None:
    vad_filter, iterator = _filter([{"start": 0}, None])
    first = _window(1)
    second = _window(2)

    assert vad_filter.process(first[:600]) == []
    assert vad_filter.process(first[600:] + second[:200]) == []
    outputs = vad_filter.process(second[200:])
    outputs.extend(vad_filter.close())

    assert [(item.start_frame, item.end_frame) for item in outputs] == [
        (0, 512),
        (512, 1024),
    ]
    assert len(iterator.calls) == 2


def test_streaming_filter_reports_no_speech() -> None:
    vad_filter, _iterator = _filter([None])

    assert vad_filter.process(_window(0)) == []
    assert vad_filter.close() == []

    assert vad_filter.accepted_frames == 0
    assert vad_filter.filtered_frames == 512
    assert vad_filter.warnings == ["vad_no_speech_detected"]


def test_streaming_filter_rejects_incomplete_pcm_and_invalid_events() -> None:
    vad_filter, _iterator = _filter([])
    with pytest.raises(VadBackendError, match="incomplete PCM frame"):
        vad_filter.process(b"\x00")

    invalid_filter, _invalid_iterator = _filter([{"start": "bad"}])
    with pytest.raises(VadBackendError, match="invalid event"):
        invalid_filter.process(_window(0))


def test_timeline_remaps_compressed_words_across_filtered_silence() -> None:
    timeline = AcceptedAudioTimeline(16_000)
    timeline.add(TimedAudioBlock(_window(1), 0, 512))
    timeline.add(TimedAudioBlock(_window(2), 1024, 1536))

    mapped = timeline.remap_result(
        {
            "text": "два слова",
            "result": [
                {"word": "два", "start": 0.03, "end": 0.032},
                {"word": "слова", "start": 0.032, "end": 0.04},
            ],
        }
    )

    assert mapped["result"] == [
        {"word": "два", "start": 0.03, "end": 0.032},
        {"word": "слова", "start": 0.064, "end": 0.072},
    ]
    assert timeline.last_source_span == (0.064, 0.096)


def test_timeline_rejects_overlapping_source_blocks() -> None:
    timeline = AcceptedAudioTimeline(16_000)
    timeline.add(TimedAudioBlock(_window(1), 0, 512))

    with pytest.raises(VadBackendError, match="monotonic"):
        timeline.add(TimedAudioBlock(_window(2), 500, 1012))


def test_timeline_coalesces_contiguous_audio_and_keeps_gap_boundaries() -> None:
    timeline = AcceptedAudioTimeline(16_000)
    timeline.add(TimedAudioBlock(_window(1), 0, 512))
    timeline.add(TimedAudioBlock(_window(2), 512, 1024))
    timeline.add(TimedAudioBlock(_window(3), 2048, 2560))

    assert len(timeline._spans) == 2
    assert timeline.map_interval(0.0, 0.064) == (0.0, 0.064)
    assert timeline.map_interval(0.064, 0.096) == (0.128, 0.16)


@pytest.mark.parametrize(
    ("config", "message"),
    [
        (SileroVadConfig(min_speech_ms=30_001), "min_speech_ms"),
        (SileroVadConfig(min_silence_ms=10_001), "min_silence_ms"),
        (SileroVadConfig(speech_pad_ms=5_001), "speech_pad_ms"),
    ],
)
def test_streaming_filter_rejects_unbounded_buffer_configuration(
    config: SileroVadConfig,
    message: str,
) -> None:
    with pytest.raises(VadBackendError, match=message):
        StreamingSileroVadFilter(
            sample_rate=16_000,
            config=config,
            iterator=SequenceIterator([]),
            tensor_factory=lambda pcm: pcm,
        )


class _SecondBlockFilter:
    window_frames = 512

    def __init__(self) -> None:
        self.input_frames = 0
        self.accepted_frames = 0
        self.short_speech_dropped = 0
        self.speech_windows = [SpeechWindow(start=0.032, end=0.064)]
        self.warnings: list[str] = []

    @property
    def filtered_frames(self) -> int:
        return self.input_frames - self.accepted_frames

    def process(self, block: bytes) -> list[TimedAudioBlock]:
        start = self.input_frames
        frames = len(block) // 2
        self.input_frames += frames
        if start == 0:
            return []
        self.accepted_frames += frames
        return [TimedAudioBlock(block, start, self.input_frames)]

    def close(self) -> list[TimedAudioBlock]:
        return []


class _OneResultRecognizer:
    def __init__(self) -> None:
        self.blocks: list[bytes] = []

    def AcceptWaveform(self, block: bytes) -> bool:
        self.blocks.append(block)
        return True

    def Result(self) -> str:
        return (
            '{"text":"речь","result":['
            '{"word":"речь","start":0.0,"end":0.032,"conf":0.9}]}'
        )

    def PartialResult(self) -> str:
        return '{"partial":""}'


def test_microphone_and_system_streams_share_original_timeline_contract(
    tmp_path: Path,
    monkeypatch,
) -> None:
    first = _window(1)
    second = _window(2)
    filters: list[_SecondBlockFilter] = []

    def filter_factory(**_kwargs) -> _SecondBlockFilter:
        created = _SecondBlockFilter()
        filters.append(created)
        return created

    monkeypatch.setattr(
        vosk_backend,
        "create_streaming_silero_filter",
        filter_factory,
    )

    class MicStream:
        def __init__(self, callback) -> None:
            self.callback = callback

        def __enter__(self):
            self.callback(first, 512, None, None)
            self.callback(second, 512, None, None)
            return self

        def __exit__(self, *_args) -> None:
            return None

    fake_sounddevice = SimpleNamespace(
        RawInputStream=lambda **kwargs: MicStream(kwargs["callback"])
    )
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sounddevice)

    mic_segments = []
    mic_metrics: dict = {}
    mic_timeline = AcceptedAudioTimeline(16_000)
    mic_recognizer = _OneResultRecognizer()
    mic_duration = vosk_backend._transcribe_microphone(
        VoskLiveConfig(
            model_path=tmp_path,
            source="MIC",
            duration_sec=0.064,
            vad="silero",
        ),
        mic_recognizer,
        "synthetic-vosk",
        mic_segments,
        [],
        mic_metrics,
        mic_timeline,
    )

    class LoopbackStream:
        def __init__(self) -> None:
            self.blocks = [first, second]

        def read(self, _frames: int, *, exception_on_overflow: bool) -> bytes:
            assert exception_on_overflow is False
            return self.blocks.pop(0)

    @contextmanager
    def fake_open(**_kwargs):
        yield OpenLoopbackStream(
            stream=LoopbackStream(),
            device=LoopbackDevice(
                index=7,
                name="private-device-name",
                channels=1,
                sample_rate=16_000,
            ),
        )

    class IdentityConverter:
        def __init__(self, **_kwargs) -> None:
            self.input_frames = 0
            self.output_frames = 0
            self.clips = 0

        def convert(self, block: bytes) -> bytes:
            frames = len(block) // 2
            self.input_frames += frames
            self.output_frames += frames
            return block

        def flush(self) -> bytes:
            return b""

    monkeypatch.setattr(vosk_backend, "open_wasapi_loopback_stream", fake_open)
    monkeypatch.setattr(vosk_backend, "Pcm16MonoResampler", IdentityConverter)

    sys_segments = []
    sys_metrics: dict = {}
    sys_timeline = AcceptedAudioTimeline(16_000)
    sys_recognizer = _OneResultRecognizer()
    sys_duration = vosk_backend._transcribe_system_loopback(
        VoskLiveConfig(
            model_path=tmp_path,
            source="SYS",
            duration_sec=0.064,
            vad="silero",
        ),
        sys_recognizer,
        "synthetic-vosk",
        sys_segments,
        [],
        sys_metrics,
        sys_timeline,
    )

    assert mic_duration == sys_duration == pytest.approx(0.064)
    assert mic_recognizer.blocks == sys_recognizer.blocks == [second]
    assert [(item.start, item.end) for item in mic_segments] == [(0.032, 0.064)]
    assert [(item.start, item.end) for item in sys_segments] == [(0.032, 0.064)]
    for metrics in (mic_metrics, sys_metrics):
        assert metrics["vad_streaming"] is True
        assert metrics["vad_input_frames"] == 1024
        assert metrics["vad_accepted_frames"] == 512
        assert metrics["vad_filtered_frames"] == 512
        assert metrics["vad_filtered_seconds"] == pytest.approx(0.032)
    assert len(filters) == 2


def test_input_wav_silero_behavior_remains_offline_and_wall_clock_aligned(
    tmp_path: Path,
    monkeypatch,
) -> None:
    wav_path = tmp_path / "input.wav"
    with wave.open(str(wav_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16_000)
        wav_file.writeframes(_window(1) + _window(2))

    monkeypatch.setattr(
        vosk_backend,
        "detect_silero_speech_windows",
        lambda *_args, **_kwargs: [SpeechWindow(start=0.032, end=0.064)],
    )
    recognizer = _OneResultRecognizer()
    metrics: dict = {}
    timeline = AcceptedAudioTimeline(16_000)
    segments = []

    duration = vosk_backend._transcribe_wav(
        VoskLiveConfig(
            model_path=tmp_path,
            source="MIC",
            input_wav=wav_path,
            block_ms=32,
            vad="silero",
        ),
        recognizer,
        "synthetic-vosk",
        segments,
        [],
        metrics,
        timeline,
    )

    assert duration == pytest.approx(0.064)
    assert recognizer.blocks == [_window(2)]
    assert [(item.start, item.end) for item in segments] == [(0.032, 0.064)]
    assert metrics["vad_streaming"] is False
    assert metrics["vad_input_frames"] == 1024
    assert metrics["vad_accepted_frames"] == 512
