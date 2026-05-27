from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from jsonschema import Draft202012Validator


WORK_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = WORK_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from asu_june_bot.core.config import load_config  # noqa: E402
from asu_june_bot.llm.ollama_common import normalize_llm_answer  # noqa: E402


ARTIFACT_PATHS = {
    "memo": "artifacts/summary.md",
    "protocol": "artifacts/protocol.md",
    "decisions": "artifacts/decisions.json",
    "tasks": "artifacts/tasks.json",
    "risks": "artifacts/risks.json",
    "open_questions": "artifacts/open_questions.json",
}

SCHEMA_FILES = {
    "decisions": "meeting.decisions.schema.json",
    "tasks": "meeting.tasks.schema.json",
    "risks": "meeting.risks.schema.json",
    "open_questions": "meeting.open_questions.schema.json",
}

ID_PREFIXES = {
    "decisions": "DEC",
    "tasks": "TASK",
    "risks": "RISK",
    "open_questions": "Q",
}


class AnalyzeMeetingError(RuntimeError):
    def __init__(self, message: str, stage: str = "meeting_analysis") -> None:
        super().__init__(message)
        self.stage = stage


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(text.rstrip() + "\n", encoding="utf-8")
    tmp_path.replace(path)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fp:
        for line_no, line in enumerate(fp, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise AnalyzeMeetingError(f"Invalid JSONL at {path}:{line_no}: {exc}", "read_chunks") from exc
    return rows


def validate_schema(data: dict[str, Any], schema_path: Path) -> None:
    schema = read_json(schema_path)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(data)


def resolve_meeting_dir(raw: str) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def format_time(seconds: float) -> str:
    total = max(0, int(seconds))
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


def compact_text(text: str, max_chars: int) -> str:
    text = str(text or "").strip()
    if len(text) <= max_chars:
        return text
    head = max_chars // 2
    tail = max_chars - head
    return text[:head].rstrip() + "\n[...]\n" + text[-tail:].lstrip()


def extract_json_object(text: str) -> dict[str, Any]:
    clean = normalize_llm_answer(text)
    clean = re.sub(r"^```(?:json)?\s*", "", clean.strip(), flags=re.IGNORECASE)
    clean = re.sub(r"\s*```$", "", clean.strip())
    start = clean.find("{")
    end = clean.rfind("}")
    if start < 0 or end <= start:
        raise AnalyzeMeetingError("LLM response does not contain a JSON object.", "parse_json")
    return json.loads(clean[start : end + 1])


def source_ref(chunk: dict[str, Any], quote: str | None = None, score: float = 0.75) -> dict[str, Any]:
    text = " ".join(str(quote or chunk.get("text") or "").split())[:500]
    return {
        "kind": "rag_source",
        "path": "transcript/chunks.jsonl",
        "start": float(chunk.get("start") or 0),
        "end": float(chunk.get("end") or chunk.get("start") or 0),
        "quote": text,
        "score": max(0.0, min(1.0, float(score))),
    }


def ollama_generate(
    base_url: str,
    model: str,
    prompt: str,
    *,
    temperature: float,
    top_p: float,
    num_ctx: int,
    keep_alive: str,
    timeout_sec: int,
) -> str:
    response = requests.post(
        f"{base_url.rstrip('/')}/api/generate",
        json={
            "model": model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": keep_alive,
            "options": {
                "temperature": temperature,
                "top_p": top_p,
                "num_ctx": num_ctx,
            },
        },
        timeout=timeout_sec,
    )
    response.raise_for_status()
    return normalize_llm_answer(response.json().get("response") or "")


def map_prompt(meeting: dict[str, Any], chunk: dict[str, Any]) -> str:
    payload = {
        "meeting_id": meeting["meeting_id"],
        "title": meeting["title"],
        "date": meeting["date"],
        "chunk_id": chunk["chunk_id"],
        "timestamp_start": format_time(float(chunk.get("start") or 0)),
        "timestamp_end": format_time(float(chunk.get("end") or 0)),
        "speakers": chunk.get("speakers") or [],
        "text": compact_text(str(chunk.get("text") or ""), 5500),
    }
    return f"""Ты извлекаешь структурированные итоги русскоязычной рабочей встречи.

Правила:
- Не выдумывай факты, владельцев и сроки.
- Каждый пункт должен быть подтвержден текстом текущего chunk.
- Если пункт неочевиден, добавь needs_review=true.
- Верни только JSON object без markdown.

Схема ответа:
{{
  "summary_bullets": ["..."],
  "decisions": [{{"title":"...", "decision":"...", "rationale":"...", "status":"accepted|proposed", "needs_review": true}}],
  "tasks": [{{"title":"...", "description":"...", "owner":"...", "due_date": null, "status":"open", "priority":"normal", "needs_review": true}}],
  "risks": [{{"title":"...", "description":"...", "impact":"low|medium|high", "probability":"low|medium|high", "mitigation":"...", "status":"open", "needs_review": true}}],
  "open_questions": [{{"question":"...", "context":"...", "owner":"...", "status":"open", "needs_review": true}}]
}}

Chunk:
{json.dumps(payload, ensure_ascii=False, indent=2)}
"""


def reduce_prompt(meeting: dict[str, Any], partials: list[dict[str, Any]]) -> str:
    payload = {
        "meeting_id": meeting["meeting_id"],
        "title": meeting["title"],
        "date": meeting["date"],
        "partials": partials,
    }
    return f"""Объедини MAP-результаты встречи в финальные структурированные итоги.

Правила:
- Удали дубли.
- Не добавляй факты вне partials.
- Сохрани смысл, но сделай формулировки короткими и деловыми.
- Верни только JSON object без markdown.

Схема ответа:
{{
  "summary_bullets": ["..."],
  "decisions": [{{"title":"...", "decision":"...", "rationale":"...", "status":"accepted|proposed", "chunk_id":"...", "needs_review": true}}],
  "tasks": [{{"title":"...", "description":"...", "owner":"...", "due_date": null, "status":"open", "priority":"normal", "chunk_id":"...", "needs_review": true}}],
  "risks": [{{"title":"...", "description":"...", "impact":"low|medium|high", "probability":"low|medium|high", "mitigation":"...", "status":"open", "chunk_id":"...", "needs_review": true}}],
  "open_questions": [{{"question":"...", "context":"...", "owner":"...", "status":"open", "chunk_id":"...", "needs_review": true}}]
}}

MAP results:
{json.dumps(payload, ensure_ascii=False, indent=2)}
"""


def fallback_map(chunk: dict[str, Any]) -> dict[str, Any]:
    return {
        "chunk_id": chunk["chunk_id"],
        "summary_bullets": [str(chunk.get("topic") or "Фрагмент встречи")],
        "decisions": chunk.get("decisions") or [],
        "tasks": [
            {
                "title": str(item.get("task") or item.get("title") or "")[:120],
                "description": str(item.get("task") or item.get("description") or ""),
                "status": "open",
                "priority": "normal",
                "needs_review": True,
            }
            for item in (chunk.get("action_items") or [])[:5]
            if str(item.get("task") or item.get("description") or "").strip()
        ],
        "risks": chunk.get("risks") or [],
        "open_questions": [
            {
                "question": str(item.get("question") or ""),
                "context": str(chunk.get("topic") or ""),
                "status": "open",
                "needs_review": True,
            }
            for item in (chunk.get("open_questions") or [])
            if str(item.get("question") or "").strip()
        ],
    }


def run_map(
    meeting: dict[str, Any],
    chunks: list[dict[str, Any]],
    partials_dir: Path,
    args: argparse.Namespace,
    cfg: dict[str, Any],
) -> list[dict[str, Any]]:
    partials_dir.mkdir(parents=True, exist_ok=True)
    if args.mode == "extractive":
        partials = [fallback_map(chunk) for chunk in chunks]
        for partial in partials:
            write_json_atomic(partials_dir / f"{partial['chunk_id']}.json", partial)
        return partials

    ollama_cfg = cfg.get("ollama", {})
    gen_cfg = cfg.get("generation", {})
    base_url = args.base_url or str(ollama_cfg.get("base_url", "http://localhost:11434"))
    model = args.model or str(ollama_cfg.get("chat_model", "qwen3:8b"))
    keep_alive = str(ollama_cfg.get("keep_alive", "24h"))
    num_ctx = int(args.num_ctx or ollama_cfg.get("generation_num_ctx", ollama_cfg.get("embedding_num_ctx", 8192)))
    temperature = float(args.temperature if args.temperature is not None else gen_cfg.get("temperature", 0.1))
    top_p = float(args.top_p if args.top_p is not None else gen_cfg.get("top_p", 0.8))

    partials: list[dict[str, Any]] = []
    for chunk in chunks:
        chunk_id = str(chunk["chunk_id"])
        raw_path = partials_dir / f"{chunk_id}.map.raw.txt"
        json_path = partials_dir / f"{chunk_id}.map.json"
        fallback_path = partials_dir / f"{chunk_id}.map.fallback.json"
        if json_path.exists() and not args.recompute_partials:
            partial = read_json(json_path)
        else:
            try:
                raw = ollama_generate(
                    base_url,
                    model,
                    map_prompt(meeting, chunk),
                    temperature=temperature,
                    top_p=top_p,
                    num_ctx=num_ctx,
                    keep_alive=keep_alive,
                    timeout_sec=args.timeout_sec,
                )
                raw_path.write_text(raw + "\n", encoding="utf-8")
                partial = extract_json_object(raw)
                partial["chunk_id"] = chunk_id
                write_json_atomic(json_path, partial)
            except Exception as exc:
                if args.strict_llm:
                    raise
                partial = fallback_map(chunk)
                partial["llm_error"] = {
                    "stage": "map",
                    "message": str(exc),
                    "type": type(exc).__name__,
                }
                write_json_atomic(fallback_path, partial)
                print(f"[MAP fallback] {chunk_id}: {exc}", flush=True)
        partials.append(partial)

    if args.mode == "ollama-map-only":
        return partials

    raw_reduce_path = partials_dir / "reduce.raw.txt"
    reduce_json_path = partials_dir / "reduce.json"
    if reduce_json_path.exists() and not args.recompute_partials:
        return [read_json(reduce_json_path)]

    try:
        raw_reduce = ollama_generate(
            base_url,
            model,
            reduce_prompt(meeting, partials),
            temperature=temperature,
            top_p=top_p,
            num_ctx=num_ctx,
            keep_alive=keep_alive,
            timeout_sec=args.timeout_sec,
        )
        raw_reduce_path.write_text(raw_reduce + "\n", encoding="utf-8")
        reduced = extract_json_object(raw_reduce)
        write_json_atomic(reduce_json_path, reduced)
    except Exception as exc:
        if args.strict_llm:
            raise
        reduced = merge_partials(partials)
        reduced["llm_error"] = {
            "stage": "reduce",
            "message": str(exc),
            "type": type(exc).__name__,
        }
        write_json_atomic(reduce_json_path, reduced)
        print(f"[REDUCE fallback]: {exc}", flush=True)
    return [reduced]


def chunk_by_id(chunks: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(chunk["chunk_id"]): chunk for chunk in chunks}


def source_chunk(item: dict[str, Any], chunks: list[dict[str, Any]], fallback_index: int) -> dict[str, Any]:
    by_id = chunk_by_id(chunks)
    chunk_id = item.get("chunk_id")
    if chunk_id and str(chunk_id) in by_id:
        return by_id[str(chunk_id)]
    return chunks[min(fallback_index, len(chunks) - 1)]


def clean_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"null", "none", "не указано", "n/a"}:
        return None
    return text


