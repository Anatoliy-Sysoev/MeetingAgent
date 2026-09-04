from __future__ import annotations

import json

import pytest

from meeting_agent.speakers import (
    DuplicateSpeakerProfileError,
    SpeakerDirectory,
    SpeakerProfileNotFoundError,
)


def test_speaker_directory_crud_and_search(tmp_path) -> None:
    path = tmp_path / "private" / "speakers.json"
    directory = SpeakerDirectory(path)

    created = directory.create(
        {"name": "Иван Иванов", "role": "PO", "company": "Acme", "aliases": ["Ваня"]}
    )

    assert created["speaker_id"].startswith("spk_")
    assert directory.list(query="acme")[0]["name"] == "Иван Иванов"
    updated = directory.update(
        created["speaker_id"],
        {"name": "Иван Иванов", "role": "Lead", "company": "Acme"},
    )
    assert updated["role"] == "Lead"
    directory.delete(created["speaker_id"])
    assert directory.list() == []
    with pytest.raises(SpeakerProfileNotFoundError):
        directory.delete(created["speaker_id"])


def test_speaker_directory_rejects_normalized_duplicate(tmp_path) -> None:
    directory = SpeakerDirectory(tmp_path / "speakers.json")
    directory.create({"name": "  Иван   Иванов ", "company": "Компания"})

    with pytest.raises(DuplicateSpeakerProfileError):
        directory.create({"name": "иван иванов", "company": "  компания "})


def test_speaker_directory_write_is_atomic_and_path_free(tmp_path) -> None:
    path = tmp_path / "speakers.json"
    directory = SpeakerDirectory(path)
    profile = directory.create({"name": "Public DTO"})

    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["schema_version"] == 1
    assert profile == document["profiles"][0]
    assert list(tmp_path.glob(".speaker-directory.*.tmp")) == []
    assert str(tmp_path) not in json.dumps(profile)


def test_speaker_directory_enforces_bounded_read(tmp_path) -> None:
    path = tmp_path / "speakers.json"
    path.write_text("x" * 100, encoding="utf-8")
    directory = SpeakerDirectory(path, max_bytes=10)

    with pytest.raises(ValueError, match="size limit"):
        directory.list()


def test_speaker_directory_rejects_malformed_stored_profile(tmp_path) -> None:
    path = tmp_path / "speakers.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "profiles": [{"speaker_id": "../../escape", "name": "Broken"}],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="profile id"):
        SpeakerDirectory(path).list()
