from __future__ import annotations

import json
import queue
import time
import wave
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from .schema import LiveSegment
from .vad import (
    AcceptedAudioTimeline,
    SileroVadConfig,
    SpeechWindow,
    TimedAudioBlock,
    VadBackendError,
    block_overlaps_speech,
    create_streaming_silero_filter,
    detect_silero_speech_windows,
)
from .wasapi_loopback import (
    Pcm16MonoResampler,
    WasapiLoopbackError,
    open_wasapi_loopback_stream,
)


@dataclass(frozen=True)
class VoskLiveConfig:
    model_path: Path
    source: str = "MIC"
    sample_rate: int = 16_000
    block_ms: int = 300
    duration_sec: float | None = None
    input_wav: Path | None = None
    audio_device_index: int | None = None
    save_partials: bool = True
    vad: str = "none"
    silero_vad: SileroVadConfig = SileroVadConfig()


@dataclass(frozen=True)
class VoskLiveResult:
    segments: list[LiveSegment]
    partials: list[dict[str, Any]]
    metrics: dict[str, Any]


class VoskBackendError(RuntimeError):
    pass


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _load_vosk():
    try:
        from vosk import KaldiRecognizer, Model, SetLogLevel
    except ImportError as exc:
        raise VoskBackendError(
            "Vosk is not installed. Install optional live dependencies: "
            "python -m pip install -r requirements-live.txt"
        ) from exc
    SetLogLevel(-1)
    return KaldiRecognizer, Model


def _segment_from_result(
    result: dict[str, Any],
    *,
    index: int,
    source: str,
    model: str,
    fallback_start: float,
    fallback_end: float,
    use_word_timestamps: bool = True,
) -> LiveSegment | None:
    text = str(result.get("text") or "").strip()
    if not text:
        return None

    words = result.get("result")
    start = fallback_start
    end = max(fallback_end, fallback_start + 0.01)
    confidence: float | None = None
    if use_word_timestamps and isinstance(words, list) and words:
        starts = [word.get("start") for word in words if isinstance(word, dict) and isinstance(word.get("start"), (int, float))]
        ends = [word.get("end") for word in words if isinstance(word, dict) and isinstance(word.get("end"), (int, float))]
        confs = [word.get("conf") for word in words if isinstance(word, dict) and isinstance(word.get("conf"), (int, float))]
        if starts:
            start = float(min(starts))
        if ends:
            end = max(float(max(ends)), start + 0.01)
        if confs:
            confidence = round(sum(float(value) for value in confs) / len(confs), 4)

    return LiveSegment(
        segment_id=f"live-seg-{index:06d}",
        segment_index=index,
        start=round(start, 3),
        end=round(end, 3),
        text=text,
        source=source,
        engine="vosk",
        model=model,
        confidence=confidence,
        is_final=True,
        created_at=_now_iso(),
        metadata={"words_count": len(words) if isinstance(words, list) else None},
    )


def _accept_block(
    recognizer: Any,
    block: bytes,
    *,
    cursor_start: float,
    cursor_end: float,
    config: VoskLiveConfig,
    model_label: str,
    segments: list[LiveSegment],
    partials: list[dict[str, Any]],
    use_word_timestamps: bool = True,
    timestamp_mapper: AcceptedAudioTimeline | None = None,
) -> None:
    if recognizer.AcceptWaveform(block):
        result = json.loads(recognizer.Result())
        if timestamp_mapper is not None:
            result = timestamp_mapper.remap_result(result)
        segment = _segment_from_result(
            result,
            index=len(segments),
            source=config.source,
            model=model_label,
            fallback_start=cursor_start,
            fallback_end=cursor_end,
            use_word_timestamps=use_word_timestamps,
        )
        if segment is not None:
            _append_monotonic_segment(segments, segment)
    elif config.save_partials:
        partial = json.loads(recognizer.PartialResult())
        text = str(partial.get("partial") or "").strip()
        if text:
            partials.append(
                {
                    "timestamp": _now_iso(),
                    "start": round(cursor_start, 3),
                    "end": round(cursor_end, 3),
                    "text": text,
                    "source": config.source,
                    "engine": "vosk",
                    "model": model_label,
                    "is_final": False,
                }
            )


def _append_monotonic_segment(
    segments: list[LiveSegment],
    segment: LiveSegment,
) -> None:
    if not segments or segment.start >= segments[-1].end:
        segments.append(segment)
        return
    start = segments[-1].end
    segments.append(
        replace(
            segment,
            start=round(start, 3),
            end=round(max(segment.end, start + 0.01), 3),
        )
    )