def normalize_items(kind: str, raw_items: list[Any], chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_items, start=1):
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        chunk = source_chunk(item, chunks, index - 1)
        ref = source_ref(chunk, item.get("decision") or item.get("description") or item.get("question") or item.get("title"))
        prefix = ID_PREFIXES[kind]
        if kind == "decisions":
            text = clean_optional_string(item.get("decision") or item.get("title"))
            if not text:
                continue
            row = {
                "decision_id": f"{prefix}-{index:03d}",
                "title": clean_optional_string(item.get("title")) or text[:120],
                "decision": text,
                "rationale": clean_optional_string(item.get("rationale")),
                "status": item.get("status") if item.get("status") in {"proposed", "accepted", "rejected", "superseded"} else "proposed",
                "source_refs": [ref],
                "needs_review": bool(item.get("needs_review", True)),
            }
        elif kind == "tasks":
            title = clean_optional_string(item.get("title") or item.get("description"))
            if not title:
                continue
            row = {
                "task_id": f"{prefix}-{index:03d}",
                "title": title[:160],
                "description": clean_optional_string(item.get("description")),
                "owner": clean_optional_string(item.get("owner")),
                "due_date": clean_optional_string(item.get("due_date")),
                "status": item.get("status") if item.get("status") in {"open", "in_progress", "done", "blocked", "cancelled"} else "open",
                "priority": item.get("priority") if item.get("priority") in {"low", "normal", "high"} else "normal",
                "source_refs": [ref],
                "needs_review": bool(item.get("needs_review", True)),
            }
        elif kind == "risks":
            desc = clean_optional_string(item.get("description") or item.get("title"))
            if not desc:
                continue
            row = {
                "risk_id": f"{prefix}-{index:03d}",
                "title": clean_optional_string(item.get("title")) or desc[:120],
                "description": desc,
                "impact": item.get("impact") if item.get("impact") in {"low", "medium", "high"} else "medium",
                "probability": item.get("probability") if item.get("probability") in {"low", "medium", "high"} else "medium",
                "mitigation": clean_optional_string(item.get("mitigation")),
                "owner": clean_optional_string(item.get("owner")),
                "status": item.get("status") if item.get("status") in {"open", "monitoring", "mitigated", "closed"} else "open",
                "source_refs": [ref],
                "needs_review": bool(item.get("needs_review", True)),
            }
        else:
            question = clean_optional_string(item.get("question"))
            if not question:
                continue
            row = {
                "question_id": f"{prefix}-{index:03d}",
                "question": question,
                "context": clean_optional_string(item.get("context")),
                "owner": clean_optional_string(item.get("owner")),
                "due_date": clean_optional_string(item.get("due_date")),
                "status": item.get("status") if item.get("status") in {"open", "answered", "closed"} else "open",
                "answer": clean_optional_string(item.get("answer")),
                "source_refs": [ref],
                "needs_review": bool(item.get("needs_review", True)),
            }
        items.append({key: value for key, value in row.items() if value is not None})
    return items


