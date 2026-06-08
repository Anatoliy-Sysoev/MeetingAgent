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


@dataclass(frozen=True)
class VoskLiveConfig:
    model_path: Path
    source: str = "MIC"
    sample_rate: int = 16_000
    block_ms: int = 300
    duration_sec: float | None = None
    input_wav: Path | None = None
    save_partials: bool = True


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
) -> LiveSegment | None:
    text = str(result.get("text") or "").strip()
    if not text:
        return None

    words = result.get("result")
    start = fallback_start
    end = max(fallback_end, fallback_start + 0.01)
    confidence: float | None = None
    if isinstance(words, list) and words:
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

    KaldiRecognizer, Model = _load_vosk()
    model = Model(str(config.model_path))
    recognizer = KaldiRecognizer(model, float(config.sample_rate))
    recognizer.SetWords(True)
    model_label = config.model_path.name
    segments: list[LiveSegment] = []
    partials: list[dict[str, Any]] = []
    started = time.time()
    audio_seconds = 0.0

    if config.input_wav is not None:
        audio_seconds = _transcribe_wav(config, recognizer, model_label, segments, partials)
    else:
        audio_seconds = _transcribe_microphone(config, recognizer, model_label, segments, partials)

    final_result = json.loads(recognizer.FinalResult())
    final_segment = _segment_from_result(
        final_result,
        index=len(segments),
        source=config.source,
        model=model_label,
        fallback_start=max(0.0, audio_seconds - (config.block_ms / 1000.0)),
        fallback_end=max(audio_seconds, 0.01),
    )
    if final_segment is not None:
        segments.append(final_segment)

    return VoskLiveResult(
        segments=segments,
        partials=partials,
        metrics={
            "duration": round(audio_seconds, 3),
            "elapsed_seconds": round(time.time() - started, 3),
            "input_wav": str(config.input_wav) if config.input_wav else None,
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


def _transcribe_microphone(
    config: VoskLiveConfig,
    recognizer: Any,
    model_label: str,
    segments: list[LiveSegment],
    partials: list[dict[str, Any]],
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

    def callback(indata, frames, _time_info, status) -> None:
        if status:
            audio_queue.put(b"")
        audio_queue.put(bytes(indata))

    with sd.RawInputStream(
        samplerate=config.sample_rate,
        blocksize=frames_per_block,
        dtype="int16",
        channels=1,
        callback=callback,
    ):
        while True:
            if max_frames is not None and frames_read >= max_frames:
                break
            block = audio_queue.get()
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
            if config.duration_sec is None:
                continue
    return frames_read / config.sample_rate
