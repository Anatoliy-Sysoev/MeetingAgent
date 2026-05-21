from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from rag_common import load_config
from rag_ollama import ollama_generate as shared_ollama_generate


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


def meeting_payload(meeting: dict[str, Any]) -> str:
    return json.dumps(
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


def render_prompt_template(template: str, values: dict[str, str]) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{" + key + "}", value)
    return rendered


def build_segment_windows(
    segments: list[dict[str, Any]],
    window_seconds: int,
    overlap_seconds: int,
    min_last_window_seconds: int = 60,
) -> list[dict[str, Any]]:
    if window_seconds <= 0:
        raise MeetingArtifactsError("--window-seconds must be positive.", stage="preflight")
    if overlap_seconds < 0 or overlap_seconds >= window_seconds:
        raise MeetingArtifactsError("--window-overlap-seconds must be >= 0 and less than --window-seconds.", stage="preflight")

    first_start = float(segments[0].get("start", 0))
    last_end = max(float(row.get("end", row.get("start", 0))) for row in segments)
    step = window_seconds - overlap_seconds
    windows: list[dict[str, Any]] = []
    window_start = first_start
    window_number = 1

    while window_start <= last_end:
        window_end = window_start + window_seconds
        rows = [
            row
            for row in segments
            if float(row.get("start", 0)) < window_end and float(row.get("end", row.get("start", 0))) >= window_start
        ]
        if rows:
            windows.append(
                {
                    "window_id": f"W{window_number:02d}",
                    "start": window_start,
                    "end": min(window_end, last_end),
                    "segments": rows,
                }
            )
            window_number += 1
        window_start += step

    if len(windows) > 1 and windows[-1]["end"] - windows[-1]["start"] < min_last_window_seconds:
        previous = windows[-2]
        last = windows.pop()
        merged: dict[int, dict[str, Any]] = {
            int(row.get("segment_index", 0)): row
            for row in previous["segments"] + last["segments"]
        }
        previous["end"] = last["end"]
        previous["segments"] = [merged[idx] for idx in sorted(merged)]

    return windows


def compact_window_segments(window: dict[str, Any]) -> str:
    lines = [
        f"window_id: {window['window_id']}",
        f"window_start: {format_time(float(window['start']))}",
        f"window_end: {format_time(float(window['end']))}",
        "",
    ]
    for row in window["segments"]:
        text = segment_text(row)
        if not text:
            continue
        start = float(row.get("start", 0))
        end = float(row.get("end", start))
        segment_index = int(row.get("segment_index", 0))
        source = row.get("source", "MIX")
        lines.append(f"[{segment_index:04d}] [{format_time(start)}-{format_time(end)}] [{source}] {text}")
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
    return f"""/no_think
{template}

## Данные Встречи

```json
{meeting_payload(meeting)}
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
    return shared_ollama_generate(
        base_url,
        model,
        prompt,
        temperature,
        top_p,
        timeout=timeout_sec,
        num_ctx=num_ctx,
        keep_alive=keep_alive,
    )


def extract_json_object(text: str) -> dict[str, Any]:
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text.strip())
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise MeetingArtifactsError("Model response does not contain a JSON object.", stage="parse_json")
    return json.loads(text[start : end + 1])


def sanitize_artifact_items(key: str, items: list[Any]) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        if key == "tasks" and "assignee" in row and "owner" not in row:
            row["owner"] = row.pop("assignee")
        else:
            row.pop("assignee", None)
        if row.get("due_date") == "не указано":
            row.pop("due_date", None)
        if "source_refs" not in row or not isinstance(row["source_refs"], list):
            row["source_refs"] = []
        sanitized.append(row)
    return sanitized


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
        "items": sanitize_artifact_items(key, items),
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


def markdown_cell(value: Any) -> str:
    text = str(value if value is not None else "не указано")
    return text.replace("|", "\\|").replace("\n", " ").strip() or "не указано"


def first_source_time(item: dict[str, Any]) -> str:
    refs = item.get("source_refs", [])
    if not refs:
        return "не указано"
    start = refs[0].get("start")
    if isinstance(start, (int, float)):
        return f"[{format_time(float(start))}]"
    return "не указано"


def render_deterministic_documents(
    meeting: dict[str, Any],
    artifact_docs: dict[str, dict[str, Any]],
    topics: list[dict[str, Any]],
) -> tuple[str, str]:
    title = meeting.get("title", meeting.get("meeting_id", "Встреча"))
    date = meeting.get("date", "")
    meeting_id = meeting.get("meeting_id", "")
    participants = ", ".join(meeting.get("participants", [])) or "не указаны"
    decisions = artifact_docs.get("decisions", {}).get("items", [])
    tasks = artifact_docs.get("tasks", {}).get("items", [])
    risks = artifact_docs.get("risks", {}).get("items", [])
    questions = artifact_docs.get("open_questions", {}).get("items", [])

    memo_lines = [
        f"# Memo: {title}",
        "",
        f"- Дата: {date}",
        f"- meeting_id: `{meeting_id}`",
        f"- Участники: {participants}",
        "- Режим: map-reduce-render, требуется ревью пунктов с `needs_review = true`",
        "",
        "## 1. Краткая Суть",
        "",
    ]
    if topics:
        memo_lines.extend(f"- {topic.get('title', 'Тема')}: {topic.get('summary', '')}" for topic in topics[:5])
    else:
        memo_lines.append("- Краткая суть не сформирована: в REDUCE-результате нет topics.")

    memo_lines.extend(["", "## 2. Основные Итоги", ""])
    for item in decisions[:5]:
        memo_lines.append(f"- {item.get('decision_id')}. {item.get('decision')} Источник: {first_source_time(item)}")
    for item in tasks[:5]:
        memo_lines.append(f"- {item.get('task_id')}. {item.get('description', item.get('title'))} Источник: {first_source_time(item)}")

    memo_lines.extend(["", "## 3. Принятые Решения", ""])
    memo_lines.extend(
        f"- {item.get('decision_id')}. {item.get('decision')} Источник: {first_source_time(item)}"
        for item in decisions
    )
    if not decisions:
        memo_lines.append("- Не выявлены.")

    memo_lines.extend(["", "## 4. Поручения", ""])
    memo_lines.extend(
        f"- {item.get('task_id')}. {item.get('description', item.get('title'))} Ответственный: {item.get('owner', 'не указано')}. Срок: {item.get('due_date', 'не указано')}. Источник: {first_source_time(item)}"
        for item in tasks
    )
    if not tasks:
        memo_lines.append("- Не выявлены.")

    memo_lines.extend(["", "## 5. Риски И Открытые Вопросы", ""])
    memo_lines.extend(f"- {item.get('risk_id')}. {item.get('description')} Источник: {first_source_time(item)}" for item in risks)
    memo_lines.extend(f"- {item.get('question_id')}. {item.get('question')} Источник: {first_source_time(item)}" for item in questions)
    if not risks and not questions:
        memo_lines.append("- Существенные риски и открытые вопросы не выявлены.")

    memo_lines.extend(["", "## 6. Следующие Действия", ""])
    if tasks:
        memo_lines.extend(f"- {item.get('task_id')}. {item.get('description', item.get('title'))}" for item in tasks)
    else:
        memo_lines.append("- Проверить memo/protocol вручную и подтвердить отсутствие поручений.")

    protocol_lines = [
        f"# Протокол встречи: {title}",
        "",
        "## 1. Общие Сведения",
        "",
        "| Поле | Значение |",
        "| --- | --- |",
        f"| Дата | {markdown_cell(date)} |",
        f"| meeting_id | `{markdown_cell(meeting_id)}` |",
        f"| Участники | {markdown_cell(participants)} |",
        f"| Тема | {markdown_cell(title)} |",
        "",
        "## 2. Повестка",
        "",
    ]
    if topics:
        protocol_lines.extend(f"- {topic.get('title', 'Тема')}" for topic in topics)
    else:
        protocol_lines.append("- Повестка не сформирована.")

    protocol_lines.extend(["", "## 3. Ход Обсуждения", ""])
    if topics:
        for topic in topics:
            protocol_lines.append(f"### {topic.get('title', 'Тема')}")
            protocol_lines.append("")
            protocol_lines.append(f"- Предмет: {topic.get('summary', 'не указано')}")
            protocol_lines.append(f"- Источник: {first_source_time(topic)}")
            protocol_lines.append("")
    else:
        protocol_lines.append("Темы не выделены.")

    protocol_lines.extend(["", "## 4. Принятые Решения", "", "| ID | Решение | Статус | Источник |", "| --- | --- | --- | --- |"])
    for item in decisions:
        protocol_lines.append(f"| {markdown_cell(item.get('decision_id'))} | {markdown_cell(item.get('decision'))} | {markdown_cell(item.get('status'))} | {markdown_cell(first_source_time(item))} |")

    protocol_lines.extend(["", "## 5. Поручения", "", "| ID | Что Сделать | Ответственный | Срок | Статус | Источник |", "| --- | --- | --- | --- | --- | --- |"])
    for item in tasks:
        protocol_lines.append(
            f"| {markdown_cell(item.get('task_id'))} | {markdown_cell(item.get('description', item.get('title')))} | {markdown_cell(item.get('owner', 'не указано'))} | {markdown_cell(item.get('due_date', 'не указано'))} | {markdown_cell(item.get('status'))} | {markdown_cell(first_source_time(item))} |"
        )

    protocol_lines.extend(["", "## 6. Риски", "", "| ID | Риск | Влияние | Вероятность | Мера | Источник |", "| --- | --- | --- | --- | --- | --- |"])
    for item in risks:
        protocol_lines.append(
            f"| {markdown_cell(item.get('risk_id'))} | {markdown_cell(item.get('description'))} | {markdown_cell(item.get('impact'))} | {markdown_cell(item.get('probability'))} | {markdown_cell(item.get('mitigation', 'не указано'))} | {markdown_cell(first_source_time(item))} |"
        )

    protocol_lines.extend(["", "## 7. Открытые Вопросы", "", "| ID | Вопрос | Владелец | Статус | Источник |", "| --- | --- | --- | --- | --- |"])
    for item in questions:
        protocol_lines.append(
            f"| {markdown_cell(item.get('question_id'))} | {markdown_cell(item.get('question'))} | {markdown_cell(item.get('owner', 'не указано'))} | {markdown_cell(item.get('status'))} | {markdown_cell(first_source_time(item))} |"
        )

    protocol_lines.extend(["", "## 8. Итог", ""])
    protocol_lines.append("Итоги сформированы из финальных JSON-артефактов. Пункты с `needs_review = true` требуют ручной проверки по указанным таймкодам.")

    return "\n".join(memo_lines).rstrip() + "\n", "\n".join(protocol_lines).rstrip() + "\n"


def run_ollama_map_reduce(
    meeting_dir: Path,
    meeting: dict[str, Any],
    segments: list[dict[str, Any]],
    prompt_dir: Path,
    base_url: str,
    model: str,
    temperature: float,
    top_p: float,
    num_ctx: int,
    keep_alive: str,
    timeout_sec: int,
    generated_at: str,
    window_seconds: int,
    window_overlap_seconds: int,
) -> tuple[str, str, dict[str, dict[str, Any]]]:
    partials_dir = meeting_dir / "_partials"
    shutil.rmtree(partials_dir, ignore_errors=True)
    partials_dir.mkdir(parents=True, exist_ok=True)
    map_template = read_prompt(prompt_dir / "meeting_map_extract.md")
    reduce_template = read_prompt(prompt_dir / "meeting_reduce_artifacts.md")
    windows = build_segment_windows(segments, window_seconds, window_overlap_seconds)
    if not windows:
        raise MeetingArtifactsError("No transcript windows were built.", stage="map_reduce")

    partials: list[dict[str, Any]] = []
    payload = meeting_payload(meeting)
    for window in windows:
        window_id = str(window["window_id"])
        prompt = render_prompt_template(
            map_template,
            {
                "window_id": window_id,
                "meeting_payload": payload,
                "transcript_window": compact_window_segments(window),
            },
        )
        t_start = time.time()
        raw_text = ollama_generate(base_url, model, prompt, temperature, top_p, num_ctx, keep_alive, timeout_sec)
        elapsed = time.time() - t_start
        print(f"[MAP] window {window_id}: {elapsed:.1f}s")
        (partials_dir / f"window_{window_id}.raw.txt").write_text(raw_text + "\n", encoding="utf-8")
        partial = extract_json_object(raw_text)
        partial.setdefault("window_id", window_id)
        write_json_atomic(partials_dir / f"window_{window_id}.json", partial)
        partials.append(partial)

    reduce_prompt = render_prompt_template(
        reduce_template,
        {
            "partial_artifacts_json": json.dumps(partials, ensure_ascii=False, indent=2),
        },
    )
    t_start = time.time()
    reduce_raw = ollama_generate(base_url, model, reduce_prompt, temperature, top_p, num_ctx, keep_alive, timeout_sec)
    elapsed = time.time() - t_start
    print(f"[REDUCE]: {elapsed:.1f}s")
    (partials_dir / "reduce.raw.txt").write_text(reduce_raw + "\n", encoding="utf-8")
    reduced = extract_json_object(reduce_raw)
    write_json_atomic(partials_dir / "reduce.json", reduced)

    meeting_id = str(meeting.get("meeting_id"))
    artifact_docs = {
        key: normalize_artifact_doc(reduced, key, meeting_id, generated_at)
        for key in ARTIFACT_SCHEMAS
    }
    topics_doc = reduced.get("topics", {})
    topics = topics_doc.get("items", []) if isinstance(topics_doc, dict) else []
    if not isinstance(topics, list):
        topics = []
    memo_text, protocol_text = render_deterministic_documents(meeting, artifact_docs, topics)
    return memo_text, protocol_text, artifact_docs


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
            prompt_names = ["meeting_memo.md", "meeting_protocol.md", "meeting_artifacts_json.md"]
            if args.mode == "ollama-map-reduce":
                prompt_names.extend(
                    [
                        "meeting_map_extract.md",
                        "meeting_reduce_artifacts.md",
                        "meeting_render_documents.md",
                    ]
                )
                windows = build_segment_windows(segments, args.window_seconds, args.window_overlap_seconds)
                print(f"windows_count: {len(windows)}")
            for prompt_name in prompt_names:
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
        elif args.mode == "ollama":
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
        else:
            memo_text, protocol_text, artifact_docs = run_ollama_map_reduce(
                meeting_dir=meeting_dir,
                meeting=meeting,
                segments=segments,
                prompt_dir=prompt_dir,
                base_url=base_url,
                model=model,
                temperature=temperature,
                top_p=top_p,
                num_ctx=num_ctx,
                keep_alive=keep_alive,
                timeout_sec=args.timeout_sec,
                generated_at=generated_at,
                window_seconds=args.window_seconds,
                window_overlap_seconds=args.window_overlap_seconds,
            )

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
        choices=("extractive", "ollama", "ollama-map-reduce"),
        default="extractive",
        help="extractive is a deterministic scaffold; ollama uses one-pass prompts; ollama-map-reduce uses windowed extraction.",
    )
    parser.add_argument("--window-seconds", type=int, default=360, help="Window size for ollama-map-reduce MAP step.")
    parser.add_argument("--window-overlap-seconds", type=int, default=30, help="Window overlap for ollama-map-reduce MAP step.")
    parser.add_argument("--dry-run", action="store_true", help="Validate inputs, prompts and schemas without generation.")
    parser.add_argument("--force", action="store_true", help="Regenerate artifacts when meeting is already summarized or failed.")
    return parser.parse_args(argv)


def main() -> int:
    return run(parse_args(sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