def merge_partials(partials: list[dict[str, Any]]) -> dict[str, Any]:
    if len(partials) == 1 and any(key in partials[0] for key in ("decisions", "tasks", "risks", "open_questions")):
        return partials[0]
    merged: dict[str, Any] = {"summary_bullets": [], "decisions": [], "tasks": [], "risks": [], "open_questions": []}
    for partial in partials:
        for key in merged:
            values = partial.get(key) or []
            if isinstance(values, list):
                for value in values:
                    if isinstance(value, dict):
                        value = dict(value)
                        value.setdefault("chunk_id", partial.get("chunk_id"))
                    merged[key].append(value)
    return merged


def artifact_doc(kind: str, meeting_id: str, generated_at: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"schema_version": 1, "meeting_id": meeting_id, "generated_at": generated_at, "items": items}


def render_summary(meeting: dict[str, Any], reduced: dict[str, Any], docs: dict[str, dict[str, Any]]) -> str:
    lines = [
        f"# Summary: {meeting['title']}",
        "",
        f"- Дата: {meeting['date']}",
        f"- meeting_id: `{meeting['meeting_id']}`",
        "- Режим: LLM map-reduce с обязательными source_refs.",
        "",
        "## Кратко",
        "",
    ]
    bullets = reduced.get("summary_bullets") or []
    if bullets:
        lines.extend(f"- {bullet}" for bullet in bullets[:10])
    else:
        lines.append("- Краткое резюме не выделено моделью.")
    for title, key in (("Решения", "decisions"), ("Задачи", "tasks"), ("Риски", "risks"), ("Открытые вопросы", "open_questions")):
        lines.extend(["", f"## {title}", ""])
        items = docs[key]["items"]
        if not items:
            lines.append("- Не выявлены.")
            continue
        for item in items:
            ref = item["source_refs"][0]
            label = item.get("decision") or item.get("description") or item.get("question") or item.get("title")
            lines.append(f"- [{format_time(ref['start'])}] {label}")
    return "\n".join(lines) + "\n"


