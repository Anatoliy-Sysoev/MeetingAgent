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
ARTIFACT_SPECS = {
    "decisions": {
        "source_type": "meeting_decision",
        "path": "artifacts/decisions.json",
        "id_key": "decision_id",
        "title_key": "title",
        "body_key": "decision",
    },
    "tasks": {
        "source_type": "meeting_action_item",
        "path": "artifacts/tasks.json",
        "id_key": "task_id",
        "title_key": "title",
        "body_key": "description",
    },
    "risks": {
        "source_type": "meeting_risk",
        "path": "artifacts/risks.json",
        "id_key": "risk_id",
        "title_key": "title",
        "body_key": "description",
    },
    "open_questions": {
        "source_type": "meeting_open_question",
        "path": "artifacts/open_questions.json",
        "id_key": "question_id",
        "title_key": "question",
        "body_key": "context",
    },
}
STRUCTURED_SOURCE_TYPES = {str(spec["source_type"]) for spec in ARTIFACT_SPECS.values()}


class IndexArtifactsError(RuntimeError):
    def __init__(self, message: str, stage: str = "meeting_artifact_indexing") -> None:
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
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
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


def stable_id(value: str, length: int = 32) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def format_time(seconds: float) -> str:
    total = max(0, int(seconds))
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


def first_source_ref(item: dict[str, Any]) -> dict[str, Any]:
    refs = item.get("source_refs") or []
    if refs and isinstance(refs[0], dict):
        return refs[0]
    return {}


def text_for_artifact(meeting: dict[str, Any], artifact_key: str, item: dict[str, Any], spec: dict[str, str]) -> str:
    ref = first_source_ref(item)
    start = float(ref.get("start") or 0)
    end = float(ref.get("end") or start)
    title = str(item.get(spec["title_key"]) or item.get(spec["body_key"]) or "")
    body = str(item.get(spec["body_key"]) or title)
    parts = [
        f"Встреча: {meeting.get('title')}",
        f"Дата: {meeting.get('date')}",
        f"Тип артефакта: {spec['source_type']}",
        f"ID: {item.get(spec['id_key'])}",
        f"Таймкод: {format_time(start)} - {format_time(end)}",
        f"Заголовок: {title}",
        f"Статус: {item.get('status') or 'не указан'}",
    ]
    if item.get("owner"):
        parts.append(f"Ответственный: {item.get('owner')}")
    if item.get("due_date"):
        parts.append(f"Срок: {item.get('due_date')}")
    if item.get("priority"):
        parts.append(f"Приоритет: {item.get('priority')}")
    if item.get("impact"):
        parts.append(f"Влияние: {item.get('impact')}")
    if item.get("probability"):
        parts.append(f"Вероятность: {item.get('probability')}")
    if item.get("mitigation"):
        parts.append(f"Мера: {item.get('mitigation')}")
    if item.get("rationale"):
        parts.append(f"Обоснование: {item.get('rationale')}")
    parts.extend(["", body])
    if ref.get("quote"):
        parts.extend(["", f"Цитата: {ref.get('quote')}"])
    return "\n".join(parts).strip()


def to_index_rows(meeting_dir: Path, meeting: dict[str, Any], artifact_key: str, artifact_doc: dict[str, Any]) -> list[dict[str, Any]]:
    spec = ARTIFACT_SPECS[artifact_key]
    rows: list[dict[str, Any]] = []
    meeting_id = str(meeting["meeting_id"])
    artifact_rel = str(meeting.get("artifacts", {}).get(artifact_key) or spec["path"])
    for index, item in enumerate(artifact_doc.get("items") or [], start=1):
        if not isinstance(item, dict):
            continue
        artifact_id = str(item.get(spec["id_key"]) or f"{artifact_key}-{index:03d}")
        ref = first_source_ref(item)
        start = float(ref.get("start") or 0)
        end = float(ref.get("end") or start)
        text = text_for_artifact(meeting, artifact_key, item, spec)
        chunk_id = f"{meeting_id}-{spec['source_type']}-{artifact_id.lower()}"
        rows.append(
            {
                "chunk_id": chunk_id,
                "db_id": stable_id(f"meeting-artifact:{meeting_id}:{spec['source_type']}:{artifact_id}"),
                "text": text,
                "source_type": spec["source_type"],
                "document_type": "Протокол",
                "relative_path": f"meetings/{meeting_id}/{artifact_rel}",
                "source_path": str(meeting_dir / artifact_rel),
                "extension": ".json",
                "meeting_id": meeting_id,
                "meeting_title": meeting.get("title"),
                "meeting_date": meeting.get("date"),
                "artifact_type": artifact_key,
                "artifact_id": artifact_id,
                "chunk_index": index - 1,
                "start": start,
                "end": end,
                "timestamp_start": format_time(start),
                "timestamp_end": format_time(end),
                "topic": item.get(spec["title_key"]) or item.get(spec["body_key"]),
                "semantic_type": spec["source_type"].replace("meeting_", ""),
                "status": item.get("status"),
                "owner": item.get("owner"),
                "due_date": item.get("due_date"),
                "needs_review": item.get("needs_review"),
                "source_refs": item.get("source_refs") or [],
                "chars": len(text),
                "indexed_at": now_iso(),
            }
        )
    return rows


