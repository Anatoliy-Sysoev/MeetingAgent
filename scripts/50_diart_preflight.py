from __future__ import annotations

import argparse
import json
import math
import os
import struct
import sys
import tempfile
import wave
from pathlib import Path
from typing import Any


DEFAULT_SEGMENTATION_MODEL = "pyannote/segmentation-3.0"
DEFAULT_EMBEDDING_MODEL = "pyannote/embedding"


def _versions() -> dict[str, str]:
    import importlib.metadata

    packages = (
        "diart",
        "huggingface-hub",
        "numpy",
        "onnxruntime",
        "pyannote.audio",
        "torch",
        "torchaudio",
        "torchvision",
    )
    return {name: importlib.metadata.version(name) for name in packages}


def _write_synthetic_wav(path: Path, *, seconds: float = 6.0) -> None:
    sample_rate = 16_000
    frame_count = int(sample_rate * seconds)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        frames = bytearray()
        for index in range(frame_count):
            value = int(5_000 * math.sin(2 * math.pi * 220 * index / sample_rate))
            frames.extend(struct.pack("<h", value))
        wav.writeframes(bytes(frames))


def run_synthetic_stream_smoke() -> dict[str, Any]:
    import torch
    from diart import SpeakerDiarization, SpeakerDiarizationConfig
    from diart.inference import StreamingInference
    from diart.models import EmbeddingModel, SegmentationModel
    from diart.sources import FileAudioSource

    class DeterministicSegmentation:
        def to(self, _device: Any) -> "DeterministicSegmentation":
            return self

        def __call__(self, waveform: Any) -> Any:
            batch_size = int(waveform.shape[0])
            scores = torch.full((batch_size, 293, 3), 0.05, dtype=torch.float32)
            scores[:, :, 0] = 0.95
            return scores

    class DeterministicEmbedding:
        def to(self, _device: Any) -> "DeterministicEmbedding":
            return self

        def __call__(self, waveform: Any, weights: Any) -> Any:
            batch_size = int(waveform.shape[0])
            embedding = torch.zeros((batch_size, 8), dtype=torch.float32)
            embedding[:, 0] = 1.0
            return embedding

    config = SpeakerDiarizationConfig(
        segmentation=SegmentationModel(DeterministicSegmentation),
        embedding=EmbeddingModel(DeterministicEmbedding),
        duration=5.0,
        step=0.5,
        latency=1.0,
    )
    pipeline = SpeakerDiarization(config)
    with tempfile.TemporaryDirectory(prefix="meetingagent-diart-") as tmp:
        wav_path = Path(tmp) / "synthetic.wav"
        _write_synthetic_wav(wav_path)
        padding = pipeline.config.get_file_padding(wav_path)
        source = FileAudioSource(
            wav_path,
            pipeline.config.sample_rate,
            padding,
            pipeline.config.step,
        )
        pipeline.set_timestamp_shift(-padding[0])
        inference = StreamingInference(
            pipeline,
            source,
            do_profile=False,
            do_plot=False,
            show_progress=False,
        )
        prediction = inference()
    tracks = list(prediction.itertracks(yield_label=True))
    if not tracks:
        raise RuntimeError("Diart synthetic streaming smoke returned no speaker tracks")
    return {
        "tracks": len(tracks),
        "first_speaker": str(tracks[0][2]),
        "first_start": round(float(tracks[0][0].start), 3),
        "first_end": round(float(tracks[0][0].end), 3),
    }


def load_real_models(
    segmentation_name: str,
    embedding_name: str,
) -> dict[str, str]:
    import torch
    from diart import SpeakerDiarization, SpeakerDiarizationConfig
    from diart.models import EmbeddingModel, SegmentationModel

    token = os.getenv("HF_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "HF_TOKEN is required after accepting the pyannote model conditions"
        )
    use_token: str | bool = token
    segmentation = SegmentationModel.from_pretrained(
        segmentation_name,
        use_hf_token=use_token,
    )
    embedding = EmbeddingModel.from_pretrained(
        embedding_name,
        use_hf_token=use_token,
    )
    segmentation.to(torch.device("cpu")).eval()
    embedding.to(torch.device("cpu")).eval()
    SpeakerDiarization(
        SpeakerDiarizationConfig(
            segmentation=segmentation,
            embedding=embedding,
            step=0.5,
            latency=3.0,
        )
    )
    return {
        "segmentation": segmentation_name,
        "embedding": embedding_name,
        "hf_token_provided": "true",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the isolated MeetingAgent Diart pilot runtime",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON result")
    parser.add_argument(
        "--load-models",
        action="store_true",
        help="Download/load the real gated models and construct a CPU pipeline",
    )
    parser.add_argument("--segmentation", default=DEFAULT_SEGMENTATION_MODEL)
    parser.add_argument("--embedding", default=DEFAULT_EMBEDDING_MODEL)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result: dict[str, Any] = {
        "ok": False,
        "runtime": "diart-isolated-cpu",
        "versions": {},
    }
    try:
        result["versions"] = _versions()
        result["synthetic_stream"] = run_synthetic_stream_smoke()
        if args.load_models:
            result["models"] = load_real_models(args.segmentation, args.embedding)
        result["ok"] = True
    except Exception as exc:
        result["error"] = type(exc).__name__
        result["message"] = str(exc)[:500]

    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        for key, value in result.items():
            print(f"{key}: {value}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
