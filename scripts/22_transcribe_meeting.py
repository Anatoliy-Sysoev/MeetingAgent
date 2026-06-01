from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


STATUS_NEW = "new"
STATUS_TRANSCRIBING = "transcribing"
STATUS_TRANSCRIBED = "transcribed"
STATUS_FAILED = "failed"
SUPPORTED_ENGINES = {"faster-whisper", "gigaam", "from-segments"}
DEFAULT_OUTPUT_FORMATS = {"txt", "md", "srt", "vtt", "json", "jsonl"}


class TranscribeMeetingError(RuntimeError):
    def __init__(self, message: str, stage: str = "runtime") -> None:
        super().__init__(message)
        self.stage = stage


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


ROOT = repo_root()
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from meeting_agent.transcription import (  # noqa: E402
    TranscriptDocument,
    build_transcription_report,
    normalize_segments,
    write_transcript_exports,
)


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def validate_schema(data: dict[str, Any], schema_path: Path) -> None:
    schema = read_json(schema_path)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(data)


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


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
                raise TranscribeMeetingError(f"Invalid JSONL at {path}:{line_number}: {exc}", stage="read_segments") from exc
            if not isinstance(row, dict):
                raise TranscribeMeetingError(f"JSONL row must be an object at {path}:{line_number}", stage="read_segments")
            rows.append(row)
    return rows


def load_legacy_transcribe06():
    path = ROOT / "scripts" / "06_transcribe_meeting.py"
    spec = importlib.util.spec_from_file_location("meeting_transcribe_06_compat", path)
    if not spec or not spec.loader:
        raise TranscribeMeetingError(f"Cannot load legacy transcriber: {path}", stage="preflight")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ensure_tool(name: str) -> None:
    if not shutil.which(name):
        raise TranscribeMeetingError(f"{name} was not found in PATH.", stage="preflight")


def choose_media(meeting_dir: Path, meeting: dict[str, Any]) -> Path:
    media_files = meeting.get("source", {}).get("media_files", [])
    if not media_files:
        raise TranscribeMeetingError("meeting.json has no source.media_files.", stage="preflight")

    preferred = ["source/audio_16k_mono.wav"]
    candidates = []
    for media in media_files:
        value = media.get("path")
        if value:
            candidates.append(str(value))
    ordered = preferred + [value for value in candidates if value not in preferred]

    for value in ordered:
        path = Path(value)
        if path.is_absolute():
            raise TranscribeMeetingError("source.media_files paths must be relative to meeting directory.", stage="preflight")
        resolved = meeting_dir / path
        if resolved.exists():
            return resolved

    raise TranscribeMeetingError("No existing media file found in meeting source.media_files.", stage="preflight")


def ensure_status_allows_run(meeting: dict[str, Any], force: bool, resume: bool) -> None:
    status = meeting.get("processing_status")
    if status in {STATUS_NEW, STATUS_FAILED, STATUS_TRANSCRIBING}:
        if status in {STATUS_FAILED, STATUS_TRANSCRIBING} and not (force or resume):
            raise TranscribeMeetingError(f"Meeting status is {status}. Use --force or --resume.", stage="preflight")
        return
    if status == STATUS_TRANSCRIBED and not force:
        raise TranscribeMeetingError("Meeting is already transcribed. Use --force to overwrite.", stage="preflight")
    if status == STATUS_TRANSCRIBED and force:
        return
    raise TranscribeMeetingError(f"Meeting status must allow transcription, got '{status}'.", stage="preflight")


def parse_output_formats(value: str) -> set[str]:
    if not value.strip():
        return set(DEFAULT_OUTPUT_FORMATS)
    formats = {item.strip().lower() for item in value.split(",") if item.strip()}
    allowed = {"txt", "md", "srt", "vtt", "json", "jsonl"}
    unknown = formats - allowed
    if unknown:
        raise TranscribeMeetingError(f"Unsupported output formats: {', '.join(sorted(unknown))}", stage="preflight")
    selected = formats or set(DEFAULT_OUTPUT_FORMATS)
    selected.add("jsonl")
    return selected


def relative_path(meeting_dir: Path, path: Path) -> str:
    return path.resolve().relative_to(meeting_dir.resolve()).as_posix()


