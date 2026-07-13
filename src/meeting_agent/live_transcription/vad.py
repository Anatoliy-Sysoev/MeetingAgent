from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SpeechWindow:
    start: float
    end: float

    def overlaps(self, start: float, end: float) -> bool:
        return self.start < end and self.end > start

    def to_dict(self) -> dict[str, float]:
        return {"start": round(self.start, 3), "end": round(self.end, 3)}


@dataclass(frozen=True)
class SileroVadConfig:
    threshold: float = 0.5
    min_speech_ms: int = 250
    min_silence_ms: int = 100
    speech_pad_ms: int = 100


class VadBackendError(RuntimeError):
    pass


@dataclass(frozen=True)
class TimedAudioBlock:
    data: bytes
    start_frame: int
    end_frame: int

    def __post_init__(self) -> None:
        if self.start_frame < 0 or self.end_frame <= self.start_frame:
            raise ValueError("Timed audio block must have a positive frame span")
        if len(self.data) != (self.end_frame - self.start_frame) * 2:
            raise ValueError("Timed audio block must contain mono int16 PCM")


@dataclass(frozen=True)
class _TimelineSpan:
    accepted_start: int
    accepted_end: int
    source_start: int
    source_end: int


class AcceptedAudioTimeline:
    """Map compressed recognizer time back to original capture frames."""

    def __init__(self, sample_rate: int) -> None:
        if sample_rate <= 0:
            raise ValueError("Timeline sample rate must be positive")
        self.sample_rate = sample_rate
        self._spans: list[_TimelineSpan] = []
        self._accepted_ends: list[int] = []
        self.accepted_frames = 0

    def add(self, block: TimedAudioBlock) -> None:
        source_frames = block.end_frame - block.start_frame
        if self._spans and block.start_frame < self._spans[-1].source_end:
            raise VadBackendError("Accepted audio blocks must be monotonic")
        span = _TimelineSpan(
            accepted_start=self.accepted_frames,
            accepted_end=self.accepted_frames + source_frames,
            source_start=block.start_frame,
            source_end=block.end_frame,
        )
        if self._spans and block.start_frame == self._spans[-1].source_end:
            previous = self._spans[-1]
            span = _TimelineSpan(
                accepted_start=previous.accepted_start,
                accepted_end=span.accepted_end,
                source_start=previous.source_start,
                source_end=span.source_end,
            )
            self._spans[-1] = span
            self._accepted_ends[-1] = span.accepted_end
        else:
            self._spans.append(span)
            self._accepted_ends.append(span.accepted_end)
        self.accepted_frames = span.accepted_end

    @property
    def last_source_span(self) -> tuple[float, float] | None:
        if not self._spans:
            return None
        span = self._spans[-1]
        return (
            span.source_start / self.sample_rate,
            span.source_end / self.sample_rate,
        )

    def map_interval(self, start: float, end: float) -> tuple[float, float]:
        if not self._spans:
            return start, end
        start_frame = max(0.0, start * self.sample_rate)
        end_frame = max(start_frame, end * self.sample_rate)
        mapped_start = self._map_frame(start_frame, prefer_previous=False)
        mapped_end = self._map_frame(end_frame, prefer_previous=True)
        mapped_end = max(mapped_end, mapped_start)
        return (
            round(mapped_start / self.sample_rate, 3),
            round(mapped_end / self.sample_rate, 3),
        )

    def remap_result(self, result: dict[str, Any]) -> dict[str, Any]:
        words = result.get("result")
        if not isinstance(words, list) or not self._spans:
            return result
        mapped_result = dict(result)
        mapped_words: list[Any] = []
        for word in words:
            if not isinstance(word, dict):
                mapped_words.append(word)
                continue
            start = word.get("start")
            end = word.get("end")
            if not isinstance(start, (int, float)) or not isinstance(
                end, (int, float)
            ):
                mapped_words.append(dict(word))
                continue
            mapped_start, mapped_end = self.map_interval(float(start), float(end))
            mapped_word = dict(word)
            mapped_word["start"] = mapped_start
            mapped_word["end"] = mapped_end
            mapped_words.append(mapped_word)
        mapped_result["result"] = mapped_words
        return mapped_result

    def _map_frame(self, frame: float, *, prefer_previous: bool) -> float:
        clamped = min(max(frame, 0.0), float(self.accepted_frames))
        if prefer_previous:
            index = bisect_left(self._accepted_ends, clamped)
        else:
            index = bisect_right(self._accepted_ends, clamped)
        index = min(index, len(self._spans) - 1)
        span = self._spans[index]
        offset = max(0.0, clamped - span.accepted_start)
        return min(float(span.source_end), span.source_start + offset)