class _CanonicalStreamConsumer:
    def __init__(
        self,
        *,
        config: VoskLiveConfig,
        recognizer: Any,
        model_label: str,
        segments: list[LiveSegment],
        partials: list[dict[str, Any]],
        timeline: AcceptedAudioTimeline | None,
        runtime_metrics: dict[str, Any],
    ) -> None:
        self.config = config
        self.recognizer = recognizer
        self.model_label = model_label
        self.segments = segments
        self.partials = partials
        self.timeline = timeline
        self.runtime_metrics = runtime_metrics
        self.input_frames = 0
        self._closed = False
        self._vad_filter = None
        if config.vad == "silero":
            self._vad_filter = create_streaming_silero_filter(
                sample_rate=config.sample_rate,
                config=config.silero_vad,
            )

    def consume(self, block: bytes) -> None:
        if self._closed:
            raise VadBackendError("Canonical audio consumer is already finalized")
        if not block:
            return
        if len(block) % 2:
            raise VadBackendError("Canonical audio contains an incomplete PCM frame")
        start_frame = self.input_frames
        self.input_frames += len(block) // 2
        if self._vad_filter is None:
            outputs = [
                TimedAudioBlock(
                    data=block,
                    start_frame=start_frame,
                    end_frame=self.input_frames,
                )
            ]
        else:
            outputs = self._vad_filter.process(block)
        self._feed(outputs)

    def close(self) -> None:
        if self._closed:
            return
        if self._vad_filter is not None:
            self._feed(self._vad_filter.close())
            self.runtime_metrics.update(
                {
                    "vad_streaming": True,
                    "vad_window_frames": self._vad_filter.window_frames,
                    "vad_input_frames": self._vad_filter.input_frames,
                    "vad_accepted_frames": self._vad_filter.accepted_frames,
                    "vad_filtered_frames": self._vad_filter.filtered_frames,
                    "vad_filtered_seconds": round(
                        self._vad_filter.filtered_frames / self.config.sample_rate,
                        3,
                    ),
                    "vad_speech_windows_count": len(
                        self._vad_filter.speech_windows
                    ),
                    "vad_short_speech_dropped": (
                        self._vad_filter.short_speech_dropped
                    ),
                    "vad_warnings": self._vad_filter.warnings,
                }
            )
        self._closed = True

    def _feed(self, blocks: list[TimedAudioBlock]) -> None:
        for block in blocks:
            if self.timeline is not None:
                self.timeline.add(block)
            _accept_block(
                self.recognizer,
                block.data,
                cursor_start=block.start_frame / self.config.sample_rate,
                cursor_end=block.end_frame / self.config.sample_rate,
                config=self.config,
                model_label=self.model_label,
                segments=self.segments,
                partials=self.partials,
                use_word_timestamps=True,
                timestamp_mapper=self.timeline,
            )


def transcribe_vosk_live(config: VoskLiveConfig) -> VoskLiveResult:
    if not config.model_path.exists():
        raise VoskBackendError(f"Vosk model path does not exist: {config.model_path}")
    if config.sample_rate <= 0:
        raise VoskBackendError("--sample-rate must be positive.")
    if config.block_ms <= 0:
        raise VoskBackendError("--block-ms must be positive.")
    if config.vad not in {"none", "silero"}:
        raise VoskBackendError(f"Unsupported VAD mode: {config.vad}")
    if config.source not in {"MIC", "SYS", "MIX"}:
        raise VoskBackendError(f"Unsupported live source: {config.source}")
    if config.input_wav is None and config.source == "MIX":
        raise VoskBackendError("Live MIX capture is not implemented")
    if (
        config.input_wav is None
        and config.source == "SYS"
        and config.sample_rate != 16_000
    ):
        raise VoskBackendError("Live SYS capture requires canonical 16000 Hz output")

    KaldiRecognizer, Model = _load_vosk()
    model = Model(str(config.model_path))
    recognizer = KaldiRecognizer(model, float(config.sample_rate))
    recognizer.SetWords(True)
    model_label = config.model_path.name
    segments: list[LiveSegment] = []
    partials: list[dict[str, Any]] = []
    started = time.time()
    audio_seconds = 0.0
    interrupted = False
    runtime_metrics: dict[str, Any] = {}
    timeline = (
        AcceptedAudioTimeline(config.sample_rate)
        if config.vad == "silero"
        else None
    )

    try:
        if config.input_wav is not None:
            audio_seconds = _transcribe_wav(
                config,
                recognizer,
                model_label,
                segments,
                partials,
                runtime_metrics,
                timeline,
            )
        elif config.source == "MIC":
            audio_seconds = _transcribe_microphone(
                config,
                recognizer,
                model_label,
                segments,
                partials,
                runtime_metrics,
                timeline,
            )
        else:
            try:
                audio_seconds = _transcribe_system_loopback(
                    config,
                    recognizer,
                    model_label,
                    segments,
                    partials,
                    runtime_metrics,
                    timeline,
                )
            except WasapiLoopbackError as exc:
                raise VoskBackendError(str(exc)) from exc
    except VadBackendError as exc:
        raise VoskBackendError(str(exc)) from exc
    except KeyboardInterrupt:
        interrupted = True

    final_result = json.loads(recognizer.FinalResult())
    if timeline is not None:
        final_result = timeline.remap_result(final_result)
    fallback_start = max(0.0, audio_seconds - (config.block_ms / 1000.0))
    fallback_end = max(audio_seconds, 0.01)
    if timeline is not None and timeline.last_source_span is not None:
        fallback_start, fallback_end = timeline.last_source_span
    final_segment = _segment_from_result(
        final_result,
        index=len(segments),
        source=config.source,
        model=model_label,
        fallback_start=fallback_start,
        fallback_end=fallback_end,
        use_word_timestamps=True,
    )
    if final_segment is not None:
        _append_monotonic_segment(segments, final_segment)

    return VoskLiveResult(
        segments=segments,
        partials=partials,
        metrics={
            "duration": round(audio_seconds, 3),
            "elapsed_seconds": round(time.time() - started, 3),
            "input_mode": "wav" if config.input_wav else "capture",
            "vad": config.vad,
            "interrupted": interrupted,
            **runtime_metrics,
        },
    )


