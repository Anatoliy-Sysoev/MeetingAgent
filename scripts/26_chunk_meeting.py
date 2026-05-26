from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


DEFAULT_MAX_SECONDS = 180.0
DEFAULT_MAX_CHARS = 6000


class ChunkMeetingError(RuntimeError):
    def __init__(self, message: str, stage: str = "meeting_chunking") -> None:
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
                raise ChunkMeetingError(
                    f"Invalid JSONL at {path}:{line_number}: {exc}",
                    stage="read_utterances",
                ) from exc
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def validate_utterance(row: dict[str, Any], index: int) -> dict[str, Any]:
    text = str(row.get("text") or "").strip()
    if not text:
        return {}
    try:
        start = round(float(row["start"]), 3)
        end = round(float(row["end"]), 3)
    except (KeyError, TypeError, ValueError) as exc:
        raise ChunkMeetingError(
            f"Utterance {index} must have numeric start/end.",
            stage="validate_utterances",
        ) from exc
    if end < start:
        raise ChunkMeetingError(
            f"Utterance {index} has end before start.",
            stage="validate_utterances",
        )
    return {
        **row,
        "start": start,
        "end": end,
        "text": text,
        "speaker": str(row.get("speaker") or "SPEAKER_UNKNOWN"),
        "source": str(row.get("source") or "MIX"),
        "utterance_id": str(row.get("utterance_id") or f"utt-{index:06d}"),
    }


def chunk_text(utterances: list[dict[str, Any]], meeting_id: str, max_seconds: float, max_chars: int) -> list[dict[str, Any]]:
    normalized = [validate_utterance(row, index) for index, row in enumerate(utterances, start=1)]
    normalized = [row for row in normalized if row]
    if not normalized:
        raise ChunkMeetingError("No non-empty utterances found.", stage="validate_utterances")

    chunks: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []

    def current_chars(rows: list[dict[str, Any]]) -> int:
        return sum(len(str(row["text"])) for row in rows) + max(0, len(rows) - 1)

    def should_flush(next_row: dict[str, Any]) -> bool:
        if not current:
            return False
        start = float(current[0]["start"])
        next_end = float(next_row["end"])
        duration = next_end - start
        chars = current_chars(current) + 1 + len(str(next_row["text"]))
        return duration > max_seconds or chars > max_chars

    def flush() -> None:
        if not current:
            return
        index = len(chunks) + 1
        speakers = sorted({str(row["speaker"]) for row in current})
        sources = sorted({str(row["source"]) for row in current})
        text = "\n".join(
            f"[{row['speaker']}] {row['text']}" for row in current
        ).strip()
        chunks.append(
            {
                "chunk_id": f"{meeting_id}-chunk-{index:04d}",
                "meeting_id": meeting_id,
                "source_type": "meeting_chunk",
                "start": float(current[0]["start"]),
                "end": float(current[-1]["end"]),
                "speakers": speakers,
                "sources": sources,
                "text": text,
                "utterance_ids": [str(row["utterance_id"]) for row in current],
            }
        )
        current.clear()

    for utterance in normalized:
        if should_flush(utterance):
            flush()
        current.append(utterance)
    flush()
    return chunks


def update_meeting(meeting: dict[str, Any]) -> None:
    artifacts = dict(meeting.get("artifacts", {}))
    artifacts["chunks"] = "transcript/chunks.jsonl"
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
        raise ChunkMeetingError(f"meeting.json not found: {meeting_path}", stage="preflight")

    meeting = read_json(meeting_path)
    validate_schema(meeting, schema_path)
    speaker_rel = meeting.get("artifacts", {}).get(
        "speaker_transcript",
        "transcript/speaker_transcript.jsonl",
    )
    speaker_path = meeting_dir / speaker_rel
    if not speaker_path.exists():
        raise ChunkMeetingError(
            f"speaker_transcript.jsonl not found: {speaker_path}",
            stage="preflight",
        )

    output_path = meeting_dir / "transcript" / "chunks.jsonl"
    if output_path.exists() and not args.force:
        raise ChunkMeetingError(
            f"Meeting chunks already exist: {output_path}. Use --force to overwrite.",
            stage="preflight",
        )

    try:
        chunks = chunk_text(
            utterances=read_jsonl(speaker_path),
            meeting_id=str(meeting["meeting_id"]),
            max_seconds=args.max_seconds,
            max_chars=args.max_chars,
        )
        write_jsonl(output_path, chunks)
        update_meeting(meeting)
        validate_schema(meeting, schema_path)
        write_json_atomic(meeting_path, meeting)
    except Exception as exc:
        mark_failed(meeting_path, meeting, exc, getattr(exc, "stage", "meeting_chunking"))
        raise

    print("meeting chunks complete")
    print(f"chunks: {len(chunks)}")
    print(f"jsonl: {output_path}")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build meeting-aware chunks from speaker transcript utterances.",
    )
    parser.add_argument("--meeting-dir", required=True, help="Path to meeting folder.")
    parser.add_argument("--max-seconds", default=DEFAULT_MAX_SECONDS, type=float)
    parser.add_argument("--max-chars", default=DEFAULT_MAX_CHARS, type=int)
    parser.add_argument("--force", action="store_true", help="Overwrite existing chunks.")
    return parser.parse_args(argv)


def main() -> int:
    try:
        return run(parse_args(sys.argv[1:]))
    except ChunkMeetingError as exc:
        print(f"ERROR[{exc.stage}]: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR[runtime]: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
