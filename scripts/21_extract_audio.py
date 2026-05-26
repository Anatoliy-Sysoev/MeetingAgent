from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


OUTPUT_AUDIO = "source/audio_16k_mono.wav"


class ExtractAudioError(RuntimeError):
    def __init__(self, message: str, stage: str = "audio_extraction") -> None:
        super().__init__(message)
        self.stage = stage


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


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


def mark_failed(meeting_path: Path, meeting: dict[str, Any], exc: BaseException, stage: str) -> None:
    meeting["processing_status"] = "failed"
    meeting["updated_at"] = now_iso()
    meeting["last_error"] = {
        "stage": stage,
        "message": str(exc),
        "type": type(exc).__name__,
        "timestamp": now_iso(),
    }
    write_json_atomic(meeting_path, meeting)


def resolve_meeting_dir(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def ensure_ffmpeg() -> None:
    if not shutil.which("ffmpeg"):
        raise ExtractAudioError(
            "ffmpeg was not found in PATH. Install ffmpeg or add it to PATH.",
            stage="preflight",
        )


def choose_input_media(meeting_dir: Path, meeting: dict[str, Any]) -> Path:
    media_files = meeting.get("source", {}).get("media_files", [])
    if not media_files:
        raise ExtractAudioError("meeting.json has no source.media_files.", stage="preflight")

    for media in media_files:
        path_value = media.get("path")
        if not path_value or path_value == OUTPUT_AUDIO:
            continue
        media_path = meeting_dir / path_value
        if media_path.exists():
            return media_path

    raise ExtractAudioError("No existing input media found under source.media_files.", stage="preflight")


def ffprobe_duration(path: Path) -> float | None:
    if not shutil.which("ffprobe"):
        return None
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nokey=1:noprint_wrappers=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        return None
    try:
        return round(float(result.stdout.strip()), 3)
    except ValueError:
        return None


def extract_audio(input_path: Path, output_path: Path, force: bool) -> float | None:
    if output_path.exists() and not force:
        return ffprobe_duration(output_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip()
        raise ExtractAudioError(message or "ffmpeg failed.", stage="ffmpeg")
    return ffprobe_duration(output_path)


def update_meeting(meeting: dict[str, Any], duration: float | None) -> None:
    media_files = list(meeting.get("source", {}).get("media_files", []))
    audio_entry = {
        "path": OUTPUT_AUDIO,
        "media_type": "audio",
    }
    if duration is not None:
        audio_entry["duration_seconds"] = duration

    updated_files = [item for item in media_files if item.get("path") != OUTPUT_AUDIO]
    updated_files.append(audio_entry)
    meeting.setdefault("source", {})["media_files"] = updated_files
    meeting["source"]["derived_tracks"] = sorted(set(meeting["source"].get("derived_tracks", []) + ["MIX"]))

    no_index = set(meeting.setdefault("rag", {}).get("no_index_artifacts", []))
    no_index.add(OUTPUT_AUDIO)
    meeting["rag"]["no_index_artifacts"] = sorted(no_index)
    meeting["updated_at"] = now_iso()
    meeting.pop("last_error", None)
    if meeting.get("processing_status") == "failed":
        meeting["processing_status"] = "new"


def run(args: argparse.Namespace) -> int:
    root = repo_root()
    schema_path = root / "configs" / "schemas" / "meeting.schema.json"
    meeting_dir = resolve_meeting_dir(args.meeting_dir)
    meeting_path = meeting_dir / "meeting.json"
    if not meeting_path.exists():
        raise ExtractAudioError(f"meeting.json not found: {meeting_path}", stage="preflight")

    ensure_ffmpeg()
    meeting = read_json(meeting_path)
    validate_schema(meeting, schema_path)
    input_path = choose_input_media(meeting_dir, meeting)
    output_path = meeting_dir / OUTPUT_AUDIO

    try:
        duration = extract_audio(input_path, output_path, force=args.force)
        update_meeting(meeting, duration)
        validate_schema(meeting, schema_path)
        write_json_atomic(meeting_path, meeting)
    except Exception as exc:
        mark_failed(meeting_path, meeting, exc, getattr(exc, "stage", "audio_extraction"))
        raise

    print("audio extracted")
    print(f"input: {input_path}")
    print(f"audio: {output_path}")
    if duration is not None:
        print(f"duration_seconds: {duration}")
    print(f"processing_status: {meeting['processing_status']}")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract normalized 16 kHz mono WAV audio for a MeetingAgent meeting card.",
    )
    parser.add_argument("--meeting-dir", required=True, help="Path to meeting folder.")
    parser.add_argument("--force", action="store_true", help="Recreate audio even if it exists.")
    return parser.parse_args(argv)


def main() -> int:
    try:
        return run(parse_args(sys.argv[1:]))
    except ExtractAudioError as exc:
        print(f"ERROR[{exc.stage}]: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR[runtime]: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