def _transcribe_wav(
    config: VoskLiveConfig,
    recognizer: Any,
    model_label: str,
    segments: list[LiveSegment],
    partials: list[dict[str, Any]],
    runtime_metrics: dict[str, Any],
    timeline: AcceptedAudioTimeline | None,
) -> float:
    assert config.input_wav is not None
    if not config.input_wav.exists():
        raise VoskBackendError(f"Input WAV does not exist: {config.input_wav}")

    with wave.open(str(config.input_wav), "rb") as wav:
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        sample_rate = wav.getframerate()
        if channels != 1 or sample_width != 2 or sample_rate != config.sample_rate:
            raise VoskBackendError(
                "Input WAV must be mono 16-bit PCM with sample rate "
                f"{config.sample_rate}; got channels={channels}, sample_width={sample_width}, sample_rate={sample_rate}."
            )
        frames_per_block = max(1, int(config.sample_rate * config.block_ms / 1000))
        frames_limit = None
        if config.duration_sec is not None:
            frames_limit = int(config.sample_rate * config.duration_sec)

        speech_windows: list[SpeechWindow] = []
        if config.vad == "silero":
            try:
                speech_windows = detect_silero_speech_windows(
                    config.input_wav,
                    sample_rate=config.sample_rate,
                    config=config.silero_vad,
                )
            except VadBackendError as exc:
                raise VoskBackendError(str(exc)) from exc

        frames_read = 0
        accepted_frames = 0
        while True:
            remaining = frames_per_block
            if frames_limit is not None:
                remaining = min(remaining, max(0, frames_limit - frames_read))
                if remaining <= 0:
                    break
            block = wav.readframes(remaining)
            if not block:
                break
            block_frames = len(block) // sample_width // channels
            cursor_start = frames_read / config.sample_rate
            frames_read += block_frames
            cursor_end = frames_read / config.sample_rate
            if config.vad == "silero" and not block_overlaps_speech(cursor_start, cursor_end, speech_windows):
                continue
            if timeline is not None:
                timeline.add(
                    TimedAudioBlock(
                        data=block,
                        start_frame=frames_read - block_frames,
                        end_frame=frames_read,
                    )
                )
                accepted_frames += block_frames
            _accept_block(
                recognizer,
                block,
                cursor_start=cursor_start,
                cursor_end=cursor_end,
                config=config,
                model_label=model_label,
                segments=segments,
                partials=partials,
                use_word_timestamps=True,
                timestamp_mapper=timeline,
            )
        if config.vad == "silero":
            filtered_frames = max(0, frames_read - accepted_frames)
            runtime_metrics.update(
                {
                    "vad_streaming": False,
                    "vad_input_frames": frames_read,
                    "vad_accepted_frames": accepted_frames,
                    "vad_filtered_frames": filtered_frames,
                    "vad_filtered_seconds": round(
                        filtered_frames / config.sample_rate,
                        3,
                    ),
                    "vad_speech_windows_count": len(speech_windows),
                    "vad_short_speech_dropped": 0,
                    "vad_warnings": (
                        [] if accepted_frames else ["vad_no_speech_detected"]
                    ),
                }
            )
        return frames_read / config.sample_rate


