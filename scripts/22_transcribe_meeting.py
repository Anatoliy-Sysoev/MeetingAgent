from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator


STATUS_NEW = "new"
STATUS_PROCESSING = "processing"
STATUS_TRANSCRIBING = "transcribing"
STATUS_TRANSCRIBED = "transcribed"
STATUS_FAILED = "failed"
SUPPORTED_ENGINES = {"faster-whisper", "gigaam", "from-segments"}
DEFAULT_OUTPUT_FORMATS = {"txt", "md", "srt", "vtt", "json", "jsonl"}


class TranscribeMeetingError(RuntimeError):
    def __init__(self, message: str, stage: str = "runtime") -> None:
        super().__init__(message)
        self.stage = stage


class AlreadyTranscribed(RuntimeError):
    pass


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


ROOT = repo_root()
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from meeting_agent.transcription import (  # noqa: E402
    DEFAULT_FASTER_WHISPER_MODEL,
    FasterWhisperConfig,
    GigaAMConfig,
    HotwordsConfigError,
    TranscriptDocument,
    build_transcription_report,
    extract_initial_prompt as extract_glossary_initial_prompt,
    load_hotwords_config,
    normalize_segments,
    transcribe_faster_whisper as run_faster_whisper_backend,
    transcribe_gigaam as run_gigaam_backend,
    write_transcript_exports,
)


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


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


def load_app_config() -> dict[str, Any]:
    config = read_yaml(ROOT / "config.yaml")
    if config:
        return config
    return read_yaml(ROOT / "config.example.yaml")


def transcription_config() -> dict[str, Any]:
    cfg = load_app_config().get("transcription", {})
    return cfg if isinstance(cfg, dict) else {}


def ensure_status_allows_run(meeting: dict[str, Any], force: bool, resume: bool) -> None:
    status = meeting.get("processing_status")
    if status in {STATUS_NEW, STATUS_PROCESSING, STATUS_FAILED, STATUS_TRANSCRIBING}:
        if status in {STATUS_FAILED, STATUS_TRANSCRIBING} and not (force or resume):
            raise TranscribeMeetingError(f"Meeting status is {status}. Use --force or --resume.", stage="preflight")
        return
    if status == STATUS_TRANSCRIBED and not force:
        raise AlreadyTranscribed("Meeting is already transcribed. Use --force to overwrite.")
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


def existing_segments_path(meeting_dir: Path, meeting: dict[str, Any]) -> Path:
    value = meeting.get("artifacts", {}).get("segments")
    if isinstance(value, str) and value:
        path = meeting_dir / value
        if path.exists():
            return path
    return meeting_dir / "transcript" / "segments.jsonl"


def validate_artifact_paths_exist(meeting: dict[str, Any], meeting_dir: Path, artifact_keys: set[str]) -> None:
    artifacts = meeting.get("artifacts", {})
    missing: list[str] = []
    for key in sorted(artifact_keys):
        value = artifacts.get(key)
        if not isinstance(value, str) or not value:
            missing.append(f"{key}=<missing>")
            continue
        path = Path(value)
        if path.is_absolute() or not (meeting_dir / path).exists():
            missing.append(f"{key}={value}")
    if missing:
        raise TranscribeMeetingError(
            "Successful transcription produced missing artifact paths: " + "; ".join(missing),
            stage="artifact_validation",
        )


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


def extract_initial_prompt() -> str:
    return extract_glossary_initial_prompt(ROOT / "docs" / "glossary.md")


