from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


STATUS_NEW = "new"
STATUS_TRANSCRIBING = "transcribing"
STATUS_TRANSCRIBED = "transcribed"
STATUS_FAILED = "failed"


@dataclass(frozen=True)
class TranscribeContext:
    repo_root: Path
    meeting_dir: Path
    meeting_path: Path
    schema_path: Path
    glossary_path: Path


class MeetingTranscribeError(RuntimeError):
    def __init__(self, message: str, stage: str = "runtime") -> None:
        super().__init__(message)
        self.stage = stage


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(path)


def validate_schema(data: dict[str, Any], schema_path: Path) -> None:
    schema = read_json(schema_path)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(data)


def resolve_context(meeting_dir_arg: str) -> TranscribeContext:
    script_path = Path(__file__).resolve()
    repo_root = script_path.parents[1]
    meeting_dir = Path(meeting_dir_arg).expanduser()
    if not meeting_dir.is_absolute():
        meeting_dir = (Path.cwd() / meeting_dir).resolve()
    else:
        meeting_dir = meeting_dir.resolve()

    return TranscribeContext(
        repo_root=repo_root,
        meeting_dir=meeting_dir,
        meeting_path=meeting_dir / "meeting.json",
        schema_path=repo_root / "configs" / "schemas" / "meeting.schema.json",
        glossary_path=repo_root / "docs" / "glossary.md",
    )


def ensure_status_allows_run(meeting: dict[str, Any], force: bool) -> None:
    status = meeting.get("processing_status")
    if status == STATUS_NEW:
        return
    if force and status in {STATUS_TRANSCRIBED, STATUS_FAILED, STATUS_TRANSCRIBING}:
        return
    if status == STATUS_TRANSCRIBED:
        raise MeetingTranscribeError(
            "Meeting is already transcribed. Use --force to overwrite transcript.",
            stage="preflight",
        )
    if status in {STATUS_FAILED, STATUS_TRANSCRIBING}:
        raise MeetingTranscribeError(
            f"Meeting status is {status}. Use --force to retry.",
            stage="preflight",
        )
    raise MeetingTranscribeError(
        f"Meeting status must be 'new' before transcription, got '{status}'.",
        stage="preflight",
    )


def ensure_ffmpeg() -> None:
    if not shutil.which("ffmpeg"):
        raise MeetingTranscribeError(
            "ffmpeg was not found in PATH. Install ffmpeg or add it to PATH.",
            stage="preflight",
        )


def get_source_media(ctx: TranscribeContext, meeting: dict[str, Any]) -> Path:
    media_files = meeting.get("source", {}).get("media_files", [])
    if not media_files:
        raise MeetingTranscribeError(
            "meeting.json has no source.media_files entries.",
            stage="preflight",
        )

    media_path_value = media_files[0].get("path")
    if not media_path_value:
        raise MeetingTranscribeError(
            "First source.media_files entry has no path.",
            stage="preflight",
        )

    media_path = Path(media_path_value)
    if media_path.is_absolute():
        raise MeetingTranscribeError(
            "source.media_files[0].path must be relative to meeting directory.",
            stage="preflight",
        )

    resolved = (ctx.meeting_dir / media_path).resolve()
    source_root = (ctx.meeting_dir / "source").resolve()
    if source_root not in resolved.parents and resolved != source_root:
        raise MeetingTranscribeError(
            "source media must be located under meeting source/ directory.",
            stage="preflight",
        )
    if not resolved.exists():
        raise MeetingTranscribeError(
            f"Source media file does not exist: {resolved}",
            stage="preflight",
        )
    return resolved


def extract_initial_prompt(glossary_path: Path) -> str:
    text = glossary_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    in_terms = False
    terms: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped == "## Проектные Термины":
            in_terms = True
            continue
        if in_terms and stripped.startswith("## "):
            break
        if not in_terms or not stripped.startswith("|"):
            continue
        if stripped.startswith("| ---") or stripped.startswith("| Термин"):
            continue
        cells = [cell.strip(" `") for cell in stripped.strip("|").split("|")]
        if len(cells) >= 2 and cells[0]:
            terms.append(f"{cells[0]}: {cells[1]}")

    if not terms:
        return ""
    return "Встреча по проекту АСУ. Возможные термины: " + "; ".join(terms)