def _transcribe_microphone(
    config: VoskLiveConfig,
    recognizer: Any,
    model_label: str,
    segments: list[LiveSegment],
    partials: list[dict[str, Any]],
    runtime_metrics: dict[str, Any],
    timeline: AcceptedAudioTimeline | None = None,
) -> float:
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise VoskBackendError(
            "sounddevice is not installed. Install optional live dependencies: "
            "python -m pip install -r requirements-live.txt"
        ) from exc

    audio_queue: queue.Queue[bytes] = queue.Queue()
    frames_per_block = max(1, int(config.sample_rate * config.block_ms / 1000))
    max_frames = int(config.sample_rate * config.duration_sec) if config.duration_sec is not None else None
    consumer = _CanonicalStreamConsumer(
        config=config,
        recognizer=recognizer,
        model_label=model_label,
        segments=segments,
        partials=partials,
        timeline=timeline,
        runtime_metrics=runtime_metrics,
    )
    interrupted = False
    runtime_metrics["input_status_events"] = 0
    runtime_metrics["queue_timeouts"] = 0

    def callback(indata, frames, _time_info, status) -> None:
        if status:
            runtime_metrics["input_status_events"] += 1
        audio_queue.put(bytes(indata))

    try:
        with sd.RawInputStream(
            samplerate=config.sample_rate,
            blocksize=frames_per_block,
            dtype="int16",
            channels=1,
            device=config.audio_device_index,
            callback=callback,
        ):
            runtime_metrics.update(
                {
                    "capture_backend": "sounddevice",
                    "input_device_index": config.audio_device_index,
                    "input_sample_rate": config.sample_rate,
                    "input_channels": 1,
                    "output_sample_rate": config.sample_rate,
                    "output_channels": 1,
                }
            )
            try:
                while max_frames is None or consumer.input_frames < max_frames:
                    try:
                        block = audio_queue.get(timeout=0.5)
                    except queue.Empty:
                        runtime_metrics["queue_timeouts"] += 1
                        continue
                    if not block:
                        continue
                    if max_frames is not None:
                        remaining = max_frames - consumer.input_frames
                        block = block[: remaining * 2]
                    consumer.consume(block)
            except KeyboardInterrupt:
                interrupted = True
            consumer.close()
    finally:
        runtime_metrics["interrupted"] = interrupted
    return consumer.input_frames / config.sample_rate


def _transcribe_system_loopback(
    config: VoskLiveConfig,
    recognizer: Any,
    model_label: str,
    segments: list[LiveSegment],
    partials: list[dict[str, Any]],
    runtime_metrics: dict[str, Any],
    timeline: AcceptedAudioTimeline | None = None,
) -> float:
    max_frames = (
        int(config.sample_rate * config.duration_sec)
        if config.duration_sec is not None
        else None
    )
    read_errors = 0
    interrupted = False
    consumer = _CanonicalStreamConsumer(
        config=config,
        recognizer=recognizer,
        model_label=model_label,
        segments=segments,
        partials=partials,
        timeline=timeline,
        runtime_metrics=runtime_metrics,
    )

    def accept_canonical(block: bytes) -> None:
        if not block:
            return
        block_frames = len(block) // 2
        if max_frames is not None:
            remaining = max(0, max_frames - consumer.input_frames)
            if remaining <= 0:
                return
            if block_frames > remaining:
                block = block[: remaining * 2]
        consumer.consume(block)

    with open_wasapi_loopback_stream(
        device_index=config.audio_device_index,
        block_ms=config.block_ms,
    ) as opened:
        device = opened.device
        frames_per_block = max(1, int(device.sample_rate * config.block_ms / 1000))
        converter = Pcm16MonoResampler(
            input_rate=device.sample_rate,
            input_channels=device.channels,
            output_rate=config.sample_rate,
        )
        runtime_metrics.update(
            {
                "capture_backend": "pyaudiowpatch",
                "input_device_index": device.index,
                "input_sample_rate": device.sample_rate,
                "input_channels": device.channels,
                "input_dtype": "int16",
                "output_sample_rate": config.sample_rate,
                "output_channels": 1,
                "output_dtype": "int16",
                "resampler": "soxr_hq",
            }
        )
        try:
            try:
                while max_frames is None or consumer.input_frames < max_frames:
                    try:
                        native_block = opened.stream.read(
                            frames_per_block,
                            exception_on_overflow=False,
                        )
                    except Exception as exc:  # noqa: BLE001 - normalize native read failures
                        read_errors += 1
                        raise WasapiLoopbackError(
                            "WASAPI loopback stream read failed"
                        ) from exc
                    accept_canonical(converter.convert(native_block))
            except KeyboardInterrupt:
                interrupted = True
            accept_canonical(converter.flush())
            consumer.close()
        finally:
            runtime_metrics.update(
                {
                    "input_frames": converter.input_frames,
                    "converted_frames": converter.output_frames,
                    "output_frames": consumer.input_frames,
                    "resampler_clips": converter.clips,
                    "read_errors": read_errors,
                    "interrupted": interrupted,
                }
            )
    return consumer.input_frames / config.sample_rate
