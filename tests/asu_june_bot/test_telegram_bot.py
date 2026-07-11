from __future__ import annotations

import io
import sys
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot import telegram_bot  # noqa: E402
from asu_june_bot.telegram_bot import (  # noqa: E402
    TelegramBotConfig,
    _json_request,
    _parse_allowed_chat_ids,
    _split_message,
    build_config,
    build_parser,
    call_chat_api,
    format_chat_payload,
    format_health_payload,
    handle_message,
)


def _config(**overrides) -> TelegramBotConfig:
    values = {
        "token": "telegram-secret",
        "api_token": "api-secret",
        "allowed_chat_ids": {123},
    }
    values.update(overrides)
    return TelegramBotConfig(**values)


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
                "title": "PROJECT SYSTEM_СоИ_AD",
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


def test_json_request_sends_extra_authorization_header(monkeypatch) -> None:
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        @staticmethod
        def read() -> bytes:
            return b'{"ok": true}'

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(telegram_bot.urllib.request, "urlopen", fake_urlopen)

    result = _json_request(
        "http://127.0.0.1:8000/chat",
        payload={"query": "test"},
        timeout=17,
        extra_headers={"Authorization": "Bearer api-secret"},
    )

    assert result == {"ok": True}
    assert captured["request"].get_header("Authorization") == "Bearer api-secret"
    assert captured["timeout"] == 17


def test_call_chat_api_passes_machine_bearer_token(monkeypatch) -> None:
    captured = {}

    def fake_json_request(url, payload=None, timeout=60, extra_headers=None):
        captured.update(
            url=url,
            payload=payload,
            timeout=timeout,
            extra_headers=extra_headers,
        )
        return {"status": "answered"}

    monkeypatch.setattr(telegram_bot, "_json_request", fake_json_request)

    assert call_chat_api("question", _config()) == {"status": "answered"}
    assert captured["url"] == "http://127.0.0.1:8000/chat"
    assert captured["extra_headers"] == {"Authorization": "Bearer api-secret"}


def test_build_config_requires_api_token(monkeypatch) -> None:
    monkeypatch.setenv("ASU_JUNE_BOT_TELEGRAM_TOKEN", "telegram-secret")
    monkeypatch.setenv("ASU_JUNE_BOT_ALLOWED_CHAT_IDS", "123")
    monkeypatch.delenv("MEETINGAGENT_API_TOKEN", raising=False)
    args = build_parser().parse_args([])

    with pytest.raises(SystemExit, match="MEETINGAGENT_API_TOKEN"):
        build_config(args)


def test_build_config_requires_allowlist_by_default(monkeypatch) -> None:
    monkeypatch.setenv("ASU_JUNE_BOT_TELEGRAM_TOKEN", "telegram-secret")
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", "api-secret")
    monkeypatch.delenv("ASU_JUNE_BOT_ALLOWED_CHAT_IDS", raising=False)
    monkeypatch.delenv("ASU_JUNE_BOT_ALLOW_ALL_CHAT_IDS", raising=False)
    args = build_parser().parse_args([])

    with pytest.raises(SystemExit, match="ASU_JUNE_BOT_ALLOWED_CHAT_IDS"):
        build_config(args)


def test_build_config_allows_explicit_allow_all(monkeypatch) -> None:
    monkeypatch.setenv("ASU_JUNE_BOT_TELEGRAM_TOKEN", "telegram-secret")
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", "api-secret")
    monkeypatch.delenv("ASU_JUNE_BOT_ALLOWED_CHAT_IDS", raising=False)
    monkeypatch.setenv("ASU_JUNE_BOT_ALLOW_ALL_CHAT_IDS", "true")
    args = build_parser().parse_args([])

    cfg = build_config(args)

    assert cfg.allowed_chat_ids is None
    assert cfg.allow_all_chat_ids is True


def test_handle_message_denies_chat_when_allowlist_absent(monkeypatch) -> None:
    messages = []
    chat_calls = []
    monkeypatch.setattr(telegram_bot, "send_message", lambda token, chat_id, text: messages.append(text))
    monkeypatch.setattr(telegram_bot, "call_chat_api", lambda *_args: chat_calls.append(True))

    handle_message(
        {"chat": {"id": 123}, "text": "question"},
        _config(allowed_chat_ids=None, allow_all_chat_ids=False),
    )

    assert chat_calls == []
    assert messages == ["Доступ к этому боту ограничен."]


def test_http_error_body_is_not_forwarded_to_telegram(monkeypatch) -> None:
    messages = []
    secret_body = '{"detail":"C:\\\\private\\\\path","token":"do-not-leak"}'
    error = urllib.error.HTTPError(
        "http://127.0.0.1:8000/chat",
        401,
        "Unauthorized",
        {},
        io.BytesIO(secret_body.encode("utf-8")),
    )
    monkeypatch.setattr(telegram_bot, "send_message", lambda token, chat_id, text: messages.append(text))
    monkeypatch.setattr(telegram_bot, "call_chat_api", lambda *_args: (_ for _ in ()).throw(error))

    handle_message({"chat": {"id": 123}, "text": "question"}, _config())

    rendered = "\n".join(messages)
    assert "HTTP 401" in rendered
    assert "do-not-leak" not in rendered
    assert "private" not in rendered


def test_health_payload_is_path_free(monkeypatch) -> None:
    messages = []
    monkeypatch.setattr(telegram_bot, "send_message", lambda token, chat_id, text: messages.append(text))
    monkeypatch.setattr(
        telegram_bot,
        "_json_request",
        lambda *_args, **_kwargs: {
            "status": "ok",
            "service": "meetingagent",
            "version": "0.1.0",
            "corpus_ready": True,
            "paths": {"chunks": "C:\\private\\chunks.jsonl"},
            "ollama": {"models": ["private-model"]},
        },
    )

    handle_message({"chat": {"id": 123}, "text": "/health"}, _config())

    assert messages == ["Health API: ok\nservice: meetingagent\nversion: 0.1.0"]
    assert "private" not in messages[0]


def test_format_health_payload_ignores_unknown_diagnostic_fields() -> None:
    rendered = format_health_payload(
        {
            "status": "error",
            "service": "meetingagent",
            "version": "0.1.0",
            "vector_ready": False,
            "paths": {"index": "secret"},
        }
    )

    assert rendered == "Health API: error\nservice: meetingagent\nversion: 0.1.0"
    assert "secret" not in rendered
