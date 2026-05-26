from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


SEMANTIC_MARKERS = {
    "decision": ("решили", "решение", "согласовали", "принимаем", "фиксируем"),
    "action_item": ("задача", "надо", "нужно", "сделать", "подготовить", "проверить", "ответственный"),
    "risk": ("риск", "проблема", "заблокировано", "не успеем", "опасность"),
    "open_question": ("вопрос", "уточнить", "непонятно", "осталось открытым", "обсудить"),
    "requirement_change": ("требование", "изменение", "доработать", "поменять", "правка"),
    "status_update": ("статус", "готово", "в работе", "прогресс", "завершили"),
    "issue": ("дефект", "инцидент", "ошибка", "не работает", "проблема"),
}
ENTITY_RE = re.compile(
    r"\b(?:ФТТ|ПМИ|ЦТА|ПР|AD|LDAP|LDAPS|JWT|OAuth|OIDC|MDR|КШД|СОИ|НОВАДОК|НОВАТЭК|ОПКС|УПКС|ППО|СПО)\b",
    re.IGNORECASE,
)


class EnrichMeetingError(RuntimeError):
    def __init__(self, message: str, stage: str = "meeting_enrichment") -> None:
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
    with path.open("r", encoding="utf-8") as fh:
        for line_number, line in enumerate(fh, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                rows.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise EnrichMeetingError(f"Invalid JSONL at {path}:{line_number}: {exc}", stage="read_chunks") from exc
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?。])\s+|\n+", text)
    return [part.strip() for part in parts if part.strip()]


def detect_semantic_type(text: str) -> str:
    lowered = text.lower()
    for semantic_type, markers in SEMANTIC_MARKERS.items():
        if any(marker in lowered for marker in markers):
            return semantic_type
    return "discussion"


def detect_topic(text: str, semantic_type: str) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    if not clean:
        return "Без темы"
    first = sentences(clean)[0] if sentences(clean) else clean
    first = re.sub(r"^\[[^\]]+\]\s*", "", first)
    topic = first[:90].strip(" .,:;")
    if topic:
        return topic
    return semantic_type


def detect_entities(text: str) -> list[str]:
    found = []
    seen = set()
    for match in ENTITY_RE.finditer(text):
        value = match.group(0).upper().replace("Ё", "Е")
        if value not in seen:
            seen.add(value)
            found.append(value)
    return found


def extract_candidates(text: str, semantic_type: str, timestamp: float) -> dict[str, list[dict[str, Any]]]:
    result = {"decisions": [], "action_items": [], "risks": [], "open_questions": []}
    for sentence in sentences(text):
        lowered = sentence.lower()
        source_ref = {"timecode_start": timestamp, "note": "heuristic_chunk_enrichment"}
        if semantic_type == "decision" or any(marker in lowered for marker in SEMANTIC_MARKERS["decision"]):
            result["decisions"].append({"text": sentence, "confidence": 0.55, "source_refs": [source_ref]})
        if semantic_type == "action_item" or any(marker in lowered for marker in SEMANTIC_MARKERS["action_item"]):
            result["action_items"].append({"task": sentence, "owner": None, "due_date": None, "confidence": 0.5, "source_refs": [source_ref]})
        if semantic_type == "risk" or any(marker in lowered for marker in SEMANTIC_MARKERS["risk"]):
            result["risks"].append({"risk": sentence, "confidence": 0.5, "source_refs": [source_ref]})
        if semantic_type == "open_question" or "?" in sentence or any(marker in lowered for marker in SEMANTIC_MARKERS["open_question"]):
            result["open_questions"].append({"question": sentence, "confidence": 0.5, "source_refs": [source_ref]})
    return result


def enrich_chunk(chunk: dict[str, Any]) -> dict[str, Any]:
    text = str(chunk.get("text") or "").strip()
    if not text:
        raise EnrichMeetingError("Chunk text is empty.", stage="validate_chunks")
    semantic_type = detect_semantic_type(text)
    start = float(chunk.get("start") or 0)
    candidates = extract_candidates(text, semantic_type, start)
    quality_flags = []
    if semantic_type in {"action_item", "decision", "risk", "open_question"}:
        quality_flags.append("needs_human_review")
    if not chunk.get("speakers"):
        quality_flags.append("missing_speaker")
    return {
        **chunk,
        "topic": detect_topic(text, semantic_type),
        "semantic_type": semantic_type,
        "entities": detect_entities(text),
        "decisions": candidates["decisions"],
        "action_items": candidates["action_items"],
        "risks": candidates["risks"],
        "open_questions": candidates["open_questions"],
        "importance_score": 0.7 if semantic_type != "discussion" else 0.35,
        "quality_flags": quality_flags,
        "enrichment_mode": "heuristic_v1",
        "needs_review": True,
    }


def update_meeting(meeting: dict[str, Any]) -> None:
    artifacts = dict(meeting.get("artifacts", {}))
    artifacts["enriched_chunks"] = "artifacts/enriched_chunks.jsonl"
    meeting["artifacts"] = artifacts
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
    meeting_dir = resolve_meeting_dir(args.meeting_dir)
    meeting_path = meeting_dir / "meeting.json"
    if not meeting_path.exists():
        raise EnrichMeetingError(f"meeting.json not found: {meeting_path}", stage="preflight")
    meeting = read_json(meeting_path)
    validate_schema(meeting, schema_path)
    chunks_rel = meeting.get("artifacts", {}).get("chunks", "transcript/chunks.jsonl")
    chunks_path = meeting_dir / chunks_rel
    if not chunks_path.exists():
        raise EnrichMeetingError(f"chunks.jsonl not found: {chunks_path}", stage="preflight")
    output_path = meeting_dir / "artifacts" / "enriched_chunks.jsonl"
    if output_path.exists() and not args.force:
        raise EnrichMeetingError(f"Enriched chunks already exist: {output_path}. Use --force.", stage="preflight")
    try:
        enriched = [enrich_chunk(chunk) for chunk in read_jsonl(chunks_path)]
        write_jsonl(output_path, enriched)
        update_meeting(meeting)
        validate_schema(meeting, schema_path)
        write_json_atomic(meeting_path, meeting)
    except Exception as exc:
        mark_failed(meeting_path, meeting, exc, getattr(exc, "stage", "meeting_enrichment"))
        raise
    print("meeting enrichment complete")
    print(f"chunks: {len(enriched)}")
    print(f"jsonl: {output_path}")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Heuristically enrich meeting chunks for MVP indexing and analysis.")
    parser.add_argument("--meeting-dir", required=True)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args(argv)


def main() -> int:
    try:
        return run(parse_args(sys.argv[1:]))
    except EnrichMeetingError as exc:
        print(f"ERROR[{exc.stage}]: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR[runtime]: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
