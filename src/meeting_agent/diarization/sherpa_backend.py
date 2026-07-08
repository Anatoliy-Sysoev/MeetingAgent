from __future__ import annotations

import importlib.util
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .normalize import normalize_intervals
from .schema import DiarizationInterval, DiarizationReport


BACKEND_NAME = "sherpa-onnx/pyannote-seg-3.0+wespeaker-resnet34"


class SherpaDiarizationError(RuntimeError):
    pass


@dataclass(frozen=True)
class SherpaDiarizationConfig:
    segmentation_model: Path
    embedding_model: Path
    num_speakers: int | None = None
    min_speakers: int | None = None
    max_speakers: int | None = None
    cluster_threshold: float = 0.5
    min_duration_on: float = 0.3
    min_duration_off: float = 0.5
    num_threads: int = 1


@dataclass(frozen=True)
class SherpaDiarizationResult:
    intervals: list[DiarizationInterval]
    report: DiarizationReport


def validate_model_paths(config: SherpaDiarizationConfig) -> None:
    missing = [
        path
        for path in (config.segmentation_model, config.embedding_model)
        if not path.exists()
    ]
    if missing:
        joined = ", ".join(str(path) for path in missing)
        raise SherpaDiarizationError(f"Missing diarization model file(s): {joined}")


def validate_runtime_dependencies() -> None:
    """Validate optional sherpa-onnx diarization runtime dependencies.

    This is intentionally a lightweight import-spec check so API readiness can
    call it without importing heavy native libraries. The actual backend still
    imports the modules at execution time in ``_import_runtime``.
    """
    missing = [
        module_name
        for module_name in ("numpy", "sherpa_onnx", "soundfile")
        if importlib.util.find_spec(module_name) is None
    ]
    if missing:
        joined = ", ".join(missing)
        raise SherpaDiarizationError(
            "sherpa-onnx diarization dependencies are not installed "
            f"({joined}). Install them in an isolated env with "
            "requirements-diarization.txt."
        )


def _import_runtime():
    try:
        import numpy as np  # type: ignore
        import sherpa_onnx  # type: ignore
        import soundfile as sf  # type: ignore
    except ImportError as exc:
        raise SherpaDiarizationError(
            "sherpa-onnx diarization dependencies are not installed. "
            "Install them in an isolated env with requirements-diarization.txt."
        ) from exc
    return np, sherpa_onnx, sf


def build_diarizer(config: SherpaDiarizationConfig):
    validate_model_paths(config)
    _, sherpa_onnx, _ = _import_runtime()

    clustering_kwargs: dict[str, Any] = {"threshold": config.cluster_threshold}
    if config.num_speakers is not None:
        clustering_kwargs["num_clusters"] = config.num_speakers

    sd_config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                model=str(config.segmentation_model),
            ),
        ),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(
            model=str(config.embedding_model),
            num_threads=config.num_threads,
        ),
        clustering=sherpa_onnx.FastClusteringConfig(**clustering_kwargs),
        min_duration_on=config.min_duration_on,
        min_duration_off=config.min_duration_off,
    )
    if not sd_config.validate():
        raise SherpaDiarizationError("Invalid sherpa-onnx diarization config.")
    return sherpa_onnx.OfflineSpeakerDiarization(sd_config)


def diarize_wav(wav_path: Path, config: SherpaDiarizationConfig) -> SherpaDiarizationResult:
    if not wav_path.exists():
        raise SherpaDiarizationError(f"Audio file not found: {wav_path}")

    np, _, sf = _import_runtime()
    start_time = time.monotonic()
    audio, sample_rate = sf.read(str(wav_path), dtype="float32", always_2d=True)
    mono = np.ascontiguousarray(audio[:, 0])
    diarizer = build_diarizer(config)
    expected_sample_rate = int(diarizer.sample_rate)
    if int(sample_rate) != expected_sample_rate:
        raise SherpaDiarizationError(
            f"Expected {expected_sample_rate} Hz audio, got {sample_rate}. "
            "Run scripts/21_extract_audio.py first."
        )

    raw_result = diarizer.process(mono).sort_by_start_time()
    raw_intervals = [
        {
            "speaker": f"SPEAKER_{int(item.speaker):02d}",
            "start": float(item.start),
            "end": float(item.end),
            "confidence": None,
            "backend": BACKEND_NAME,
        }
        for item in raw_result
    ]
    intervals, warnings = normalize_intervals(raw_intervals, backend=BACKEND_NAME)
    elapsed = round(time.monotonic() - start_time, 3)
    duration = round(float(len(mono)) / expected_sample_rate, 3)
    speakers = {interval.speaker for interval in intervals}
    report = DiarizationReport(
        backend="sherpa-onnx",
        segmentation_model=config.segmentation_model.name,
        embedding_model=config.embedding_model.name,
        num_speakers=config.num_speakers if config.num_speakers is not None else "auto",
        min_speakers=config.min_speakers,
        max_speakers=config.max_speakers,
        cluster_threshold=config.cluster_threshold,
        min_duration_on=config.min_duration_on,
        min_duration_off=config.min_duration_off,
        sample_rate=expected_sample_rate,
        audio_duration_sec=duration,
        processed_in_sec=elapsed,
        rtf=round(elapsed / duration, 3) if duration > 0 else None,
        intervals_count=len(intervals),
        speakers_count=len(speakers),
        created_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        warnings=warnings,
    )
    return SherpaDiarizationResult(intervals=intervals, report=report)
