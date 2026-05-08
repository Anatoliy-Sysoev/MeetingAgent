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

from rag_common import load_config


STATUS_TRANSCRIBED = "transcribed"
STATUS_SUMMARIZED = "summarized"
STATUS_FAILED = "failed"

ARTIFACT_SCHEMAS = {
    "decisions": "meeting.decisions.schema.json",
    "tasks": "meeting.tasks.schema.json",
    "risks": "meeting.risks.schema.json",
    "open_questions": "meeting.open_questions.schema.json",
}

ARTIFACT_PATHS = {
    "memo": "artifacts/memo.md",
    "protocol": "artifacts/protocol.md",
    "decisions": "artifacts/decisions.json",
    "tasks": "artifacts/tasks.json",
    "risks": "artifacts/risks.json",
    "open_questions": "artifacts/open_questions.json",
}

DECISION_KEYWORDS = (
    "предлагаю",
    "давай",
    "давайте",
    "удалим",
    "удалить",
    "убрать",
    "оставить",
    "указать",
    "переформулировать",
    "сделаем",
)

TASK_KEYWORDS = (
    "сделаю",
    "схожу",
    "передам",
    "подадим",
    "обсужу",
    "нужно",
    "надо",
    "нужна",
    "подготовим",
)

RISK_KEYWORDS = (
    "не входит",
    "за рамками",
    "не настроено",
    "не запрашивалось",
    "разъедутся",
    "придется",
    "не хватает",
    "если",
    "риск",
)

QUESTION_KEYWORDS = (
    "?",
    "вопрос",
    "уточнить",
    "каких документах",
    "почему",
    "как",
    "где",
)


class MeetingArtifactsError(RuntimeError):
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


def resolve_meeting_dir(raw: str) -> Path:
    meeting_dir = Path(raw).expanduser()
    if not meeting_dir.is_absolute():
        meeting_dir = (Path.cwd() / meeting_dir).resolve()
    return meeting_dir.resolve()


def ensure_status_allows_run(meeting: dict[str, Any], force: bool) -> None:
    status = meeting.get("processing_status")
    if status == STATUS_TRANSCRIBED:
        return
    if force and status in {STATUS_SUMMARIZED, STATUS_FAILED}:
        return
    if status == STATUS_SUMMARIZED:
        raise MeetingArtifactsError(
            "Meeting is already summarized. Use --force to regenerate artifacts.",
            stage="preflight",
        )
    if status == STATUS_FAILED:
        raise MeetingArtifactsError(
            "Meeting status is failed. Use --force to retry artifact generation.",
            stage="preflight",
        )
    raise MeetingArtifactsError(
        f"Meeting status must be 'transcribed' before artifact generation, got '{status}'.",
        stage="preflight",
    )


def require_artifact_file(meeting_dir: Path, meeting: dict[str, Any], key: str) -> Path:
    value = meeting.get("artifacts", {}).get(key)
    if not value:
        raise MeetingArtifactsError(
            f"meeting.json must contain artifacts.{key}.",
            stage="preflight",
        )
    path = meeting_dir / value
    if not path.exists():
        raise MeetingArtifactsError(
            f"Artifact file does not exist: {path}",
            stage="preflight",
        )
    return path


