from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.chat.models import ChatRequest, ChatResponse, ChatSource  # noqa: E402
from asu_june_bot.observability import ChatRunsLogger  # noqa: E402


def test_chat_runs_logger_appends_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "chat_runs.jsonl"
    logger = ChatRunsLogger(path)
    request = ChatRequest(query="СоИ AD как происходит авторизация пользователей?")
    response = ChatResponse(
        status="answered",
        query=request.query,
        answer="Авторизация описана через AD. [S1]",
        sources=[ChatSource(source_ref="S1", title="ЦП УПКС_СоИ_AD", bucket="primary_sources")],
        search={"status": "ok", "guard": {"decision": "allow"}},
        diagnostics={
            "llm_called": True,
            "search_status": "ok",
            "llm_model": "fake-model",
            "llm_finish_reason": "stop",
            "validation_errors": [],
            "prompt_sources": 1,
            "prompt": {"used_context_chars": 100, "max_context_chars": 9000},
        },
    )

    logger.log(request, response, latency_ms=123)

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["query"] == request.query
    assert record["status"] == "answered"
    assert record["llm_called"] is True
    assert record["llm_model"] == "fake-model"
    assert record["sources"][0]["source_ref"] == "S1"
    assert record["latency_ms"] == 123
    assert record["manual_label"] is None


def test_chat_runs_logger_disabled_skips_write(tmp_path: Path) -> None:
    path = tmp_path / "chat_runs.jsonl"
    logger = ChatRunsLogger(path, enabled=False)
    request = ChatRequest(query="Какая погода завтра?")
    response = ChatResponse(status="refused", query=request.query, answer="refused")

    logger.log(request, response)

    assert not path.exists()
