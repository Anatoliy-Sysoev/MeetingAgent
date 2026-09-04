from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from meeting_agent.jobs.progress import ProgressReporter


@dataclass(frozen=True)
class GigaAMConfig:
    model: str = "v3_e2e_rnnt"
    language: str = "ru"
    chunk_seconds: int = 24
    gigaam_root: Path = field(default_factory=lambda: Path.home() / "GigaAM")
    cache_root: Path = field(default_factory=lambda: Path(r"C:\ProgramData") / "gigaam_cache")
    python_exe: str = sys.executable
    source: str = "MIX"
    resume: bool = False


@dataclass(frozen=True)
class GigaAMResult:
    segments: list[dict[str, Any]]
    metrics: dict[str, Any]
    work_dir: Path
    raw_segments_path: Path


class GigaAMBackendError(RuntimeError):
    def __init__(self, message: str, stage: str = "gigaam") -> None:
        super().__init__(message)
        self.stage = stage


def ensure_tool(name: str) -> None:
    if not shutil.which(name):
        raise GigaAMBackendError(f"{name} was not found in PATH.", stage="preflight")


def run_command(command: list[str], stage: str) -> None:
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip()
        raise GigaAMBackendError(message or f"Command failed: {' '.join(command)}", stage=stage)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_number, line in enumerate(fh, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise GigaAMBackendError(f"Invalid JSONL at {path}:{line_number}: {exc}", stage="read_segments") from exc
            if not isinstance(row, dict):
                raise GigaAMBackendError(f"JSONL row must be an object at {path}:{line_number}", stage="read_segments")
            rows.append(row)
    return rows


def prepare_audio_and_chunks(media_path: Path, work_dir: Path, config: GigaAMConfig) -> tuple[Path, Path]:
    ensure_tool("ffmpeg")
    chunks_dir = work_dir / f"chunks_{int(config.chunk_seconds)}s"
    wav_path = work_dir / "audio_16k_mono.wav"
    work_dir.mkdir(parents=True, exist_ok=True)
    chunks_dir.mkdir(parents=True, exist_ok=True)

    run_command(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(media_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(wav_path),
        ],
        "gigaam_audio",
    )
    run_command(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(wav_path),
            "-f",
            "segment",
            "-segment_time",
            str(config.chunk_seconds),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(chunks_dir / "chunk_%04d.wav"),
        ],
        "gigaam_chunks",
    )
    return wav_path, chunks_dir


def normalize_gigaam_rows(rows: list[dict[str, Any]], config: GigaAMConfig) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        normalized.append(
            {
                **row,
                "engine": "gigaam",
                "language": config.language,
                "source": config.source,
            }
        )
    return normalized


def transcribe_gigaam(
    *,
    media_path: Path,
    meeting_dir: Path,
    repo_root: Path,
    config: GigaAMConfig,
    progress_path: Path | None = None,
) -> GigaAMResult:
    work_dir = meeting_dir / "transcript" / "_gigaam"
    raw_segments_path = work_dir / "raw_segments.jsonl"
    legacy_segments_path = work_dir / "segments_gigaam.jsonl"

    if not config.resume or not raw_segments_path.exists():
        _wav_path, chunks_dir = prepare_audio_and_chunks(media_path, work_dir, config)
        worker_command = [
                config.python_exe,
                str(repo_root / "scripts" / "gigaam_transcribe_chunks.py"),
                "--chunks-dir",
                str(chunks_dir),
                "--output-dir",
                str(work_dir),
                "--source-file",
                str(media_path),
                "--gigaam-root",
                str(config.gigaam_root),
                "--cache-root",
                str(config.cache_root),
                "--model",
                config.model,
                "--chunk-seconds",
                str(config.chunk_seconds),
            ]
        if progress_path is not None:
            worker_command.extend(["--progress-path", str(progress_path)])
        run_command(worker_command, "gigaam_asr")
        if not legacy_segments_path.exists():
            raise GigaAMBackendError(f"GigaAM worker did not create {legacy_segments_path}", stage="gigaam_asr")
        legacy_segments_path.replace(raw_segments_path)

    rows = read_jsonl(raw_segments_path)
    if progress_path is not None:
        ProgressReporter(
            progress_path,
            phase="transcribe:gigaam",
            unit="chunks",
        ).emit_safely(len(rows), len(rows) or None, force=True)
    errors = sum(1 for row in rows if row.get("error"))
    nonempty = sum(1 for row in rows if str(row.get("text") or "").strip())
    metrics = {
        "asr_engine": "gigaam",
        "asr_model": f"gigaam/{config.model}",
        "chunk_seconds": config.chunk_seconds,
        "chunks": len(rows),
        "nonempty_chunks": nonempty,
        "chunk_errors": errors,
        "cache_root": str(config.cache_root),
        "gigaam_root": str(config.gigaam_root),
        "raw_segments": str(raw_segments_path),
    }
    return GigaAMResult(
        segments=normalize_gigaam_rows(rows, config),
        metrics=metrics,
        work_dir=work_dir,
        raw_segments_path=raw_segments_path,
    )
