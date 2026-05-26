from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


SUPPORTED_MEDIA_EXTENSIONS = {".mp4", ".mp3", ".wav", ".m4a"}
VIDEO_EXTENSIONS = {".mp4"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a"}
CYRILLIC_TRANSLIT = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "sch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}


class IngestMeetingError(RuntimeError):
    def __init__(self, message: str, stage: str = "ingest") -> None:
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


def slugify(value: str) -> str:
    lowered = value.strip().lower()
    transliterated = "".join(CYRILLIC_TRANSLIT.get(char, char) for char in lowered)
    slug = re.sub(r"[^a-z0-9]+", "-", transliterated)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug or "meeting"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def media_type_for(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    if suffix in AUDIO_EXTENSIONS:
        return "audio"
    return "other"


def unique_destination(source_file: Path, source_dir: Path) -> Path:
    candidate = source_dir / source_file.name
    if not candidate.exists():
        return candidate

    stem = source_file.stem
    suffix = source_file.suffix
    for index in range(2, 1000):
        candidate = source_dir / f"{stem}-{index}{suffix}"
        if not candidate.exists():
            return candidate
    raise IngestMeetingError("Could not allocate a unique source filename.")


def build_meeting_json(
    *,
    meeting_id: str,
    title: str,
    meeting_date: str,
    original_location: Path,
    copied_media_path: Path,
    media_sha256: str,
    retention_policy: str,
) -> dict[str, Any]:
    timestamp = now_iso()
    relative_media_path = copied_media_path.as_posix()
    return {
        "schema_version": 1,
        "meeting_id": meeting_id,
        "title": title,
        "date": meeting_date,
        "source": {
            "kind": "offline_record",
            "original_location": str(original_location),
            "media_files": [
                {
                    "path": relative_media_path,
                    "media_type": media_type_for(copied_media_path),
                    "sha256": media_sha256,
                }
            ],
            "derived_tracks": ["MIX"],
        },
        "processing_status": "new",
        "participants": [],
        "artifacts": {},
        "classification": {"project_stage": "PRJ-00", "needs_review": True},
        "links": {},
        "retention": {"policy": retention_policy},
        "rag": {
            "index_policy": "structured_artifacts_and_final_transcript",
            "indexed_artifacts": [],
            "no_index_artifacts": [relative_media_path],
        },
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def run(args: argparse.Namespace) -> int:
    root = repo_root()
    schema_path = root / "configs" / "schemas" / "meeting.schema.json"
    meetings_root = Path(args.meetings_root)
    if not meetings_root.is_absolute():
        meetings_root = root / meetings_root
    meetings_root = meetings_root.resolve()

    source_file = Path(args.file).expanduser().resolve()
    if not source_file.exists():
        raise IngestMeetingError(f"Input file does not exist: {source_file}", stage="preflight")
    if not source_file.is_file():
        raise IngestMeetingError(f"Input path is not a file: {source_file}", stage="preflight")
    if source_file.suffix.lower() not in SUPPORTED_MEDIA_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_MEDIA_EXTENSIONS))
        raise IngestMeetingError(
            f"Unsupported media extension '{source_file.suffix}'. Supported: {supported}",
            stage="preflight",
        )

    meeting_date = args.date or date.today().isoformat()
    meeting_id = args.meeting_id or f"{meeting_date}__{slugify(args.title)}"
    meeting_dir = meetings_root / meeting_id
    meeting_path = meeting_dir / "meeting.json"

    if meeting_path.exists() and not args.force:
        raise IngestMeetingError(
            f"Meeting already exists: {meeting_dir}. Use --force to overwrite meeting.json/source copy.",
            stage="preflight",
        )

    source_dir = meeting_dir / "source"
    transcript_dir = meeting_dir / "transcript"
    artifacts_dir = meeting_dir / "artifacts"
    exports_dir = meeting_dir / "exports"
    partials_dir = meeting_dir / "_partials"
    for path in (source_dir, transcript_dir, artifacts_dir, exports_dir, partials_dir):
        path.mkdir(parents=True, exist_ok=True)

    destination = unique_destination(source_file, source_dir)
    if args.force and destination.exists():
        destination.unlink()
    shutil.copy2(source_file, destination)
    media_sha256 = sha256_file(destination)
    relative_destination = destination.relative_to(meeting_dir)

    meeting = build_meeting_json(
        meeting_id=meeting_id,
        title=args.title,
        meeting_date=meeting_date,
        original_location=source_file,
        copied_media_path=relative_destination,
        media_sha256=media_sha256,
        retention_policy=args.retention_policy,
    )

    validate_schema(meeting, schema_path)
    write_json_atomic(meeting_path, meeting)

    print("meeting ingested")
    print(f"meeting_id: {meeting_id}")
    print(f"meeting_dir: {meeting_dir}")
    print(f"source: {meeting_dir / relative_destination}")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a canonical MeetingAgent meeting card from a media file.",
    )
    parser.add_argument("--file", required=True, help="Input mp4/mp3/wav/m4a file.")
    parser.add_argument("--title", required=True, help="Human-readable meeting title.")
    parser.add_argument("--date", help="Meeting date YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--meeting-id", help="Explicit YYYY-MM-DD__slug meeting id.")
    parser.add_argument("--meetings-root", default="meetings", help="Meetings root directory.")
    parser.add_argument(
        "--retention-policy",
        default="default",
        choices=["default", "protected"],
        help="Retention policy for the meeting media.",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing meeting card.")
    return parser.parse_args(argv)


def main() -> int:
    try:
        return run(parse_args(sys.argv[1:]))
    except IngestMeetingError as exc:
        print(f"ERROR[{exc.stage}]: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
