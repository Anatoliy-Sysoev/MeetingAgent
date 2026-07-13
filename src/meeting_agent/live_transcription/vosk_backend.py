from __future__ import annotations

import json
import queue
import time
import wave
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .schema import LiveSegment
from .vad import SileroVadConfig, VadBackendError, SpeechWindow, block_overlaps_speech, detect_silero_speech_windows
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
) -> None:
    if recognizer.AcceptWaveform(block):
        result = json.loads(recognizer.Result())
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
            segments.append(segment)
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
    if config.vad == "silero" and config.input_wav is None:
        raise VoskBackendError("Silero VAD currently requires --input-wav. Microphone streaming VAD is planned.")
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

    try:
        if config.input_wav is not None:
            audio_seconds = _transcribe_wav(config, recognizer, model_label, segments, partials)
        elif config.source == "MIC":
            audio_seconds = _transcribe_microphone(config, recognizer, model_label, segments, partials, runtime_metrics)
        else:
            try:
                audio_seconds = _transcribe_system_loopback(
                    config,
                    recognizer,
                    model_label,
                    segments,
                    partials,
                    runtime_metrics,
                )
            except WasapiLoopbackError as exc:
                raise VoskBackendError(str(exc)) from exc
    except KeyboardInterrupt:
        interrupted = True

    final_result = json.loads(recognizer.FinalResult())
    final_segment = _segment_from_result(
        final_result,
        index=len(segments),
        source=config.source,
        model=model_label,
        fallback_start=max(0.0, audio_seconds - (config.block_ms / 1000.0)),
        fallback_end=max(audio_seconds, 0.01),
        use_word_timestamps=config.vad != "silero",
    )
    if final_segment is not None:
        segments.append(final_segment)

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
            _accept_block(
                recognizer,
                block,
                cursor_start=cursor_start,
                cursor_end=cursor_end,
                config=config,
                model_label=model_label,
                segments=segments,
                partials=partials,
                use_word_timestamps=config.vad != "silero",
            )
        return frames_read / config.sample_rate


def _transcribe_microphone(
    config: VoskLiveConfig,
    recognizer: Any,
    model_label: str,
    segments: list[LiveSegment],
    partials: list[dict[str, Any]],
    runtime_metrics: dict[str, Any],
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
    frames_read = 0
    runtime_metrics["input_status_events"] = 0
    runtime_metrics["queue_timeouts"] = 0

    def callback(indata, frames, _time_info, status) -> None:
        if status:
            runtime_metrics["input_status_events"] += 1
        audio_queue.put(bytes(indata))

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
        while True:
            if max_frames is not None and frames_read >= max_frames:
                break
            try:
                block = audio_queue.get(timeout=0.5)
            except queue.Empty:
                runtime_metrics["queue_timeouts"] += 1
                continue
            if not block:
                continue
            block_frames = len(block) // 2
            cursor_start = frames_read / config.sample_rate
            frames_read += block_frames
            cursor_end = frames_read / config.sample_rate
            _accept_block(
                recognizer,
                block,
                cursor_start=cursor_start,
                cursor_end=cursor_end,
                config=config,
                model_label=model_label,
                segments=segments,
                partials=partials,
            )
    return frames_read / config.sample_rate


def _transcribe_system_loopback(
    config: VoskLiveConfig,
    recognizer: Any,
    model_label: str,
    segments: list[LiveSegment],
    partials: list[dict[str, Any]],
    runtime_metrics: dict[str, Any],
) -> float:
    max_frames = (
        int(config.sample_rate * config.duration_sec)
        if config.duration_sec is not None
        else None
    )
    output_frames = 0
    read_errors = 0
    interrupted = False

    def accept_canonical(block: bytes) -> None:
        nonlocal output_frames
        if not block:
            return
        block_frames = len(block) // 2
        if max_frames is not None:
            remaining = max(0, max_frames - output_frames)
            if remaining <= 0:
                return
            if block_frames > remaining:
                block = block[: remaining * 2]
                block_frames = remaining
        cursor_start = output_frames / config.sample_rate
        output_frames += block_frames
        cursor_end = output_frames / config.sample_rate
        _accept_block(
            recognizer,
            block,
            cursor_start=cursor_start,
            cursor_end=cursor_end,
            config=config,
            model_label=model_label,
            segments=segments,
            partials=partials,
        )

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
                while max_frames is None or output_frames < max_frames:
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
        finally:
            runtime_metrics.update(
                {
                    "input_frames": converter.input_frames,
                    "output_frames": output_frames,
                    "resampler_clips": converter.clips,
                    "read_errors": read_errors,
                    "interrupted": interrupted,
                }
            )
    return output_frames / config.sample_rate
