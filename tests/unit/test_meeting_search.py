from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "31_meeting_search.py"


def load_module():
    spec = importlib.util.spec_from_file_location("meeting_search", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_read_jsonl_keeps_only_meeting_chunks(tmp_path: Path) -> None:
    module = load_module()
    chunks_path = tmp_path / "meeting_chunks.jsonl"
    write_jsonl(
        chunks_path,
        [
            {
                "chunk_id": "m1-c1",
                "source_type": "meeting_chunk",
                "text": "Решили использовать общий endpoint organization.",
            },
            {
                "chunk_id": "doc-c1",
                "source_type": "project_doc",
                "text": "Не встреча.",
            },
        ],
    )

    rows = module.read_jsonl(chunks_path)

    assert [row["chunk_id"] for row in rows] == ["m1-c1"]


def test_read_jsonl_keeps_structured_meeting_artifacts(tmp_path: Path) -> None:
    module = load_module()
    chunks_path = tmp_path / "meeting_chunks.jsonl"
    write_jsonl(
        chunks_path,
        [
            {
                "chunk_id": "m1-decision-1",
                "source_type": "meeting_decision",
                "text": "Решение: разделить поддержку по линиям.",
            },
            {
                "chunk_id": "runtime-1",
                "source_type": "runtime_export",
                "text": "Не встреча.",
            },
        ],
    )

    rows = module.read_jsonl(chunks_path)

    assert [row["chunk_id"] for row in rows] == ["m1-decision-1"]


def test_search_meeting_chunks_finds_decision_and_keeps_timestamps() -> None:
    module = load_module()
    rows = [
        {
            "chunk_id": "m1-c1",
            "source_type": "meeting_chunk",
            "meeting_id": "2026-05-26__status",
            "meeting_title": "Статус АСУ",
            "timestamp_start": "00:01:00",
            "timestamp_end": "00:02:10",
            "speaker_names": ["SPEAKER_UNKNOWN"],
            "topic": "Endpoint organization",
            "semantic_type": "decision",
            "text": "Решили использовать общий endpoint organization для единой модели данных.",
        },
        {
            "chunk_id": "m2-c1",
            "source_type": "meeting_chunk",
            "meeting_id": "2026-05-27__other",
            "meeting_title": "Другая встреча",
            "timestamp_start": "00:03:00",
            "timestamp_end": "00:04:00",
            "speaker_names": [],
            "topic": "Общие вопросы",
            "semantic_type": "discussion",
            "text": "Обсуждали календарь отпусков.",
        },
    ]

    results = module.search_meeting_chunks(rows, "какое решение по organization", top_k=3)

    assert results[0]["chunk_id"] == "m1-c1"
    assert results[0]["timestamp_start"] == "00:01:00"
    assert results[0]["semantic_type"] == "decision"
    assert "endpoint organization" in results[0]["text_preview"]


def test_search_meeting_chunks_filters_by_meeting_id() -> None:
    module = load_module()
    rows = [
        {
            "chunk_id": "m1-c1",
            "source_type": "meeting_chunk",
            "meeting_id": "meeting-a",
            "text": "Сергей должен проверить LDAP.",
            "semantic_type": "action_item",
        },
        {
            "chunk_id": "m2-c1",
            "source_type": "meeting_chunk",
            "meeting_id": "meeting-b",
            "text": "Сергей должен подготовить отчет.",
            "semantic_type": "action_item",
        },
    ]

    results = module.search_meeting_chunks(rows, "задачи Сергей", top_k=5, meeting_id="meeting-b")

    assert [result["chunk_id"] for result in results] == ["m2-c1"]


def test_search_prioritizes_structured_decisions() -> None:
    module = load_module()
    rows = [
        {
            "chunk_id": "m1-chunk",
            "source_type": "meeting_chunk",
            "meeting_id": "meeting-a",
            "text": "Обсуждали решение по линиям поддержки.",
            "semantic_type": "discussion",
        },
        {
            "chunk_id": "m1-decision",
            "source_type": "meeting_decision",
            "artifact_id": "DEC-001",
            "meeting_id": "meeting-a",
            "text": "Решение: разделить поддержку по линиям.",
            "semantic_type": "decision",
        },
    ]

    results = module.search_meeting_chunks(rows, "какие решения по поддержке", top_k=2)

    assert results[0]["chunk_id"] == "m1-decision"
    assert results[0]["source_type"] == "meeting_decision"
    assert results[0]["artifact_id"] == "DEC-001"