class StreamingSileroVadFilter:
    """Incremental 16 kHz mono PCM gate backed by Silero VADIterator."""

    window_frames = 512

    def __init__(
        self,
        *,
        sample_rate: int,
        config: SileroVadConfig,
        iterator: Any,
        tensor_factory: Callable[[bytes], Any],
    ) -> None:
        _validate_silero_config(sample_rate, config)
        self.sample_rate = sample_rate
        self.config = config
        self._iterator = iterator
        self._tensor_factory = tensor_factory
        self._pending = bytearray()
        self._processed_frames = 0
        self._history: list[TimedAudioBlock] = []
        self._candidate_start: int | None = None
        self._active = False
        self._last_emitted_frame = 0
        self._closed = False
        self.input_frames = 0
        self.accepted_frames = 0
        self.short_speech_dropped = 0
        self._accepted_windows: list[tuple[int, int]] = []

    def process(self, block: bytes | bytearray | memoryview) -> list[TimedAudioBlock]:
        if self._closed:
            raise VadBackendError("Streaming VAD is already finalized")
        if not isinstance(block, (bytes, bytearray, memoryview)):
            raise VadBackendError("Streaming VAD requires mono int16 PCM bytes")
        if len(block) % 2:
            raise VadBackendError("Streaming VAD received an incomplete PCM frame")
        raw = bytes(block)
        self.input_frames += len(raw) // 2
        self._pending.extend(raw)
        outputs: list[TimedAudioBlock] = []
        window_bytes = self.window_frames * 2
        while len(self._pending) >= window_bytes:
            window = bytes(self._pending[:window_bytes])
            del self._pending[:window_bytes]
            outputs.extend(
                self._process_window(window, actual_frames=self.window_frames)
            )
        return outputs

    def close(self) -> list[TimedAudioBlock]:
        if self._closed:
            return []
        outputs: list[TimedAudioBlock] = []
        if self._pending:
            actual_frames = len(self._pending) // 2
            padded = bytes(self._pending) + b"\x00\x00" * (
                self.window_frames - actual_frames
            )
            self._pending.clear()
            outputs.extend(self._process_window(padded, actual_frames=actual_frames))
        if self._candidate_start is not None and not self._active:
            speech_frames = self._processed_frames - self._candidate_start
            if speech_frames >= self._min_speech_frames:
                outputs.extend(self._emit_history(self._processed_frames))
            else:
                self.short_speech_dropped += 1
        self._candidate_start = None
        self._active = False
        reset_states = getattr(self._iterator, "reset_states", None)
        if callable(reset_states):
            reset_states()
        self._closed = True
        return outputs

    @property
    def filtered_frames(self) -> int:
        return max(0, self.input_frames - self.accepted_frames)

    @property
    def speech_windows(self) -> list[SpeechWindow]:
        return [
            SpeechWindow(
                start=start / self.sample_rate,
                end=end / self.sample_rate,
            )
            for start, end in self._accepted_windows
        ]

    @property
    def warnings(self) -> list[str]:
        warnings: list[str] = []
        if self.accepted_frames == 0:
            warnings.append("vad_no_speech_detected")
        if self.short_speech_dropped:
            warnings.append("vad_short_speech_dropped")
        return warnings

    @property
    def _min_speech_frames(self) -> int:
        return max(1, int(self.sample_rate * self.config.min_speech_ms / 1000))

    @property
    def _history_frames(self) -> int:
        speech_pad = int(self.sample_rate * self.config.speech_pad_ms / 1000)
        return max(self.window_frames * 2, speech_pad + self.window_frames)

    def _process_window(
        self,
        model_pcm: bytes,
        *,
        actual_frames: int,
    ) -> list[TimedAudioBlock]:
        start_frame = self._processed_frames
        end_frame = start_frame + actual_frames
        actual_pcm = model_pcm[: actual_frames * 2]
        if actual_frames:
            self._history.append(
                TimedAudioBlock(
                    data=actual_pcm,
                    start_frame=start_frame,
                    end_frame=end_frame,
                )
            )
        self._processed_frames = end_frame
        try:
            event = self._iterator(
                self._tensor_factory(model_pcm),
                return_seconds=False,
            )
        except Exception as exc:  # noqa: BLE001 - normalize optional model errors
            raise VadBackendError("Silero streaming VAD inference failed") from exc
        if event is not None and not isinstance(event, Mapping):
            raise VadBackendError("Silero streaming VAD returned an invalid event")

        event_start = self._event_frame(event, "start", end_frame)
        event_end = self._event_frame(event, "end", end_frame)
        if event_start is not None:
            self._candidate_start = max(self._last_emitted_frame, event_start)
            self._active = False

        outputs: list[TimedAudioBlock] = []
        if event_end is not None and self._candidate_start is not None:
            speech_frames = max(0, event_end - self._candidate_start)
            if self._active or speech_frames >= self._min_speech_frames:
                outputs.extend(self._emit_history(end_frame))
            else:
                self.short_speech_dropped += 1
            self._candidate_start = None
            self._active = False
        elif self._candidate_start is not None:
            if not self._active:
                candidate_frames = end_frame - self._candidate_start
                if candidate_frames >= self._min_speech_frames:
                    self._active = True
            if self._active:
                outputs.extend(self._emit_history(end_frame))

        self._prune_history(end_frame)
        return outputs

    def _event_frame(
        self,
        event: Mapping[str, Any] | None,
        key: str,
        current_end: int,
    ) -> int | None:
        if event is None or key not in event:
            return None
        value = event.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise VadBackendError("Silero streaming VAD returned an invalid event")
        return min(max(0, int(value)), current_end)

    def _emit_history(self, end_frame: int) -> list[TimedAudioBlock]:
        if self._candidate_start is None:
            return []
        emit_start = max(self._candidate_start, self._last_emitted_frame)
        outputs: list[TimedAudioBlock] = []
        for block in self._history:
            start = max(block.start_frame, emit_start)
            end = min(block.end_frame, end_frame)
            if end <= start:
                continue
            offset_start = (start - block.start_frame) * 2
            offset_end = (end - block.start_frame) * 2
            output = TimedAudioBlock(
                data=block.data[offset_start:offset_end],
                start_frame=start,
                end_frame=end,
            )
            outputs.append(output)
            self.accepted_frames += end - start
            self._record_window(start, end)
            self._last_emitted_frame = end
            emit_start = end
        return outputs

    def _record_window(self, start: int, end: int) -> None:
        if self._accepted_windows and start <= self._accepted_windows[-1][1]:
            previous_start, previous_end = self._accepted_windows[-1]
            self._accepted_windows[-1] = (previous_start, max(previous_end, end))
        else:
            self._accepted_windows.append((start, end))

    def _prune_history(self, current_end: int) -> None:
        if self._candidate_start is not None:
            keep_from = max(self._candidate_start, self._last_emitted_frame)
        else:
            keep_from = max(0, current_end - self._history_frames)
        retained: list[TimedAudioBlock] = []
        for block in self._history:
            if block.end_frame <= keep_from:
                continue
            if block.start_frame < keep_from:
                offset = (keep_from - block.start_frame) * 2
                retained.append(
                    TimedAudioBlock(
                        data=block.data[offset:],
                        start_frame=keep_from,
                        end_frame=block.end_frame,
                    )
                )
            else:
                retained.append(block)
        self._history = retained


