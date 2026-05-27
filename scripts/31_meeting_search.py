from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


WORK_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = WORK_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from asu_june_bot.core.config import load_config, resolve_work_path  # noqa: E402


DEFAULT_CHUNKS_PATH = "data/meeting_chunks.jsonl"
DEFAULT_TOP_K = 5
TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9]{2,}")
MEETING_SOURCE_TYPES = {
    "meeting_chunk",
    "meeting_decision",
    "meeting_action_item",
    "meeting_risk",
    "meeting_open_question",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Meeting chunks file not found: {path}")

    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fp:
        for line_no, line in enumerate(fp, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc
            if row.get("source_type") in MEETING_SOURCE_TYPES and str(row.get("text") or "").strip():
                rows.append(row)
    return rows


def tokenize(text: str) -> list[str]:
    return [token.lower().replace("ё", "е") for token in TOKEN_RE.findall(text)]


def row_search_text(row: dict[str, Any]) -> str:
    values: list[str] = [
        str(row.get("text") or ""),
        str(row.get("meeting_title") or ""),
        str(row.get("topic") or ""),
        str(row.get("semantic_type") or ""),
        str(row.get("artifact_type") or ""),
        str(row.get("artifact_id") or ""),
        str(row.get("status") or ""),
        str(row.get("owner") or ""),
        str(row.get("meeting_id") or ""),
    ]
    speaker_names = row.get("speaker_names") or []
    if isinstance(speaker_names, list):
        values.extend(str(item) for item in speaker_names)
    return "\n".join(values)


def lexical_score(query: str, row: dict[str, Any]) -> float:
    query_tokens = tokenize(query)
    if not query_tokens:
        return 0.0

    haystack = row_search_text(row)
    haystack_lower = haystack.lower().replace("ё", "е")
    haystack_tokens = tokenize(haystack)
    haystack_set = set(haystack_tokens)

    overlap = sum(1 for token in query_tokens if token in haystack_set)
    score = overlap / max(len(set(query_tokens)), 1)

    query_lower = query.lower().replace("ё", "е").strip()
    if query_lower and query_lower in haystack_lower:
        score += 1.0

    source_type = str(row.get("source_type") or "").lower()
    semantic_type = str(row.get("semantic_type") or "").lower()
    query_set = set(query_tokens)
    semantic_boosts = {
        "decision": {"решение", "решения", "решили", "приняли"},
        "action_item": {"задача", "задачи", "сделать", "ответственный"},
        "risk": {"риск", "риски", "опасность", "проблема"},
        "open_question": {"вопрос", "вопросы", "открыто", "уточнить"},
    }
    source_boosts = {
        "meeting_decision": semantic_boosts["decision"],
        "meeting_action_item": semantic_boosts["action_item"],
        "meeting_risk": semantic_boosts["risk"],
        "meeting_open_question": semantic_boosts["open_question"],
    }
    if source_type in source_boosts and query_set.intersection(source_boosts[source_type]):
        score += 1.0
    if semantic_type in semantic_boosts and query_set.intersection(semantic_boosts[semantic_type]):
        score += 0.35

    topic = str(row.get("topic") or "")
    if topic and any(token in tokenize(topic) for token in query_tokens):
        score += 0.15

    return round(score, 6)


def make_preview(text: str, max_chars: int = 280) -> str:
    text = " ".join(str(text or "").split())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def search_meeting_chunks(
    rows: list[dict[str, Any]],
    query: str,
    top_k: int,
    meeting_id: str | None = None,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for row in rows:
        if meeting_id and row.get("meeting_id") != meeting_id:
            continue
        score = lexical_score(query, row)
        if score <= 0:
            continue
        matches.append({"score": score, "row": row})

    matches.sort(
        key=lambda item: (
            -float(item["score"]),
            str(item["row"].get("meeting_id") or ""),
            str(item["row"].get("timestamp_start") or ""),
            str(item["row"].get("chunk_id") or ""),
        )
    )

    results: list[dict[str, Any]] = []
    for rank, item in enumerate(matches[:top_k], start=1):
        row = item["row"]
        results.append(
            {
                "rank": rank,
                "score": item["score"],
                "source_type": row.get("source_type"),
                "meeting_id": row.get("meeting_id"),
                "meeting_title": row.get("meeting_title"),
                "timestamp_start": row.get("timestamp_start"),
                "timestamp_end": row.get("timestamp_end"),
                "speaker_names": row.get("speaker_names") or [],
                "topic": row.get("topic"),
                "semantic_type": row.get("semantic_type"),
                "artifact_type": row.get("artifact_type"),
                "artifact_id": row.get("artifact_id"),
                "chunk_id": row.get("chunk_id"),
                "text_preview": make_preview(str(row.get("text") or "")),
            }
        )
    return results


def format_result(result: dict[str, Any]) -> str:
    speakers = result.get("speaker_names") or []
    speaker_text = ", ".join(str(item) for item in speakers) if speakers else "speaker unknown"
    title = result.get("meeting_title") or result.get("meeting_id") or "meeting"
    time_start = result.get("timestamp_start") or "??:??:??"
    time_end = result.get("timestamp_end") or "??:??:??"
    topic = result.get("topic") or "Без темы"
    semantic_type = result.get("semantic_type") or "unknown"
    source_type = result.get("source_type") or "meeting"
    artifact_id = result.get("artifact_id")
    artifact_suffix = f" | {artifact_id}" if artifact_id else ""
    return (
        f"{result['rank']}. score={result['score']:.3f} | {title} | {time_start}-{time_end} | "
        f"{speaker_text} | {source_type} | {semantic_type}{artifact_suffix} | {topic}\n"
        f"   {result['text_preview']}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke search over exported meeting chunks")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--chunks-path", default=DEFAULT_CHUNKS_PATH)
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--meeting-id")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    args = parser.parse_args()

    cfg = load_config()
    chunks_path = resolve_work_path(cfg, args.chunks_path)
    rows = read_jsonl(chunks_path)
    results = search_meeting_chunks(rows, args.query, max(args.top_k, 1), args.meeting_id)

    if args.json:
        print(
            json.dumps(
                {
                    "query": args.query,
                    "chunks_path": str(chunks_path),
                    "meeting_id": args.meeting_id,
                    "count": len(results),
                    "results": results,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    if not results:
        print(f"Ничего не найдено по встречам: {args.query}")
        return

    print(f"Найдено фрагментов: {len(results)}")
    for result in results:
        print(format_result(result))


if __name__ == "__main__":
    main()