def render_protocol(meeting: dict[str, Any], docs: dict[str, dict[str, Any]]) -> str:
    lines = [
        f"# Протокол встречи: {meeting['title']}",
        "",
        "## 1. Общая информация",
        "",
        f"- Дата: {meeting['date']}",
        f"- meeting_id: `{meeting['meeting_id']}`",
        "",
        "## 2. Решения",
        "",
    ]
    decisions = docs["decisions"]["items"]
    lines.extend(f"- {item['decision_id']} [{format_time(item['source_refs'][0]['start'])}] {item['decision']}" for item in decisions)
    if not decisions:
        lines.append("- Не выявлены.")
    lines.extend(["", "## 3. Задачи", ""])
    tasks = docs["tasks"]["items"]
    lines.extend(
        f"- {item['task_id']} [{format_time(item['source_refs'][0]['start'])}] {item['title']} | owner: {item.get('owner', 'не указан')} | due: {item.get('due_date', 'не указан')}"
        for item in tasks
    )
    if not tasks:
        lines.append("- Не выявлены.")
    lines.extend(["", "## 4. Риски", ""])
    risks = docs["risks"]["items"]
    lines.extend(f"- {item['risk_id']} [{format_time(item['source_refs'][0]['start'])}] {item['description']}" for item in risks)
    if not risks:
        lines.append("- Не выявлены.")
    lines.extend(["", "## 5. Открытые вопросы", ""])
    questions = docs["open_questions"]["items"]
    lines.extend(f"- {item['question_id']} [{format_time(item['source_refs'][0]['start'])}] {item['question']}" for item in questions)
    if not questions:
        lines.append("- Не выявлены.")
    return "\n".join(lines) + "\n"