def _validate_silero_config(sample_rate: int, config: SileroVadConfig) -> None:
    if sample_rate != 16_000:
        raise VadBackendError("Streaming Silero VAD requires 16000 Hz mono PCM")
    if not 0.0 < config.threshold <= 1.0:
        raise VadBackendError("Silero VAD threshold must be in (0, 1]")
    if not 0 < config.min_speech_ms <= 30_000:
        raise VadBackendError(
            "Silero VAD min_speech_ms must be in the range 1..30000"
        )
    if config.min_silence_ms < 0 or config.speech_pad_ms < 0:
        raise VadBackendError("Silero VAD silence/padding values must be non-negative")
    if config.min_silence_ms > 10_000:
        raise VadBackendError(
            "Silero VAD min_silence_ms must be in the range 0..10000"
        )
    if config.speech_pad_ms > 5_000:
        raise VadBackendError(
            "Silero VAD speech_pad_ms must be in the range 0..5000"
        )


def create_streaming_silero_filter(
    *,
    sample_rate: int,
    config: SileroVadConfig,
) -> StreamingSileroVadFilter:
    _validate_silero_config(sample_rate, config)
    try:
        import numpy as np
        import torch
        from silero_vad import VADIterator, load_silero_vad
    except (ImportError, OSError) as exc:
        raise VadBackendError(
            "Silero VAD is not installed. Install optional live dependencies: "
            "python -m pip install -r requirements-live.txt"
        ) from exc
    try:
        model = load_silero_vad()
        iterator = VADIterator(
            model,
            threshold=config.threshold,
            sampling_rate=sample_rate,
            min_silence_duration_ms=config.min_silence_ms,
            speech_pad_ms=config.speech_pad_ms,
        )
    except Exception as exc:  # noqa: BLE001 - normalize optional model failures
        raise VadBackendError("Silero streaming VAD failed to initialize") from exc

    def tensor_factory(pcm: bytes) -> Any:
        samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32)
        samples /= 32768.0
        return torch.from_numpy(samples)

    return StreamingSileroVadFilter(
        sample_rate=sample_rate,
        config=config,
        iterator=iterator,
        tensor_factory=tensor_factory,
    )