def mark_failed(meeting_path: Path, meeting: dict[str, Any] | None, exc: BaseException, stage: str, mutate: bool) -> None:
    if not mutate or meeting is None:
        return
    meeting["processing_status"] = STATUS_FAILED
    meeting["updated_at"] = now_iso()
    meeting["last_error"] = {
        "stage": stage,
        "message": str(exc),
        "type": type(exc).__name__,
        "timestamp": now_iso(),
    }
    write_json_atomic(meeting_path, meeting)


def transcribe_faster_whisper(media_path: Path, args: argparse.Namespace) -> list[dict[str, Any]]:
    legacy = load_legacy_transcribe06()
    initial_prompt = legacy.extract_initial_prompt(ROOT / "docs" / "glossary.md")
    rows = legacy.transcribe(
        media_path=media_path,
        model_name=args.model,
        compute_type=args.compute_type,
        language=args.language,
        initial_prompt=initial_prompt,
    )
    for row in rows:
        row["engine"] = "faster-whisper"
        row["language"] = args.language
    return rows


def run_command(command: list[str], stage: str) -> None:
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip()
        raise TranscribeMeetingError(message or f"Command failed: {' '.join(command)}", stage=stage)


def transcribe_gigaam(media_path: Path, meeting_dir: Path, args: argparse.Namespace) -> list[dict[str, Any]]:
    ensure_tool("ffmpeg")
    work_dir = meeting_dir / "transcript" / "_gigaam"
    chunks_dir = work_dir / f"chunks_{int(args.chunk_seconds)}s"
    wav_path = work_dir / "audio_16k_mono.wav"
    raw_segments_path = work_dir / "segments_gigaam.jsonl"

    if not args.resume or not raw_segments_path.exists():
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
                str(args.chunk_seconds),
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
        run_command(
            [
                sys.executable,
                str(ROOT / "scripts" / "gigaam_transcribe_chunks.py"),
                "--chunks-dir",
                str(chunks_dir),
                "--output-dir",
                str(work_dir),
                "--source-file",
                str(media_path),
                "--gigaam-root",
                str(args.gigaam_root),
                "--cache-root",
                str(args.gigaam_cache_root),
                "--model",
                args.model,
                "--chunk-seconds",
                str(args.chunk_seconds),
            ],
            "gigaam_asr",
        )

    rows = read_jsonl(raw_segments_path)
    for row in rows:
        row["engine"] = "gigaam"
        row["language"] = args.language
        row["source"] = row.get("source") or "MIX"
    return rows


def update_meeting_artifacts(
    meeting: dict[str, Any],
    meeting_dir: Path,
    written: dict[str, Path],
    report_path: Path,
) -> None:
    artifacts = dict(meeting.get("artifacts", {}))
    mapping = {
        "segments": "segments",
        "transcript_md": "transcript",
        "transcript_txt": "transcript_txt",
        "transcript_json": "transcript_json",
        "transcript_srt": "transcript_srt",
        "transcript_vtt": "transcript_vtt",
    }
    for key, artifact_key in mapping.items():
        if key in written:
            artifacts[artifact_key] = relative_path(meeting_dir, written[key])
    artifacts["transcription_report"] = relative_path(meeting_dir, report_path)
    meeting["artifacts"] = artifacts
    meeting["processing_status"] = STATUS_TRANSCRIBED
    meeting["updated_at"] = now_iso()
    meeting.pop("last_error", None)