def format_time(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def build_markdown_transcript(
    meeting: dict[str, Any],
    segments: list[dict[str, Any]],
    model_name: str,
    compute_type: str,
    language: str,
) -> str:
    meeting_id = meeting.get("meeting_id", "")
    title = meeting.get("title", meeting_id)
    date = meeting.get("date", "")

    out: list[str] = [
        f"# Транскрипт: {title}",
        "",
        f"- meeting_id: `{meeting_id}`",
        f"- Дата: {date}",
        f"- Модель: `{model_name}`",
        f"- compute_type: `{compute_type}`",
        f"- language: `{language}`",
        "",
    ]

    current_start: float | None = None
    current_end: float | None = None
    current_text: list[str] = []

    def flush() -> None:
        nonlocal current_start, current_end, current_text
        if current_start is None or not current_text:
            return
        paragraph = " ".join(part.strip() for part in current_text if part.strip())
        if paragraph:
            out.append(f"[{format_time(current_start)}] {paragraph}")
            out.append("")
        current_start = None
        current_end = None
        current_text = []

    for segment in segments:
        start = float(segment["start"])
        end = float(segment["end"])
        text = str(segment["text"]).strip()
        if not text:
            continue

        if current_start is None:
            current_start = start
        elif current_end is not None:
            pause = start - current_end
            paragraph_duration = start - current_start
            if pause > 2 or paragraph_duration >= 30:
                flush()
                current_start = start

        current_text.append(text)
        current_end = end

    flush()
    return "\n".join(out).rstrip() + "\n"


def write_segments_jsonl(path: Path, segments: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for segment in segments:
            fh.write(json.dumps(segment, ensure_ascii=False) + "\n")


def mark_failed(
    ctx: TranscribeContext,
    meeting: dict[str, Any] | None,
    exc: BaseException,
    stage: str,
    mutate: bool,
) -> None:
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
    try:
        write_json_atomic(ctx.meeting_path, meeting)
    except Exception:
        # Avoid masking the original error.
        pass


def load_model(model_name: str, compute_type: str):
    from faster_whisper import WhisperModel

    return WhisperModel(model_name, device="cpu", compute_type=compute_type)


def transcribe(
    media_path: Path,
    model_name: str,
    compute_type: str,
    language: str,
    initial_prompt: str,
) -> list[dict[str, Any]]:
    model = load_model(model_name, compute_type)
    segment_iter, _info = model.transcribe(
        str(media_path),
        language=language,
        initial_prompt=initial_prompt or None,
        vad_filter=False,
        beam_size=3,
    )

    segments: list[dict[str, Any]] = []
    for segment in segment_iter:
        segments.append(
            {
                "start": round(float(segment.start), 3),
                "end": round(float(segment.end), 3),
                "text": segment.text.strip(),
                "source": "MIX",
            }
        )
    return segments


def validate_transcribed_status(ctx: TranscribeContext, meeting: dict[str, Any]) -> None:
    if meeting.get("processing_status") != STATUS_TRANSCRIBED:
        return
    artifacts = meeting.get("artifacts", {})
    for key in ("transcript", "segments"):
        value = artifacts.get(key)
        if not value:
            raise MeetingTranscribeError(
                f"Status 'transcribed' requires artifacts.{key}.",
                stage="status_rule",
            )
        path = ctx.meeting_dir / value
        if not path.exists():
            raise MeetingTranscribeError(
                f"Status 'transcribed' requires existing file: {path}",
                stage="status_rule",
            )


def run(args: argparse.Namespace) -> int:
    ctx = resolve_context(args.meeting_dir)
    meeting: dict[str, Any] | None = None
    mutate_on_error = False

    try:
        if not ctx.meeting_path.exists():
            raise MeetingTranscribeError(
                f"meeting.json not found: {ctx.meeting_path}",
                stage="preflight",
            )

        meeting = read_json(ctx.meeting_path)
        validate_schema(meeting, ctx.schema_path)
        ensure_status_allows_run(meeting, args.force)
        ensure_ffmpeg()
        media_path = get_source_media(ctx, meeting)
        initial_prompt = extract_initial_prompt(ctx.glossary_path)

        if args.dry_run:
            # Model load is part of dry-run: it catches missing dependencies and
            # unavailable faster-whisper models before a long transcription starts.
            load_model(args.model, args.compute_type)
            print("dry-run ok")
            print(f"meeting_dir: {ctx.meeting_dir}")
            print(f"media: {media_path}")
            print(f"model: {args.model}")
            print(f"compute_type: {args.compute_type}")
            print(f"language: {args.language}")
            return 0

        mutate_on_error = True
        meeting["processing_status"] = STATUS_TRANSCRIBING
        meeting["updated_at"] = now_iso()
        meeting.pop("last_error", None)
        write_json_atomic(ctx.meeting_path, meeting)
        validate_schema(meeting, ctx.schema_path)

        segments = transcribe(
            media_path=media_path,
            model_name=args.model,
            compute_type=args.compute_type,
            language=args.language,
            initial_prompt=initial_prompt,
        )

        transcript_dir = ctx.meeting_dir / "transcript"
        transcript_path = transcript_dir / "transcript.md"
        segments_path = transcript_dir / "segments.jsonl"
        write_segments_jsonl(segments_path, segments)
        transcript_path.write_text(
            build_markdown_transcript(
                meeting=meeting,
                segments=segments,
                model_name=args.model,
                compute_type=args.compute_type,
                language=args.language,
            ),
            encoding="utf-8",
        )

        artifacts = dict(meeting.get("artifacts", {}))
        artifacts["transcript"] = "transcript/transcript.md"
        artifacts["segments"] = "transcript/segments.jsonl"
        meeting["artifacts"] = artifacts
        meeting["processing_status"] = STATUS_TRANSCRIBED
        meeting["updated_at"] = now_iso()
        meeting.pop("last_error", None)

        validate_schema(meeting, ctx.schema_path)
        validate_transcribed_status(ctx, meeting)
        write_json_atomic(ctx.meeting_path, meeting)

        print("transcription complete")
        print(f"segments: {len(segments)}")
        print(f"transcript: {transcript_path}")
        return 0
    except MeetingTranscribeError as exc:
        mark_failed(ctx, meeting, exc, exc.stage, mutate_on_error)
        print(f"ERROR[{exc.stage}]: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        mark_failed(ctx, meeting, exc, "runtime", mutate_on_error)
        print(f"ERROR[runtime]: {exc}", file=sys.stderr)
        return 1


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Offline transcription for one MeetingAgent meeting folder.",
    )
    parser.add_argument("--meeting-dir", required=True, help="Path to meeting folder.")
    parser.add_argument("--model", default="small", help="faster-whisper model name.")
    parser.add_argument("--compute-type", default="int8", help="CTranslate2 compute type.")
    parser.add_argument("--language", default="ru", help="Audio language.")
    parser.add_argument("--dry-run", action="store_true", help="Validate inputs and model only.")
    parser.add_argument("--force", action="store_true", help="Retry or overwrite existing transcript.")
    return parser.parse_args(argv)


def main() -> int:
    return run(parse_args(sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
