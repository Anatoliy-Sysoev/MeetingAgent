from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


DEFAULT_SPEAKER = "SPEAKER_UNKNOWN"
DEFAULT_SOURCE = "MIX"


class MergeSpeakersError(RuntimeError):
    def __init__(self, message: str, stage: str = "speaker_merge") -> None:
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


def resolve_meeting_dir(value: str) -> Path:
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
                rows.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise MergeSpeakersError(
                    f"Invalid JSONL at {path}:{line_number}: {exc}",
                    stage="read_segments",
                ) from exc
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def format_time(seconds: float) -> str:
    total = max(0, int(seconds))
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


def build_utterances(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    utterances: list[dict[str, Any]] = []
    for index, segment in enumerate(segments, start=1):
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        try:
            start = round(float(segment["start"]), 3)
            end = round(float(segment["end"]), 3)
        except (KeyError, TypeError, ValueError) as exc:
            raise MergeSpeakersError(
                f"Segment {index} must have numeric start/end.",
                stage="validate_segments",
            ) from exc
        if end < start:
            raise MergeSpeakersError(
                f"Segment {index} has end before start.",
                stage="validate_segments",
            )

        utterances.append(
            {
                "utterance_id": f"utt-{len(utterances) + 1:06d}",
                "segment_index": index - 1,
                "speaker": DEFAULT_SPEAKER,
                "speaker_name": DEFAULT_SPEAKER,
                "source": str(segment.get("source") or DEFAULT_SOURCE),
                "start": start,
                "end": end,
                "text": text,
            }
        )
    if not utterances:
        raise MergeSpeakersError("No non-empty transcript segments found.", stage="validate_segments")
    return utterances


def build_text(utterances: list[dict[str, Any]]) -> str:
    lines = ["# Speaker transcript", ""]
    for utterance in utterances:
        lines.append(
            "[{time}] {speaker}: {text}".format(
                time=format_time(float(utterance["start"])),
                speaker=utterance["speaker_name"],
                text=utterance["text"],
            )
        )
    return "\n".join(lines).rstrip() + "\n"


def update_meeting(meeting: dict[str, Any]) -> None:
    artifacts = dict(meeting.get("artifacts", {}))
    artifacts["speaker_transcript"] = "transcript/speaker_transcript.jsonl"
    meeting["artifacts"] = artifacts
    meeting["updated_at"] = now_iso()
    meeting.pop("last_error", None)


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


def run(args: argparse.Namespace) -> int:
    root = repo_root()
    schema_path = root / "configs" / "schemas" / "meeting.schema.json"
    meeting_dir = resolve_meeting_dir(args.meeting_dir)
    meeting_path = meeting_dir / "meeting.json"
    if not meeting_path.exists():
        raise MergeSpeakersError(f"meeting.json not found: {meeting_path}", stage="preflight")

    meeting = read_json(meeting_path)
    validate_schema(meeting, schema_path)
    segments_rel = meeting.get("artifacts", {}).get("segments", "transcript/segments.jsonl")
    segments_path = meeting_dir / segments_rel
    if not segments_path.exists():
        raise MergeSpeakersError(f"segments.jsonl not found: {segments_path}", stage="preflight")

    output_jsonl = meeting_dir / "transcript" / "speaker_transcript.jsonl"
    output_txt = meeting_dir / "transcript" / "speaker_transcript.txt"
    if output_jsonl.exists() and not args.force:
        raise MergeSpeakersError(
            f"Speaker transcript already exists: {output_jsonl}. Use --force to overwrite.",
            stage="preflight",
        )

    try:
        utterances = build_utterances(read_jsonl(segments_path))
        write_jsonl(output_jsonl, utterances)
        output_txt.write_text(build_text(utterances), encoding="utf-8")
        update_meeting(meeting)
        validate_schema(meeting, schema_path)
        write_json_atomic(meeting_path, meeting)
    except Exception as exc:
        mark_failed(meeting_path, meeting, exc, getattr(exc, "stage", "speaker_merge"))
        raise

    print("speaker transcript complete")
    print(f"utterances: {len(utterances)}")
    print(f"jsonl: {output_jsonl}")
    print(f"text: {output_txt}")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a diarization-lite speaker transcript from ASR segments.",
    )
    parser.add_argument("--meeting-dir", required=True, help="Path to meeting folder.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing speaker transcript.")
    return parser.parse_args(argv)


def main() -> int:
    try:
        return run(parse_args(sys.argv[1:]))
    except MergeSpeakersError as exc:
        print(f"ERROR[{exc.stage}]: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR[runtime]: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
