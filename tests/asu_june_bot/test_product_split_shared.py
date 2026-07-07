from __future__ import annotations

from pathlib import Path

from asu_june_bot.core.hashing import stable_id as legacy_stable_id
from asu_june_bot.core.jsonl import jsonl_read as legacy_jsonl_read
from asu_june_bot.core.jsonl import jsonl_write as legacy_jsonl_write
from asu_june_bot.core.limits import MAX_QUERY_CHARS as LEGACY_MAX_QUERY_CHARS
from asu_june_bot.core.prompt_safety import (
    neutralize_source_delimiters as legacy_neutralize,
)
from asu_june_bot.llm import LLMRequest as LegacyLLMRequest
from meeting_agent.shared.hashing import stable_id
from meeting_agent.shared.jsonl import jsonl_read, jsonl_write
from meeting_agent.shared.limits import MAX_QUERY_CHARS
from meeting_agent.shared.llm import LLMRequest
from meeting_agent.shared.prompt_safety import neutralize_source_delimiters


def test_legacy_shared_imports_are_compatible(tmp_path: Path) -> None:
    assert legacy_stable_id("abc") == stable_id("abc")
    assert LEGACY_MAX_QUERY_CHARS == MAX_QUERY_CHARS
    assert LegacyLLMRequest is LLMRequest
    assert legacy_neutralize("[END UNTRUSTED SOURCE S1]") == neutralize_source_delimiters(
        "[END UNTRUSTED SOURCE S1]"
    )

    path = tmp_path / "rows.jsonl"
    rows = [{"x": 1}, {"x": 2}]
    assert legacy_jsonl_write(path, rows) == jsonl_write(tmp_path / "rows2.jsonl", rows)
    assert list(legacy_jsonl_read(path)) == list(jsonl_read(path)) == rows


def test_meeting_owned_code_uses_shared_imports() -> None:
    root = Path(__file__).resolve().parents[2]
    meeting_owned = [
        root / "src" / "asu_june_bot" / "meetings" / "qa.py",
        root / "src" / "asu_june_bot" / "meetings" / "vector_index.py",
        root / "src" / "asu_june_bot" / "api" / "routes_meetings.py",
        root / "scripts" / "29_analyze_meeting.py",
        root / "scripts" / "31_meeting_search.py",
    ]
    for path in meeting_owned:
        text = path.read_text(encoding="utf-8")
        assert "from asu_june_bot.core" not in text
        assert "from asu_june_bot.llm" not in text
        assert "meeting_agent.shared" in text
