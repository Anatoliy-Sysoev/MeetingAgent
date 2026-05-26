from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


DEFAULT_OUTPUT = "data/meeting_chunks.jsonl"


class IndexMeetingError(RuntimeError):
    def __init__(self, message: str, stage: str = "meeting_indexing") -> None:
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
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if stripped:
                rows.append(json.loads(stripped))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def stable_id(value: str, length: int = 24) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def format_time(seconds: float) -> str:
    total = max(0, int(seconds))
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


def indexed_text(meeting: dict[str, Any], chunk: dict[str, Any]) -> str:
    parts = [
        f"Встреча: {meeting.get('title')}",
        f"Дата: {meeting.get('date')}",
        f"Таймкод: {format_time(float(chunk.get('start') or 0))} - {format_time(float(chunk.get('end') or 0))}",
        f"Тема: {chunk.get('topic') or ''}",
        f"Тип: {chunk.get('semantic_type') or 'discussion'}",
        f"Спикеры: {', '.join(str(item) for item in (chunk.get('speakers') or []))}",
        "",
        str(chunk.get("text") or ""),
    ]
    return "\n".join(parts).strip()


def to_index_chunk(meeting_dir: Path, meeting: dict[str, Any], chunk: dict[str, Any], index: int) -> dict[str, Any]:
    meeting_id = str(meeting["meeting_id"])
    chunk_id = str(chunk.get("chunk_id") or f"{meeting_id}-chunk-{index:04d}")
    relative_path = f"meetings/{meeting_id}/transcript/chunks.jsonl"
    start = float(chunk.get("start") or 0)
    end = float(chunk.get("end") or start)
    text = indexed_text(meeting, chunk)
    return {
        "chunk_id": chunk_id,
        "db_id": stable_id(f"meeting:{meeting_id}:{chunk_id}", length=32),
        "text": text,
        "source_type": "meeting_chunk",
        "document_type": "Протокол",
        "relative_path": relative_path,
        "source_path": str(meeting_dir / "transcript" / "chunks.jsonl"),
        "extension": ".jsonl",
        "meeting_id": meeting_id,
        "meeting_title": meeting.get("title"),
        "meeting_date": meeting.get("date"),
        "chunk_index": index - 1,
        "start": start,
        "end": end,
        "timestamp_start": format_time(start),
        "timestamp_end": format_time(end),
        "speakers": chunk.get("speakers") or [],
        "speaker_names": chunk.get("speakers") or [],
        "sources": chunk.get("sources") or [],
        "topic": chunk.get("topic"),
        "semantic_type": chunk.get("semantic_type"),
        "entities": chunk.get("entities") or [],
        "importance_score": chunk.get("importance_score"),
        "quality_flags": chunk.get("quality_flags") or [],
        "utterance_ids": chunk.get("utterance_ids") or [],
        "chars": len(text),
        "indexed_at": now_iso(),
    }


def upsert_rows(output_path: Path, meeting_id: str, new_rows: list[dict[str, Any]]) -> None:
    existing = [row for row in read_jsonl(output_path) if row.get("meeting_id") != meeting_id]
    write_jsonl(output_path, existing + new_rows)


def update_meeting(meeting: dict[str, Any], output_path: Path) -> None:
    rag = dict(meeting.get("rag", {}))
    indexed = set(rag.get("indexed_artifacts") or [])
    indexed.add("transcript/chunks.jsonl")
    indexed.add("artifacts/enriched_chunks.jsonl")
    rag["indexed_artifacts"] = sorted(indexed)
    meeting["rag"] = rag
    meeting["updated_at"] = now_iso()
    meeting.pop("last_error", None)


def mark_failed(meeting_path: Path, meeting: dict[str, Any], exc: BaseException, stage: str) -> None:
    meeting["processing_status"] = "failed"
    meeting["updated_at"] = now_iso()
    meeting["last_error"] = {"stage": stage, "message": str(exc), "type": type(exc).__name__, "timestamp": now_iso()}
    write_json_atomic(meeting_path, meeting)


def run(args: argparse.Namespace) -> int:
    root = repo_root()
    schema_path = root / "configs" / "schemas" / "meeting.schema.json"
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = root / output_path
    meeting_dir = resolve_meeting_dir(args.meeting_dir)
    meeting_path = meeting_dir / "meeting.json"
    if not meeting_path.exists():
        raise IndexMeetingError(f"meeting.json not found: {meeting_path}", stage="preflight")
    meeting = read_json(meeting_path)
    validate_schema(meeting, schema_path)
    chunks_rel = meeting.get("artifacts", {}).get("enriched_chunks", "artifacts/enriched_chunks.jsonl")
    chunks_path = meeting_dir / chunks_rel
    if not chunks_path.exists():
        raise IndexMeetingError(f"enriched_chunks.jsonl not found: {chunks_path}", stage="preflight")
    try:
        rows = [to_index_chunk(meeting_dir, meeting, chunk, index) for index, chunk in enumerate(read_jsonl(chunks_path), start=1)]
        if not rows:
            raise IndexMeetingError("No enriched chunks to index.", stage="preflight")
        upsert_rows(output_path, str(meeting["meeting_id"]), rows)
        update_meeting(meeting, output_path)
        validate_schema(meeting, schema_path)
        write_json_atomic(meeting_path, meeting)
    except Exception as exc:
        mark_failed(meeting_path, meeting, exc, getattr(exc, "stage", "meeting_indexing"))
        raise
    print("meeting chunks indexed")
    print(f"chunks: {len(rows)}")
    print(f"output: {output_path}")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export enriched meeting chunks into RAG-compatible JSONL.")
    parser.add_argument("--meeting-dir", required=True)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    return parser.parse_args(argv)


def main() -> int:
    try:
        return run(parse_args(sys.argv[1:]))
    except IndexMeetingError as exc:
        print(f"ERROR[{exc.stage}]: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR[runtime]: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
