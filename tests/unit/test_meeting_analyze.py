from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "29_analyze_meeting.py"


def load_module():
    spec = importlib.util.spec_from_file_location("meeting_analyze", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_normalize_items_adds_source_refs_with_timestamps() -> None:
    module = load_module()
    chunks = [
        {
            "chunk_id": "meeting-chunk-0001",
            "start": 12.5,
            "end": 42.0,
            "text": "Решили разделить поддержку по линиям.",
        }
    ]

    items = module.normalize_items(
        "decisions",
        [
            {
                "title": "Линии поддержки",
                "decision": "Разделить поддержку по линиям.",
                "status": "accepted",
                "chunk_id": "meeting-chunk-0001",
                "needs_review": False,
            }
        ],
        chunks,
    )

    assert items[0]["decision_id"] == "DEC-001"
    assert items[0]["source_refs"][0]["kind"] == "rag_source"
    assert items[0]["source_refs"][0]["start"] == 12.5
    assert items[0]["source_refs"][0]["end"] == 42.0


def test_merge_partials_preserves_chunk_id_for_source_mapping() -> None:
    module = load_module()

    reduced = module.merge_partials(
        [
            {
                "chunk_id": "meeting-chunk-0002",
                "summary_bullets": ["Обсудили зоны ответственности."],
                "tasks": [
                    {
                        "title": "Перерисовать схему",
                        "description": "Перерисовать схему уровней поддержки.",
                    }
                ],
            },
            {
                "chunk_id": "meeting-chunk-0003",
                "summary_bullets": [],
                "tasks": [],
            }
        ]
    )

    assert reduced["summary_bullets"] == ["Обсудили зоны ответственности."]
    assert reduced["tasks"][0]["chunk_id"] == "meeting-chunk-0002"
