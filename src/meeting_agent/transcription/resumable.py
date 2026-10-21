from __future__ import annotations

import math
import os
import subprocess
import uuid
import wave
from contextlib import nullcontext
from dataclasses import asdict
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Callable

from .checkpoints import CheckpointError, CheckpointStore, file_sha256


def _model_revision(config: Any) -> str | None:
    try:
        from faster_whisper.utils import _MODELS
        from huggingface_hub import try_to_load_from_cache
        repository = _MODELS.get(config.model, config.model)
        cached = try_to_load_from_cache(repository, "model.bin")
        if isinstance(cached, str):
            return Path(cached).parent.name
    except (ImportError, ValueError, OSError):
        pass
    return None


def identity(media: Path, config: Any, meeting_dir: Path | None = None) -> dict[str, Any]:
    versions = {}
    for package in ("faster-whisper", "ctranslate2"):
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            versions[package] = "unavailable"
    settings = asdict(config)
    local_model = Path(config.model)
    if local_model.is_dir():
        versions["model_files"] = {
            name: file_sha256(local_model / name)
            for name in ("model.bin", "config.json", "tokenizer.json", "preprocessor_config.json")
            if (local_model / name).is_file()
        }
    return {"audio_sha256": file_sha256(media), "settings": settings, "versions": versions,
            "model_revision": _model_revision(config),
            "source": media.resolve().relative_to(meeting_dir.resolve()).as_posix() if meeting_dir else None}


def validate_resume(media: Path, config: Any, store: CheckpointStore) -> None:
    header = store.header()
    if header and header["identity"] != identity(media, config, store.meeting_dir):
        raise CheckpointError("Audio or recognition settings changed; start a new run explicitly")


def _pcm_audio(media: Path, store: CheckpointStore) -> Path:
    try:
        with wave.open(str(media), "rb") as wav:
            if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getcomptype()) == (1, 2, 16000, "NONE"):
                return media
    except (wave.Error, EOFError):
        pass
    target = store.path("transcript/_whisper/input.wav")
    temporary = target.with_name(f"input-{uuid.uuid4().hex}.wav")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        completed = subprocess.run(
            ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(media),
             "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(temporary)],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        if completed.returncode:
            raise CheckpointError("Could not prepare PCM audio for resumable transcription")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def transcribe_blocks(media: Path, config: Any, meeting_dir: Path, *, resume: bool,
                      model_loader: Callable, progress_callback: Callable | None = None,
                      saved_callback: Callable | None = None,
                      lock_held: bool = False) -> tuple[list[dict], dict]:
    import numpy as np

    if not math.isfinite(config.block_seconds) or not 1 <= config.block_seconds <= 600:
        raise CheckpointError("Whisper block duration must be between 1 and 600 seconds")
    store = CheckpointStore(meeting_dir)
    with nullcontext() if lock_held else store.lock():
        fingerprint = identity(media, config, meeting_dir)
        if resume:
            validate_resume(media, config, store)
        pcm = _pcm_audio(media, store)
        with wave.open(str(pcm), "rb") as audio:
            rate, total = audio.getframerate(), audio.getnframes()
            header = store.begin(fingerprint, total_frames=total, sample_rate=rate,
                                 block_frames=round(rate * config.block_seconds), resume=resume)
            stat = media.stat()
            header["source_stat"] = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
            from .checkpoints import atomic_json
            atomic_json(store.current, header)
            rows, first = store.prefix(header)
            header["saved_blocks"] = first
            atomic_json(store.current, header)
            blocks = math.ceil(total / header["block_frames"])
            saved = min(first * header["block_frames"], total) / rate
            duration = total / rate
            if saved_callback:
                saved_callback(saved, duration, True)
            if progress_callback:
                progress_callback(saved, duration)
            model = model_loader(config) if first < blocks else None
            # The first model load can populate a previously empty HF cache.
            revision = _model_revision(config)
            if revision != fingerprint["model_revision"]:
                if first:
                    raise CheckpointError("Model revision changed; start a new run explicitly")
                fingerprint["model_revision"] = revision
                header = store.begin(fingerprint, total_frames=total, sample_rate=rate,
                                     block_frames=header["block_frames"], resume=False)
                header["source_stat"] = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
                atomic_json(store.current, header)
            for index in range(first, blocks):
                a, b = store.bounds(header, index)
                audio.setpos(a)
                raw = audio.readframes(b - a)
                if len(raw) != (b - a) * 2:
                    raise CheckpointError("Audio ended before the expected frame boundary")
                samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
                kwargs = dict(language=config.language, vad_filter=config.vad_filter,
                              beam_size=config.beam_size)
                if config.hotwords:
                    kwargs["hotwords"] = " ".join(config.hotwords)
                elif config.initial_prompt:
                    kwargs["initial_prompt"] = config.initial_prompt
                iterator, _info = model.transcribe(samples, **kwargs)
                pending = []
                for segment in iterator:
                    local_start, local_end = float(segment.start), float(segment.end)
                    if not all(math.isfinite(v) for v in (local_start, local_end)):
                        continue
                    start = max(a / rate, a / rate + local_start)
                    end = min(b / rate, a / rate + local_end)
                    text = str(segment.text or "").strip()
                    if not all(math.isfinite(v) for v in (start, end)) or end <= start or not text:
                        continue
                    row = dict(start=round(start, 3), end=round(end, 3), text=text,
                               source=config.source, engine="faster-whisper", language=config.language)
                    for key in ("avg_logprob", "no_speech_prob"):
                        value = getattr(segment, key, None)
                        if value is not None and math.isfinite(float(value)):
                            row[key] = float(value)
                    if row["end"] <= row["start"]:
                        continue
                    pending.append(row)
                    if progress_callback:
                        progress_callback(end, duration)
                store.commit(header, index, pending)
                rows.extend(pending)
                if saved_callback:
                    saved_callback(b / rate, duration, False)
                if progress_callback:
                    progress_callback(b / rate, duration)
    return rows, dict(asr_engine="faster-whisper", asr_model=config.model,
                      duration=duration, language=config.language, resume=resume,
                      resumed_from_seconds=saved, checkpoint_generation=header["generation"],
                      blocks_total=blocks, blocks_reused=first,
                      block_seconds=config.block_seconds, device=config.device,
                      compute_type=config.compute_type, beam_size=config.beam_size,
                      vad_filter=config.vad_filter)