def load_segments(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for idx, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        row = json.loads(line)
        row.setdefault("segment_index", idx)
        rows.append(row)
    if not rows:
        raise MeetingArtifactsError(
            f"No transcript segments found in {path}",
            stage="preflight",
        )
    return rows


def format_time(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def compact_segments(segments: list[dict[str, Any]], max_chars: int) -> str:
    lines: list[str] = []
    used = 0
    for row in segments:
        text = " ".join(str(row.get("text", "")).split())
        if not text:
            continue
        start = float(row.get("start", 0))
        end = float(row.get("end", start))
        segment_index = int(row.get("segment_index", len(lines)))
        line = f"[{segment_index:04d}] [{format_time(start)}-{format_time(end)}] {text}"
        if lines and used + len(line) > max_chars:
            break
        lines.append(line)
        used += len(line) + 1
    return "\n".join(lines)


def segment_text(row: dict[str, Any]) -> str:
    return " ".join(str(row.get("text", "")).split())


def source_ref(row: dict[str, Any], quote_limit: int = 320) -> dict[str, Any]:
    text = segment_text(row)
    quote = text[: quote_limit - 1].rstrip() + "…" if len(text) > quote_limit else text
    return {
        "kind": "transcript_segment",
        "path": "transcript/segments.jsonl",
        "segment_index": int(row.get("segment_index", 0)),
        "start": float(row.get("start", 0)),
        "end": float(row.get("end", row.get("start", 0))),
        "quote": quote,
    }


def short_title(text: str, limit: int = 90) -> str:
    text = segment_text({"text": text}).strip(" .")
    if len(text) <= limit:
        return text or "Фрагмент встречи"
    return text[: limit - 1].rstrip() + "…"


def keyword_score(text: str, keywords: tuple[str, ...]) -> int:
    lowered = text.lower()
    return sum(1 for keyword in keywords if keyword.lower() in lowered)


def select_segments(segments: list[dict[str, Any]], keywords: tuple[str, ...], limit: int) -> list[dict[str, Any]]:
    scored: list[tuple[int, int, dict[str, Any]]] = []
    for row in segments:
        text = segment_text(row)
        if not text:
            continue
        score = keyword_score(text, keywords)
        if score <= 0:
            continue
        scored.append((score, int(row.get("segment_index", 0)), row))
    scored.sort(key=lambda item: (-item[0], item[1]))

    selected: list[dict[str, Any]] = []
    seen: set[int] = set()
    for _score, _idx, row in scored:
        idx = int(row.get("segment_index", 0))
        if idx in seen:
            continue
        seen.add(idx)
        selected.append(row)
        if len(selected) >= limit:
            break
    return selected


def build_extractive_memo(meeting: dict[str, Any], segments: list[dict[str, Any]]) -> str:
    title = meeting.get("title", meeting.get("meeting_id", "Встреча"))
    date = meeting.get("date", "")
    discussion = select_segments(
        segments,
        DECISION_KEYWORDS + TASK_KEYWORDS + RISK_KEYWORDS,
        limit=10,
    )
    decisions = select_segments(segments, DECISION_KEYWORDS, limit=6)
    tasks = select_segments(segments, TASK_KEYWORDS, limit=6)
    risks = select_segments(segments, RISK_KEYWORDS + QUESTION_KEYWORDS, limit=6)

    def bullet(row: dict[str, Any]) -> str:
        return f"- [{format_time(float(row.get('start', 0)))}] {segment_text(row)}"

    lines = [
        f"# Memo: {title}",
        "",
        f"- Дата: {date}",
        f"- meeting_id: `{meeting.get('meeting_id', '')}`",
        "- Режим: extractive MVP, требует ручной проверки",
        "",
        "## Краткая Суть",
        "",
        "Встреча посвящена разбору замечаний по проектной документации, удалению или переформулировке спорных разделов, а также согласованию того, какие вопросы относятся к Паспорту ИС, ЦТА, руководствам и реестру замечаний.",
        "",
        "## Обсуждалось",
        "",
    ]
    lines.extend(bullet(row) for row in discussion[:8])
    lines.extend(["", "## Важные Решения", ""])
    lines.extend(bullet(row) for row in decisions[:5])
    lines.extend(["", "## Задачи", ""])
    lines.extend(bullet(row) for row in tasks[:5])
    lines.extend(["", "## Риски И Открытые Вопросы", ""])
    lines.extend(bullet(row) for row in risks[:5])
    lines.extend(
        [
            "",
            "## Требует Ручной Проверки",
            "",
            "- Extractive-режим не подтверждает смысл как человек: перед использованием в документах проверьте пункты по таймкодам.",
            "- Если нужен финальный протокол, запустите LLM-режим или ручную редактуру поверх этого черновика.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def build_extractive_protocol(meeting: dict[str, Any], segments: list[dict[str, Any]]) -> str:
    title = meeting.get("title", meeting.get("meeting_id", "Встреча"))
    participants = ", ".join(meeting.get("participants", [])) or "не указаны"
    decisions = select_segments(segments, DECISION_KEYWORDS, limit=8)
    tasks = select_segments(segments, TASK_KEYWORDS, limit=8)
    risks = select_segments(segments, RISK_KEYWORDS, limit=6)
    questions = select_segments(segments, QUESTION_KEYWORDS, limit=6)

    lines = [
        f"# Протокол: {title}",
        "",
        "## Общие Сведения",
        "",
        f"- Дата: {meeting.get('date', '')}",
        f"- Участники: {participants}",
        f"- Источник: {meeting.get('source', {}).get('kind', '')}",
        "- Режим: extractive MVP, требует ручной проверки",
        "",
        "## Повестка / Темы",
        "",
        "1. Разбор замечаний к документации.",
        "2. Уточнение, какие разделы должны оставаться в руководстве, а какие относятся к Паспорту ИС или ЦТА.",
        "3. Действия по реестру замечаний, мониторингу, логированию, резервному копированию и версионированию.",
        "",
        "## Ход Обсуждения",
        "",
    ]
    for row in select_segments(segments, DECISION_KEYWORDS + TASK_KEYWORDS + RISK_KEYWORDS, limit=12):
        lines.append(f"- [{format_time(float(row.get('start', 0)))}] {segment_text(row)}")

    lines.extend(["", "## Принятые Решения", "", "| ID | Решение | Основание | Источник |", "| --- | --- | --- | --- |"])
    for i, row in enumerate(decisions, start=1):
        lines.append(f"| DEC-{i:03d} | {short_title(segment_text(row))} | Требует проверки по transcript | {format_time(float(row.get('start', 0)))} |")

    lines.extend(["", "## Поручения", "", "| ID | Что Сделать | Ответственный | Срок | Источник |", "| --- | --- | --- | --- | --- |"])
    for i, row in enumerate(tasks, start=1):
        lines.append(f"| TASK-{i:03d} | {short_title(segment_text(row))} | не указан | не указан | {format_time(float(row.get('start', 0)))} |")

    lines.extend(["", "## Риски", "", "| ID | Риск | Меры | Источник |", "| --- | --- | --- | --- |"])
    for i, row in enumerate(risks, start=1):
        lines.append(f"| RISK-{i:03d} | {short_title(segment_text(row))} | уточнить | {format_time(float(row.get('start', 0)))} |")

    lines.extend(["", "## Открытые Вопросы", "", "| ID | Вопрос | Кому / куда | Источник |", "| --- | --- | --- | --- |"])
    for i, row in enumerate(questions, start=1):
        lines.append(f"| Q-{i:03d} | {short_title(segment_text(row))} | не указано | {format_time(float(row.get('start', 0)))} |")

    return "\n".join(lines).rstrip() + "\n"


def build_extractive_json_artifacts(
    meeting: dict[str, Any],
    segments: list[dict[str, Any]],
    generated_at: str,
) -> dict[str, dict[str, Any]]:
    meeting_id = str(meeting.get("meeting_id"))

    decisions = []
    for i, row in enumerate(select_segments(segments, DECISION_KEYWORDS, limit=10), start=1):
        text = segment_text(row)
        decisions.append(
            {
                "decision_id": f"DEC-{i:03d}",
                "title": short_title(text),
                "decision": text,
                "status": "proposed",
                "source_refs": [source_ref(row)],
                "needs_review": True,
            }
        )

    tasks = []
    for i, row in enumerate(select_segments(segments, TASK_KEYWORDS, limit=10), start=1):
        text = segment_text(row)
        tasks.append(
            {
                "task_id": f"TASK-{i:03d}",
                "title": short_title(text),
                "description": text,
                "status": "open",
                "priority": "normal",
                "source_refs": [source_ref(row)],
                "needs_review": True,
            }
        )

    risks = []
    for i, row in enumerate(select_segments(segments, RISK_KEYWORDS, limit=8), start=1):
        text = segment_text(row)
        risks.append(
            {
                "risk_id": f"RISK-{i:03d}",
                "title": short_title(text),
                "description": text,
                "impact": "medium",
                "probability": "medium",
                "status": "open",
                "source_refs": [source_ref(row)],
                "needs_review": True,
            }
        )

    open_questions = []
    for i, row in enumerate(select_segments(segments, QUESTION_KEYWORDS, limit=8), start=1):
        text = segment_text(row)
        open_questions.append(
            {
                "question_id": f"Q-{i:03d}",
                "question": text if text.endswith("?") else short_title(text),
                "status": "open",
                "source_refs": [source_ref(row)],
                "needs_review": True,
            }
        )

    return {
        "decisions": {
            "schema_version": 1,
            "meeting_id": meeting_id,
            "generated_at": generated_at,
            "items": decisions,
        },
        "tasks": {
            "schema_version": 1,
            "meeting_id": meeting_id,
            "generated_at": generated_at,
            "items": tasks,
        },
        "risks": {
            "schema_version": 1,
            "meeting_id": meeting_id,
            "generated_at": generated_at,
            "items": risks,
        },
        "open_questions": {
            "schema_version": 1,
            "meeting_id": meeting_id,
            "generated_at": generated_at,
            "items": open_questions,
        },
    }


def read_prompt(path: Path) -> str:
    if not path.exists():
        raise MeetingArtifactsError(f"Prompt file not found: {path}", stage="preflight")
    return path.read_text(encoding="utf-8")


def build_prompt(template: str, meeting: dict[str, Any], transcript_context: str, output_hint: str) -> str:
    meeting_payload = json.dumps(
        {
            "meeting_id": meeting.get("meeting_id"),
            "title": meeting.get("title"),
            "date": meeting.get("date"),
            "participants": meeting.get("participants", []),
            "source": meeting.get("source", {}),
        },
        ensure_ascii=False,
        indent=2,
    )
    return f"""/no_think
{template}

## Данные Встречи

```json
{meeting_payload}
```

## Transcript Segments

```text
{transcript_context}
```

## Важное Ограничение Вывода

{output_hint}
"""


def ollama_generate(
    base_url: str,
    model: str,
    prompt: str,
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
    return response.json().get("response", "").strip()


def extract_json_object(text: str) -> dict[str, Any]:
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text.strip())
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise MeetingArtifactsError("Model response does not contain a JSON object.", stage="parse_json")
    return json.loads(text[start : end + 1])


def normalize_artifact_doc(raw: dict[str, Any], key: str, meeting_id: str, generated_at: str) -> dict[str, Any]:
    doc = raw.get(key)
    if not isinstance(doc, dict):
        doc = {}
    items = doc.get("items", [])
    if not isinstance(items, list):
        items = []
    return {
        "schema_version": 1,
        "meeting_id": meeting_id,
        "generated_at": generated_at,
        "items": items,
    }


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


def validate_summarized_status(meeting_dir: Path, meeting: dict[str, Any]) -> None:
    if meeting.get("processing_status") != STATUS_SUMMARIZED:
        return
    artifacts = meeting.get("artifacts", {})
    for key in ("memo", "protocol", "decisions", "tasks", "risks", "open_questions"):
        value = artifacts.get(key)
        if not value:
            raise MeetingArtifactsError(
                f"Status 'summarized' requires artifacts.{key}.",
                stage="status_rule",
            )
        path = meeting_dir / value
        if not path.exists():
            raise MeetingArtifactsError(
                f"Status 'summarized' requires existing file: {path}",
                stage="status_rule",
            )


def run(args: argparse.Namespace) -> int:
    repo_root = Path(__file__).resolve().parents[1]
    meeting_dir = resolve_meeting_dir(args.meeting_dir)
    meeting_path = meeting_dir / "meeting.json"
    schema_dir = repo_root / "configs" / "schemas"
    prompt_dir = repo_root / "configs" / "prompts"
    meeting: dict[str, Any] | None = None
    mutate_on_error = False

    try:
        if not meeting_path.exists():
            raise MeetingArtifactsError(f"meeting.json not found: {meeting_path}", stage="preflight")

        cfg = load_config()
        ollama_cfg = cfg.get("ollama", {})
        generation_cfg = cfg.get("generation", {})

        base_url = args.base_url or str(ollama_cfg.get("base_url", "http://localhost:11434"))
        model = args.model or str(ollama_cfg.get("chat_model", "qwen3:8b"))
        keep_alive = str(ollama_cfg.get("keep_alive", "24h"))
        num_ctx = int(args.num_ctx or ollama_cfg.get("generation_num_ctx", ollama_cfg.get("embedding_num_ctx", 8192)))
        temperature = float(args.temperature if args.temperature is not None else generation_cfg.get("temperature", 0.2))
        top_p = float(args.top_p if args.top_p is not None else generation_cfg.get("top_p", 0.9))

        meeting = read_json(meeting_path)
        if args.force and isinstance(meeting.get("last_error"), dict) and "timestamp" not in meeting["last_error"]:
            meeting["last_error"]["timestamp"] = now_iso()
        validate_schema(meeting, schema_dir / "meeting.schema.json")
        ensure_status_allows_run(meeting, args.force)

        transcript_path = require_artifact_file(meeting_dir, meeting, "transcript")
        segments_path = require_artifact_file(meeting_dir, meeting, "segments")
        segments = load_segments(segments_path)
        transcript_context = compact_segments(segments, args.max_transcript_chars)
        if not transcript_context:
            raise MeetingArtifactsError("Transcript context is empty.", stage="preflight")

        if args.dry_run:
            for schema_name in ARTIFACT_SCHEMAS.values():
                Draft202012Validator.check_schema(read_json(schema_dir / schema_name))
            for prompt_name in ("meeting_memo.md", "meeting_protocol.md", "meeting_artifacts_json.md"):
                read_prompt(prompt_dir / prompt_name)
            print("dry-run ok")
            print(f"meeting_dir: {meeting_dir}")
            print(f"transcript: {transcript_path}")
            print(f"segments: {segments_path}")
            print(f"segments_count: {len(segments)}")
            print(f"mode: {args.mode}")
            print(f"model: {model}")
            print(f"num_ctx: {num_ctx}")
            print(f"max_transcript_chars: {args.max_transcript_chars}")
            return 0

        mutate_on_error = True
        artifacts_dir = meeting_dir / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        generated_at = now_iso()
        if args.mode == "extractive":
            memo_text = build_extractive_memo(meeting, segments)
            protocol_text = build_extractive_protocol(meeting, segments)
            artifact_docs = build_extractive_json_artifacts(meeting, segments, generated_at)
        else:
            memo_prompt = build_prompt(
                read_prompt(prompt_dir / "meeting_memo.md"),
                meeting,
                transcript_context,
                "Верни только Markdown memo. Не добавляй рассуждения модели.",
            )
            protocol_prompt = build_prompt(
                read_prompt(prompt_dir / "meeting_protocol.md"),
                meeting,
                transcript_context,
                "Верни только Markdown протокола. Не добавляй рассуждения модели.",
            )
            json_prompt = build_prompt(
                read_prompt(prompt_dir / "meeting_artifacts_json.md"),
                meeting,
                transcript_context,
                "Верни только один JSON object. Не используй Markdown fences, пояснения и рассуждения.",
            )

            memo_text = ollama_generate(base_url, model, memo_prompt, temperature, top_p, num_ctx, keep_alive, args.timeout_sec)
            protocol_text = ollama_generate(base_url, model, protocol_prompt, temperature, top_p, num_ctx, keep_alive, args.timeout_sec)
            raw_json_text = ollama_generate(base_url, model, json_prompt, temperature, top_p, num_ctx, keep_alive, args.timeout_sec)

            raw_json_path = artifacts_dir / "generation_raw.json"
            raw_json_path.write_text(raw_json_text + "\n", encoding="utf-8")
            raw_artifacts = extract_json_object(raw_json_text)

            meeting_id = str(meeting.get("meeting_id"))
            artifact_docs = {}
            for key in ARTIFACT_SCHEMAS:
                artifact_docs[key] = normalize_artifact_doc(raw_artifacts, key, meeting_id, generated_at)

        for key, schema_name in ARTIFACT_SCHEMAS.items():
            validate_schema(artifact_docs[key], schema_dir / schema_name)

        (meeting_dir / ARTIFACT_PATHS["memo"]).write_text(memo_text.rstrip() + "\n", encoding="utf-8")
        (meeting_dir / ARTIFACT_PATHS["protocol"]).write_text(protocol_text.rstrip() + "\n", encoding="utf-8")
        for key, doc in artifact_docs.items():
            write_json_atomic(meeting_dir / ARTIFACT_PATHS[key], doc)

        artifacts = dict(meeting.get("artifacts", {}))
        artifacts.update(ARTIFACT_PATHS)
        meeting["artifacts"] = artifacts
        meeting["processing_status"] = STATUS_SUMMARIZED
        meeting["updated_at"] = now_iso()
        meeting.pop("last_error", None)

        validate_schema(meeting, schema_dir / "meeting.schema.json")
        validate_summarized_status(meeting_dir, meeting)
        write_json_atomic(meeting_path, meeting)

        print("meeting artifacts generated")
        print(f"memo: {meeting_dir / ARTIFACT_PATHS['memo']}")
        print(f"protocol: {meeting_dir / ARTIFACT_PATHS['protocol']}")
        print(f"decisions: {meeting_dir / ARTIFACT_PATHS['decisions']}")
        print(f"tasks: {meeting_dir / ARTIFACT_PATHS['tasks']}")
        print(f"risks: {meeting_dir / ARTIFACT_PATHS['risks']}")
        print(f"open_questions: {meeting_dir / ARTIFACT_PATHS['open_questions']}")
        return 0
    except MeetingArtifactsError as exc:
        mark_failed(meeting_path, meeting, exc, exc.stage, mutate_on_error)
        print(f"ERROR[{exc.stage}]: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        mark_failed(meeting_path, meeting, exc, "runtime", mutate_on_error)
        print(f"ERROR[runtime]: {exc}", file=sys.stderr)
        return 1


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate MeetingAgent memo, protocol and structured JSON artifacts from a transcribed meeting.",
    )
    parser.add_argument("--meeting-dir", required=True, help="Path to meeting folder.")
    parser.add_argument("--model", default=None, help="Ollama chat model. Defaults to config ollama.chat_model.")
    parser.add_argument("--base-url", default=None, help="Ollama base URL. Defaults to config ollama.base_url.")
    parser.add_argument("--num-ctx", type=int, default=None, help="Ollama generation context window.")
    parser.add_argument("--temperature", type=float, default=None, help="Generation temperature.")
    parser.add_argument("--top-p", type=float, default=None, help="Generation top_p.")
    parser.add_argument("--timeout-sec", type=int, default=900, help="HTTP timeout per Ollama generation call.")
    parser.add_argument("--max-transcript-chars", type=int, default=12000, help="Max compact transcript chars sent to LLM.")
    parser.add_argument(
        "--mode",
        choices=("extractive", "ollama"),
        default="extractive",
        help="extractive is fast deterministic MVP; ollama uses local LLM prompts.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate inputs, prompts and schemas without generation.")
    parser.add_argument("--force", action="store_true", help="Regenerate artifacts when meeting is already summarized or failed.")
    return parser.parse_args(argv)


def main() -> int:
    return run(parse_args(sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
