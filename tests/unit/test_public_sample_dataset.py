from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = ROOT / "examples" / "meeting_dataset" / "synthetic-support-handoff"


def _read_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _validate(schema_name: str, payload: dict) -> None:
    schema = _read_json(ROOT / "configs" / "schemas" / schema_name)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)


def test_public_sample_meeting_dataset_files_exist() -> None:
    expected = [
        "meeting.json",
        "transcript/segments.jsonl",
        "transcript/speaker_transcript.jsonl",
        "transcript/transcript.md",
        "artifacts/summary.md",
        "artifacts/protocol.md",
        "artifacts/decisions.json",
        "artifacts/tasks.json",
        "artifacts/risks.json",
        "artifacts/open_questions.json",
    ]

    for rel_path in expected:
        assert (DATASET_DIR / rel_path).exists(), rel_path


def test_public_sample_meeting_dataset_matches_schemas() -> None:
    _validate("meeting.schema.json", _read_json(DATASET_DIR / "meeting.json"))
    _validate("meeting.decisions.schema.json", _read_json(DATASET_DIR / "artifacts" / "decisions.json"))
    _validate("meeting.tasks.schema.json", _read_json(DATASET_DIR / "artifacts" / "tasks.json"))
    _validate("meeting.risks.schema.json", _read_json(DATASET_DIR / "artifacts" / "risks.json"))
    _validate(
        "meeting.open_questions.schema.json",
        _read_json(DATASET_DIR / "artifacts" / "open_questions.json"),
    )


def test_public_sample_meeting_dataset_has_no_private_markers() -> None:
    text = "\n".join(path.read_text(encoding="utf-8") for path in DATASET_DIR.rglob("*") if path.is_file())
    forbidden = [
        "C:\\",
        "Users\\",
        "Сотрудник",
        "НОВАТЭК",
        "НТК",
        "АСУ",
        "sk-",
        "token",
        ".env",
    ]

    for marker in forbidden:
        assert marker not in text


def test_public_sample_dataset_readme_linked_from_root_readme() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "examples/meeting_dataset/README.md" in readme