def build_faster_whisper_config(args: argparse.Namespace) -> FasterWhisperConfig:
    hotwords_list: list[str] | None = None
    initial_prompt = extract_initial_prompt()

    # Always load the config (cheap, defaults to disabled when file missing).
    # Activation is opt-in via either the --hotwords CLI flag OR enabled: true in config.
    hotwords_cfg_path = getattr(args, "hotwords_config", None)
    try:
        hw = load_hotwords_config(hotwords_cfg_path or None)
    except HotwordsConfigError as exc:
        raise TranscribeMeetingError(str(exc), stage="hotwords_config") from exc

    active = bool(getattr(args, "hotwords", False)) or hw.enabled
    if active and hw.hotwords_list():
        hotwords_list = hw.hotwords_list()
        initial_prompt = None  # hotwords= takes priority over initial_prompt

    return FasterWhisperConfig(
        model=args.model,
        language=args.language,
        compute_type=args.compute_type,
        device=args.device,
        beam_size=args.beam_size,
        vad_filter=args.vad_filter,
        source="MIX",
        initial_prompt=initial_prompt,
        hotwords=hotwords_list,
    )


def transcribe_faster_whisper(media_path: Path, args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    result = run_faster_whisper_backend(media_path, build_faster_whisper_config(args))
    return result.segments, result.metrics


def transcribe_gigaam_with_metrics(media_path: Path, meeting_dir: Path, args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    result = _run_gigaam(media_path, meeting_dir, args)
    return result.segments, result.metrics


def _run_gigaam(media_path: Path, meeting_dir: Path, args: argparse.Namespace):
    return run_gigaam_backend(
        media_path=media_path,
        meeting_dir=meeting_dir,
        repo_root=ROOT,
        config=GigaAMConfig(
            model=args.model,
            language=args.language,
            chunk_seconds=args.chunk_seconds,
            gigaam_root=Path(args.gigaam_root),
            cache_root=Path(args.gigaam_cache_root),
            python_exe=sys.executable,
            source="MIX",
            resume=args.resume,
        ),
    )


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


def required_artifact_keys_for_formats(output_formats: set[str]) -> set[str]:
    keys = {"segments", "transcription_report"}
    format_to_artifact = {
        "md": "transcript",
        "txt": "transcript_txt",
        "json": "transcript_json",
        "srt": "transcript_srt",
        "vtt": "transcript_vtt",
    }
    for fmt, artifact_key in format_to_artifact.items():
        if fmt in output_formats:
            keys.add(artifact_key)
    return keys


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
        if args.engine == "from-segments" and not args.segments_path and not args.resume:
            raise TranscribeMeetingError("--engine from-segments requires --segments-path.", stage="preflight")
        if not meeting_path.exists():
            raise TranscribeMeetingError(f"meeting.json not found: {meeting_path}", stage="preflight")

        meeting = read_json(meeting_path)
        validate_schema(meeting, schema_path)
        try:
            ensure_status_allows_run(meeting, args.force, args.resume)
        except AlreadyTranscribed as exc:
            print(str(exc))
            return 0

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
            if args.engine == "faster-whisper":
                print(f"model: {args.model}")
                print(f"language: {args.language}")
                print(f"compute_type: {args.compute_type}")
                print(f"device: {args.device}")
                print(f"beam_size: {args.beam_size}")
                print(f"vad_filter: {args.vad_filter}")
                if args.check_model:
                    from meeting_agent.transcription.faster_whisper_backend import load_model

                    load_model(build_faster_whisper_config(args))
                    print("model_load: ok")
            return 0

        mutate_on_error = True
        meeting["processing_status"] = STATUS_TRANSCRIBING
        meeting["updated_at"] = now_iso()
        meeting.pop("last_error", None)
        write_json_atomic(meeting_path, meeting)

        resume_segments_path = existing_segments_path(meeting_dir, meeting)
        if args.resume and resume_segments_path.exists():
            raw_segments = read_jsonl(resume_segments_path)
            model = f"gigaam/{args.model}" if args.engine == "gigaam" else (args.model or None)
            backend_metrics: dict[str, Any] = {
                "asr_engine": args.engine,
                "resume": True,
                "input_segments": str(resume_segments_path),
                "input_rows": len(raw_segments),
            }
        elif args.engine == "from-segments":
            external_segments_path = resolve_path(args.segments_path)
            raw_segments = read_jsonl(external_segments_path)
            model = args.model or None
            backend_metrics = {
                "asr_engine": "from-segments",
                "resume": False,
                "input_segments": str(external_segments_path),
                "input_rows": len(raw_segments),
            }
        elif args.engine == "faster-whisper":
            raw_segments, backend_metrics = transcribe_faster_whisper(media_path, args)  # type: ignore[arg-type]
            model = args.model
        else:
            raw_segments, backend_metrics = transcribe_gigaam_with_metrics(media_path, meeting_dir, args)  # type: ignore[arg-type]
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
            metadata={
                "generated_at": now_iso(),
                "source_file": meeting.get("source_file"),
                "source_audio": meeting.get("artifacts", {}).get("audio_wav"),
                "output_formats": sorted(output_formats),
            },
        )
        transcript_dir = meeting_dir / "transcript"
        written = write_transcript_exports(transcript_dir, document, formats=output_formats)

        report = build_transcription_report(
            normalization,
            engine=args.engine,
            model=model,
            language=args.language,
            duration_seconds=backend_metrics.get("duration") if isinstance(backend_metrics.get("duration"), (int, float)) else None,
            started_at=started_at,
            finished_at=now_iso(),
            elapsed_seconds=round(time.time() - start_time, 3),
            backend_metrics=backend_metrics,
        )
        report_path = transcript_dir / "transcription_report.json"
        report_path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        update_meeting_artifacts(meeting, meeting_dir, written, report_path)
        validate_artifact_paths_exist(meeting, meeting_dir, required_artifact_keys_for_formats(output_formats))
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
    parser.add_argument("--device", default=None)
    parser.add_argument("--beam-size", default=None, type=int)
    parser.add_argument("--vad-filter", dest="vad_filter", action="store_true", default=None)
    parser.add_argument("--no-vad-filter", dest="vad_filter", action="store_false")
    parser.add_argument("--check-model", action="store_true", help="Load faster-whisper model during --dry-run.")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output-formats", default="txt,md,srt,vtt,json,jsonl")
    parser.add_argument("--chunk-seconds", default=24, type=int, help="GigaAM chunk size.")
    parser.add_argument("--gigaam-root", default=str(Path.home() / "GigaAM"))
    parser.add_argument("--gigaam-cache-root", default=str(Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "gigaam_cache"))
    parser.add_argument(
        "--hotwords",
        action="store_true",
        default=False,
        help="Enable custom vocabulary from configs/asr_hotwords.yaml (faster-whisper only).",
    )
    parser.add_argument(
        "--hotwords-config",
        default=None,
        help="Path to custom hotwords YAML (default: configs/asr_hotwords.yaml).",
    )
    args = parser.parse_args(argv)
    cfg = transcription_config()
    if args.engine == "faster-whisper" and not args.model:
        args.model = str(cfg.get("model") or DEFAULT_FASTER_WHISPER_MODEL)
    if args.engine == "gigaam" and not args.model:
        args.model = "v3_e2e_rnnt"
    if args.engine == "faster-whisper":
        if args.language == "ru" and cfg.get("language"):
            args.language = str(cfg.get("language") or args.language)
        if args.compute_type == "int8" and cfg.get("compute_type"):
            args.compute_type = str(cfg.get("compute_type") or args.compute_type)
        args.device = str(args.device or cfg.get("device") or "cpu")
        args.beam_size = int(args.beam_size if args.beam_size is not None else cfg.get("beam_size", 5))
        args.vad_filter = bool(args.vad_filter if args.vad_filter is not None else cfg.get("vad_filter", True))
    else:
        args.device = str(args.device or "cpu")
        args.beam_size = int(args.beam_size if args.beam_size is not None else 5)
        args.vad_filter = bool(args.vad_filter if args.vad_filter is not None else True)
    return args


def main() -> int:
    return run(parse_args(sys.argv[1:]))


def main_with_argv(argv: list[str]) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
