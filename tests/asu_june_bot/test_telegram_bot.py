from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.telegram_bot import _parse_allowed_chat_ids, _split_message, format_chat_payload  # noqa: E402


def test_split_message_keeps_short_message() -> None:
    assert _split_message("short", limit=100) == ["short"]


def test_split_message_splits_long_message() -> None:
    parts = _split_message("a" * 250, limit=100)

    assert len(parts) == 3
    assert "" not in parts
    assert all(len(part) <= 100 for part in parts)


def test_format_chat_payload_includes_status_answer_and_sources() -> None:
    payload = {
        "status": "answered",
        "answer": "Краткий ответ. [S1]",
        "sources": [
            {
                "source_ref": "S1",
                "title": "ЦП УПКС_СоИ_AD",
                "section": "Авторизация",
            }
        ],
    }

    text = format_chat_payload(payload)

    assert "Статус: answered" in text
    assert "Краткий ответ" in text
    assert "Источники:" in text
    assert "[S1]" in text
    assert "Авторизация" in text


def test_parse_allowed_chat_ids() -> None:
    assert _parse_allowed_chat_ids(None) is None
    assert _parse_allowed_chat_ids("123, 456;789") == {123, 456, 789}
