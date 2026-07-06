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
            "speakers": ["SPEAKER_01"],
            "utterance_ids": ["utt-000001", "utt-000002"],
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
                "confidence": 0.83,
                "needs_review": False,
            }
        ],
        chunks,
        {"speaker_mapping": {"SPEAKER_01": {"name": "PRIVATE_PERSON_1", "role": "Lead"}}},
    )

    assert items[0]["decision_id"] == "DEC-001"
    assert items[0]["confidence"] == 0.83
    assert items[0]["needs_review"] is False
    assert items[0]["source_refs"][0]["kind"] == "rag_source"
    assert items[0]["source_refs"][0]["chunk_id"] == "meeting-chunk-0001"
    assert items[0]["source_refs"][0]["start"] == 12.5
    assert items[0]["source_refs"][0]["end"] == 42.0
    assert items[0]["source_refs"][0]["timecode_start"] == "00:00:12"
    assert items[0]["source_refs"][0]["speakers"] == ["SPEAKER_01"]
    assert items[0]["source_refs"][0]["speaker_names"] == ["PRIVATE_PERSON_1"]
    assert items[0]["source_refs"][0]["utterance_ids"] == ["utt-000001", "utt-000002"]


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


def test_render_summary_and_protocol_include_source_confidence_and_speaker() -> None:
    module = load_module()
    meeting = {
        "meeting_id": "2026-01-15__kickoff",
        "title": "Kickoff",
        "date": "2026-01-15",
        "speaker_mapping": {"SPEAKER_01": {"name": "PRIVATE_PERSON_4", "role": "Lead"}},
    }
    chunks = [
        {
            "chunk_id": "chunk-1",
            "start": 15.0,
            "end": 25.0,
            "speakers": ["SPEAKER_01"],
            "utterance_ids": ["utt-1"],
            "text": "[SPEAKER_01] Нужно подготовить протокол.",
        }
    ]
    reduced = {"summary_bullets": ["Обсудили протокол."], "_source_chunks": chunks}
    docs = {
        "decisions": {"items": []},
        "tasks": {
            "items": module.normalize_items(
                "tasks",
                [
                    {
                        "title": "Подготовить протокол",
                        "description": "Подготовить протокол встречи.",
                        "owner": "Антон",
                        "confidence": 0.91,
                        "needs_review": False,
                        "chunk_id": "chunk-1",
                    }
                ],
                chunks,
                meeting,
            )
        },
        "risks": {"items": []},
        "open_questions": {"items": []},
    }

    summary = module.render_summary(meeting, reduced, docs)
    protocol = module.render_protocol(meeting, docs)

    assert "[00:00:15, PRIVATE_PERSON_4]" in summary
    assert "confidence=0.91; ok" in summary
    assert "[00:00:15, PRIVATE_PERSON_4]" in protocol
    assert "confidence=0.91; ok" in protocol