def detect_silero_speech_windows(
    wav_path: Path,
    *,
    sample_rate: int,
    config: SileroVadConfig,
) -> list[SpeechWindow]:
    try:
        from silero_vad import get_speech_timestamps, load_silero_vad, read_audio
    except ImportError as exc:
        raise VadBackendError(
            "Silero VAD is not installed. Install optional live dependencies: "
            "python -m pip install -r requirements-live.txt"
        ) from exc

    wav = read_audio(str(wav_path), sampling_rate=sample_rate)
    model = load_silero_vad()
    timestamps: list[dict[str, Any]] = get_speech_timestamps(
        wav,
        model,
        sampling_rate=sample_rate,
        threshold=config.threshold,
        min_speech_duration_ms=config.min_speech_ms,
        min_silence_duration_ms=config.min_silence_ms,
        speech_pad_ms=config.speech_pad_ms,
        return_seconds=True,
    )
    return [
        SpeechWindow(start=float(item["start"]), end=float(item["end"]))
        for item in timestamps
        if isinstance(item, dict) and "start" in item and "end" in item and float(item["end"]) > float(item["start"])
    ]


def block_overlaps_speech(start: float, end: float, windows: list[SpeechWindow]) -> bool:
    if not windows:
        return False
    return any(window.overlaps(start, end) for window in windows)