def update_meeting(meeting: dict[str, Any]) -> None:
    artifacts = dict(meeting.get("artifacts", {}))
    artifacts.update(ARTIFACT_PATHS)
    meeting["artifacts"] = artifacts
    meeting["processing_status"] = "summarized"
    meeting["updated_at"] = now_iso()
    meeting.pop("last_error", None)


def mark_failed(meeting_path: Path, meeting: dict[str, Any], exc: BaseException, stage: str) -> None:
    meeting["processing_status"] = "failed"
    meeting["updated_at"] = now_iso()
    meeting["last_error"] = {"stage": stage, "message": str(exc), "type": type(exc).__name__, "timestamp": now_iso()}
    write_json_atomic(meeting_path, meeting)


def run(args: argparse.Namespace) -> int:
    schema_dir = WORK_ROOT / "configs" / "schemas"
    meeting_dir = resolve_meeting_dir(args.meeting_dir)
    meeting_path = meeting_dir / "meeting.json"
    if not meeting_path.exists():
        raise AnalyzeMeetingError(f"meeting.json not found: {meeting_path}", "preflight")

    meeting = read_json(meeting_path)
    validate_schema(meeting, schema_dir / "meeting.schema.json")
    chunks_rel = meeting.get("artifacts", {}).get("enriched_chunks", "artifacts/enriched_chunks.jsonl")
    chunks_path = meeting_dir / chunks_rel
    if not chunks_path.exists():
        raise AnalyzeMeetingError(f"enriched chunks not found: {chunks_path}", "preflight")

    for rel_path in ARTIFACT_PATHS.values():
        target = meeting_dir / rel_path
        if target.exists() and not args.force:
            raise AnalyzeMeetingError(f"Artifact already exists: {target}. Use --force.", "preflight")

    chunks = [chunk for chunk in read_jsonl(chunks_path) if str(chunk.get("text") or "").strip()]
    if not chunks:
        raise AnalyzeMeetingError("No enriched chunks to analyze.", "preflight")

    try:
        cfg = load_config()
        partials = run_map(meeting, chunks, meeting_dir / "artifacts" / "_partials" / "llm_map_reduce", args, cfg)
        reduced = merge_partials(partials)
        generated_at = now_iso()
        docs = {
            key: artifact_doc(
                key,
                str(meeting["meeting_id"]),
                generated_at,
                normalize_items(key, reduced.get(key) or [], chunks),
            )
            for key in SCHEMA_FILES
        }

        for key, schema_file in SCHEMA_FILES.items():
            validate_schema(docs[key], schema_dir / schema_file)

        write_text_atomic(meeting_dir / ARTIFACT_PATHS["memo"], render_summary(meeting, reduced, docs))
        write_text_atomic(meeting_dir / ARTIFACT_PATHS["protocol"], render_protocol(meeting, docs))
        for key in SCHEMA_FILES:
            write_json_atomic(meeting_dir / ARTIFACT_PATHS[key], docs[key])

        update_meeting(meeting)
        validate_schema(meeting, schema_dir / "meeting.schema.json")
        write_json_atomic(meeting_path, meeting)
    except Exception as exc:
        mark_failed(meeting_path, meeting, exc, getattr(exc, "stage", "meeting_analysis"))
        raise

    print("meeting analysis complete")
    print(f"mode: {args.mode}")
    print(f"chunks: {len(chunks)}")
    for key in ("decisions", "tasks", "risks", "open_questions"):
        print(f"{key}: {len(docs[key]['items'])}")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LLM map-reduce extraction for meeting artifacts.")
    parser.add_argument("--meeting-dir", required=True)
    parser.add_argument("--mode", choices=("ollama-map-reduce", "ollama-map-only", "extractive"), default="ollama-map-reduce")
    parser.add_argument("--model")
    parser.add_argument("--base-url")
    parser.add_argument("--num-ctx", type=int)
    parser.add_argument("--temperature", type=float)
    parser.add_argument("--top-p", type=float)
    parser.add_argument("--timeout-sec", type=int, default=180)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--recompute-partials", action="store_true", help="Re-run MAP/REDUCE even when partial JSON files already exist.")
    parser.add_argument("--strict-llm", action="store_true", help="Fail instead of using extractive fallback on invalid LLM output.")
    return parser.parse_args(argv)


def main() -> int:
    try:
        return run(parse_args(sys.argv[1:]))
    except AnalyzeMeetingError as exc:
        print(f"ERROR[{exc.stage}]: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR[runtime]: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