def run(args: argparse.Namespace) -> int:
    meeting_dir = resolve_path(args.meeting_dir)
    meeting_path = meeting_dir / "meeting.json"
    schema_path = ROOT / "configs" / "schemas" / "meeting.schema.json"
    output_formats = parse_output_formats(args.output_formats)
    meeting: dict[str, Any] | None = None
    mutate_on_error = False
    started_at = now_iso()
    start_time = time.time()

    try:
        if args.engine not in SUPPORTED_ENGINES:
            raise TranscribeMeetingError(f"Unsupported engine: {args.engine}", stage="preflight")
        if args.engine == "from-segments" and not args.segments_path:
            raise TranscribeMeetingError("--engine from-segments requires --segments-path.", stage="preflight")
        if not meeting_path.exists():
            raise TranscribeMeetingError(f"meeting.json not found: {meeting_path}", stage="preflight")

        meeting = read_json(meeting_path)
        validate_schema(meeting, schema_path)
        ensure_status_allows_run(meeting, args.force, args.resume)

        media_path = choose_media(meeting_dir, meeting) if args.engine != "from-segments" else None
        if args.dry_run:
            print("dry-run ok")
            print(f"meeting_dir: {meeting_dir}")
            print(f"engine: {args.engine}")
            if media_path:
                print(f"media: {media_path}")
            if args.segments_path:
                print(f"segments_path: {resolve_path(args.segments_path)}")
            print(f"output_formats: {','.join(sorted(output_formats))}")
            return 0

        mutate_on_error = True
        meeting["processing_status"] = STATUS_TRANSCRIBING
        meeting["updated_at"] = now_iso()
        meeting.pop("last_error", None)
        write_json_atomic(meeting_path, meeting)

        if args.engine == "from-segments":
            raw_segments = read_jsonl(resolve_path(args.segments_path))
            model = args.model or None
        elif args.engine == "faster-whisper":
            raw_segments = transcribe_faster_whisper(media_path, args)  # type: ignore[arg-type]
            model = args.model
        else:
            raw_segments = transcribe_gigaam(media_path, meeting_dir, args)  # type: ignore[arg-type]
            model = f"gigaam/{args.model}"

        normalization = normalize_segments(raw_segments, engine=args.engine, language=args.language)
        if not normalization.segments:
            raise TranscribeMeetingError("No valid non-empty transcript segments produced.", stage="normalize")

        document = TranscriptDocument(
            meeting_id=str(meeting.get("meeting_id", "")),
            title=str(meeting.get("title") or meeting.get("meeting_id") or "meeting"),
            engine=args.engine,
            model=model,
            language=args.language,
            segments=normalization.segments,
        )
        transcript_dir = meeting_dir / "transcript"
        written = write_transcript_exports(transcript_dir, document, formats=output_formats)

        report = build_transcription_report(
            normalization,
            engine=args.engine,
            model=model,
            language=args.language,
            started_at=started_at,
            finished_at=now_iso(),
            elapsed_seconds=round(time.time() - start_time, 3),
        )
        report_path = transcript_dir / "transcription_report.json"
        report_path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        update_meeting_artifacts(meeting, meeting_dir, written, report_path)
        validate_schema(meeting, schema_path)
        write_json_atomic(meeting_path, meeting)

        print("transcription complete")
        print(f"engine: {args.engine}")
        print(f"segments: {len(normalization.segments)}")
        print(f"report: {report_path}")
        return 0
    except TranscribeMeetingError as exc:
        mark_failed(meeting_path, meeting, exc, exc.stage, mutate_on_error)
        print(f"ERROR[{exc.stage}]: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        mark_failed(meeting_path, meeting, exc, "runtime", mutate_on_error)
        print(f"ERROR[runtime]: {exc}", file=sys.stderr)
        return 1


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Canonical MeetingAgent transcription entrypoint.")
    parser.add_argument("--meeting-dir", required=True, help="Path to meeting folder.")
    parser.add_argument("--engine", required=True, choices=sorted(SUPPORTED_ENGINES))
    parser.add_argument("--segments-path", help="Input JSONL for --engine from-segments.")
    parser.add_argument("--model", default=None, help="ASR model name. Defaults depend on engine.")
    parser.add_argument("--language", default="ru")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output-formats", default="txt,md,srt,vtt,json,jsonl")
    parser.add_argument("--chunk-seconds", default=24, type=int, help="GigaAM chunk size.")
    parser.add_argument("--gigaam-root", default=str(Path.home() / "GigaAM"))
    parser.add_argument("--gigaam-cache-root", default=str(Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "gigaam_cache"))
    args = parser.parse_args(argv)
    if args.engine == "faster-whisper" and not args.model:
        args.model = "small"
    if args.engine == "gigaam" and not args.model:
        args.model = "v3_e2e_rnnt"
    return args


def main() -> int:
    return run(parse_args(sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
