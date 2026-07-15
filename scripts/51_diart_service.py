from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


_MEETING_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")
_MAX_REQUEST_BYTES = 4 * 1024
_MAX_TURNS = 20_000


class DiartServiceError(RuntimeError):
    pass


def _safe_audio_path(meetings_root: Path, meeting_id: str, source: str) -> Path:
    if not _MEETING_ID_RE.fullmatch(meeting_id):
        raise DiartServiceError("invalid_meeting_id")
    if source != "SYS":
        raise DiartServiceError("unsupported_source")
    root = meetings_root.resolve(strict=True)
    meeting_dir = root / meeting_id
    candidate = meeting_dir / "source" / "live_audio.SYS.wav"
    if meeting_dir.is_symlink() or candidate.is_symlink():
        raise DiartServiceError("audio_unavailable")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise DiartServiceError("audio_unavailable") from exc
    if not resolved.is_file():
        raise DiartServiceError("audio_unavailable")
    return resolved


def _normalize_tracks(tracks: list[tuple[Any, Any, Any]]) -> list[dict[str, Any]]:
    bounded: list[tuple[float, float, str]] = []
    for segment, _track, raw_label in tracks[:_MAX_TURNS]:
        start = float(segment.start)
        end = float(segment.end)
        if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
            continue
        bounded.append((start, end, str(raw_label)))
    bounded.sort(key=lambda item: (item[0], item[1], item[2]))
    labels: dict[str, str] = {}
    rows: list[dict[str, Any]] = []
    for start, end, raw_label in bounded:
        speaker = labels.setdefault(raw_label, f"SPEAKER_{len(labels):02d}")
        if rows and rows[-1]["speaker"] == speaker and start <= rows[-1]["end"] + 0.05:
            rows[-1]["end"] = round(max(float(rows[-1]["end"]), end), 3)
            continue
        rows.append(
            {
                "speaker": speaker,
                "start": round(start, 3),
                "end": round(end, 3),
            }
        )
    return rows[:_MAX_TURNS]


class DiartRuntime:
    def __init__(self, segmentation_name: str, embedding_name: str) -> None:
        import torch
        from diart.models import EmbeddingModel, SegmentationModel

        token = os.getenv("HF_TOKEN", "").strip()
        if not token:
            raise DiartServiceError("hf_token_missing")
        self.segmentation_name = segmentation_name
        self.embedding_name = embedding_name
        self.segmentation = SegmentationModel.from_pretrained(
            segmentation_name,
            use_hf_token=token,
        )
        self.embedding = EmbeddingModel.from_pretrained(
            embedding_name,
            use_hf_token=token,
        )
        self.segmentation.to(torch.device("cpu")).eval()
        self.embedding.to(torch.device("cpu")).eval()
        self._lock = threading.Lock()

    def diarize(self, audio_path: Path) -> tuple[list[dict[str, Any]], float]:
        from diart import SpeakerDiarization, SpeakerDiarizationConfig
        from diart.inference import StreamingInference
        from diart.sources import FileAudioSource

        started = time.monotonic()
        with self._lock:
            config = SpeakerDiarizationConfig(
                segmentation=self.segmentation,
                embedding=self.embedding,
                duration=5.0,
                step=0.5,
                latency=3.0,
            )
            pipeline = SpeakerDiarization(config)
            padding = pipeline.config.get_file_padding(audio_path)
            source = FileAudioSource(
                audio_path,
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
        return _normalize_tracks(tracks), round(time.monotonic() - started, 3)


class DiartRequestHandler(BaseHTTPRequestHandler):
    server_version = "MeetingAgentDiart/1"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/health":
            self._json(404, {"ok": False, "error": "not_found"})
            return
        self._json(200, {"ok": True, "runtime": "diart-isolated-cpu"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/diarize":
            self._json(404, {"ok": False, "error": "not_found"})
            return
        try:
            raw_length = self.headers.get("Content-Length", "")
            length = int(raw_length)
            if not 1 <= length <= _MAX_REQUEST_BYTES:
                raise DiartServiceError("invalid_request")
            raw = self.rfile.read(length)
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict):
                raise DiartServiceError("invalid_request")
            meeting_id = str(payload.get("meeting_id") or "")
            source = str(payload.get("source") or "").upper()
            audio_path = _safe_audio_path(self.server.meetings_root, meeting_id, source)
            turns, elapsed = self.server.runtime.diarize(audio_path)
            self._json(
                200,
                {
                    "ok": True,
                    "engine": "diart",
                    "source": source,
                    "turns": turns,
                    "turns_count": len(turns),
                    "elapsed_seconds": elapsed,
                },
            )
        except (DiartServiceError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            self._json(422, {"ok": False, "error": "invalid_request"})
        except Exception:
            self._json(503, {"ok": False, "error": "diarization_failed"})


class DiartHttpServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], runtime: DiartRuntime, meetings_root: Path):
        self.runtime = runtime
        self.meetings_root = meetings_root
        super().__init__(address, DiartRequestHandler)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MeetingAgent localhost Diart sidecar")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--meetings-root", type=Path, default=Path("/meetings"))
    parser.add_argument("--segmentation", default="pyannote/segmentation-3.0")
    parser.add_argument("--embedding", default="pyannote/embedding")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not 1 <= args.port <= 65_535:
        raise SystemExit("invalid port")
    runtime = DiartRuntime(args.segmentation, args.embedding)
    server = DiartHttpServer((args.host, args.port), runtime, args.meetings_root)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