def upsert_rows(output_path: Path, meeting_id: str, new_rows: list[dict[str, Any]]) -> None:
    existing = [
        row
        for row in read_jsonl(output_path)
        if not (row.get("meeting_id") == meeting_id and row.get("source_type") in STRUCTURED_SOURCE_TYPES)
    ]
    write_jsonl(output_path, existing + new_rows)


def update_meeting(meeting: dict[str, Any]) -> None:
    rag = dict(meeting.get("rag", {}))
    indexed = set(rag.get("indexed_artifacts") or [])
    for key in ARTIFACT_SPECS:
        indexed.add(str(meeting.get("artifacts", {}).get(key) or ARTIFACT_SPECS[key]["path"]))
    rag["indexed_artifacts"] = sorted(indexed)
    meeting["rag"] = rag
    meeting["processing_status"] = "indexed"
    meeting["updated_at"] = now_iso()
    meeting.pop("last_error", None)


def mark_failed(meeting_path: Path, meeting: dict[str, Any], exc: BaseException, stage: str) -> None:
    meeting["processing_status"] = "failed"
    meeting["updated_at"] = now_iso()
    meeting["last_error"] = {"stage": stage, "message": str(exc), "type": type(exc).__name__, "timestamp": now_iso()}
    write_json_atomic(meeting_path, meeting)


def run(args: argparse.Namespace) -> int:
    root = repo_root()
    schema_dir = root / "configs" / "schemas"
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = root / output_path
    meeting_dir = resolve_meeting_dir(args.meeting_dir)
    meeting_path = meeting_dir / "meeting.json"
    if not meeting_path.exists():
        raise IndexArtifactsError(f"meeting.json not found: {meeting_path}", "preflight")

    meeting = read_json(meeting_path)
    validate_schema(meeting, schema_dir / "meeting.schema.json")
    all_rows: list[dict[str, Any]] = []
    try:
        for artifact_key, spec in ARTIFACT_SPECS.items():
            rel_path = str(meeting.get("artifacts", {}).get(artifact_key) or spec["path"])
            artifact_path = meeting_dir / rel_path
            if not artifact_path.exists():
                if args.allow_missing:
                    continue
                raise IndexArtifactsError(f"Artifact not found: {artifact_path}", "preflight")
            doc = read_json(artifact_path)
            validate_schema(doc, schema_dir / f"meeting.{artifact_key}.schema.json")
            all_rows.extend(to_index_rows(meeting_dir, meeting, artifact_key, doc))
        if not all_rows:
            raise IndexArtifactsError("No structured meeting artifacts to index.", "preflight")
        upsert_rows(output_path, str(meeting["meeting_id"]), all_rows)
        update_meeting(meeting)
        validate_schema(meeting, schema_dir / "meeting.schema.json")
        write_json_atomic(meeting_path, meeting)
    except Exception as exc:
        mark_failed(meeting_path, meeting, exc, getattr(exc, "stage", "meeting_artifact_indexing"))
        raise

    print("meeting artifacts indexed")
    print(f"rows: {len(all_rows)}")
    print(f"output: {output_path}")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export structured meeting artifacts into RAG-compatible JSONL.")
    parser.add_argument("--meeting-dir", required=True)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--allow-missing", action="store_true")
    return parser.parse_args(argv)


def main() -> int:
    try:
        return run(parse_args(sys.argv[1:]))
    except IndexArtifactsError as exc:
        print(f"ERROR[{exc.stage}]: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR[runtime]: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
