from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.api.app import create_app  # noqa: E402
from asu_june_bot.api.ui_assets import load_ui_asset  # noqa: E402
from asu_june_bot.auth.repository import AuthRepository  # noqa: E402
from asu_june_bot.auth.service import LocalAuthService  # noqa: E402
from asu_june_bot.chat.models import ChatResponse, ChatSource  # noqa: E402
from asu_june_bot.auth.throttle import LoginThrottle  # noqa: E402
from asu_june_bot.core.limits import MAX_QUERY_CHARS  # noqa: E402

TOKEN = "test-chat-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


class FakeHealthService:
    def check(self) -> dict:
        return {"status": "ok"}


class FakeSearchService:
    pass


class FakeChatService:
    def __init__(self) -> None:
        self.last_request = None

    def chat(self, request):
        self.last_request = request
        lowered = request.query.lower()
        if "погода" in lowered:
            return ChatResponse(
                status="refused",
                query=request.query,
                answer="Я отвечаю только по материалам проекта PROJECT SYSTEM.",
                search={"status": "refused"},
                diagnostics={"llm_called": False, "search_status": "refused"},
            )
        if "подробнее" in lowered:
            return ChatResponse(
                status="clarify",
                query=request.query,
                answer="Уточните проектный объект поиска.",
                search={"status": "clarify"},
                diagnostics={"llm_called": False, "search_status": "clarify"},
            )
        if "пустой" in lowered:
            return ChatResponse(
                status="llm_empty_response",
                query=request.query,
                answer="LLM вернула пустой ответ.",
                sources=[ChatSource(source_ref="S1", title="Тестовый источник")],
                search={"status": "ok"},
                diagnostics={"llm_called": True, "search_status": "ok", "llm_finish_reason": "length"},
            )
        return ChatResponse(
            status="answered",
            query=request.query,
            answer="Краткий ответ\nАвторизация описана через AD. [S1]",
            sources=[ChatSource(source_ref="S1", title="PROJECT SYSTEM_СоИ_AD", section="Авторизация")],
            search={"status": "ok"},
            diagnostics={"llm_called": True, "search_status": "ok", "llm_finish_reason": "stop"},
        )


@dataclass(slots=True)
class FakeState:
    health_service: FakeHealthService
    search_service: FakeSearchService
    chat_service: FakeChatService
    local_auth_service: LocalAuthService
    login_throttle: LoginThrottle = field(default_factory=LoginThrottle)


def build_client():
    os.environ["MEETINGAGENT_API_TOKEN"] = TOKEN
    td = tempfile.mkdtemp()
    repo = AuthRepository(Path(td) / "auth.db")
    repo.initialize()
    app = create_app()
    client = TestClient(app, headers=AUTH)
    client.__enter__()
    fake_chat = FakeChatService()
    app.state.asu_june_bot = FakeState(
        health_service=FakeHealthService(),
        search_service=FakeSearchService(),
        chat_service=fake_chat,
        local_auth_service=LocalAuthService(repo),
    )
    return client, fake_chat


def test_ui_endpoint_returns_local_chat_page() -> None:
    client, _fake_chat = build_client()
    try:
        response = client.get("/ui")
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 200
    ui = response.text + load_ui_asset("bot.js")
    assert "АСУ Джун бот" in ui
    assert "Проектные вопросы" in ui
    assert "Способ поиска" in ui
    assert "Сбалансированный" in ui
    assert "/chat" in ui
    assert "max_tokens: 1400" in ui
    assert "runtimeWarning" in ui
    assert str(MAX_QUERY_CHARS) in ui


def test_chat_endpoint_project_query() -> None:
    client, fake_chat = build_client()
    try:
        response = client.post(
            "/chat",
            json={
                "query": "СоИ AD как происходит авторизация пользователей?",
                "mode": "hybrid",
                "top_k": 5,
                "model": "qwen3.5:4b",
                "max_tokens": 500,
                "timeout_sec": 300,
            },
            headers={"X-Request-Id": "chat-project"},
        )
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 200
    assert response.headers["X-Request-Id"] == "chat-project"
    data = response.json()
    assert data["status"] == "answered"
    assert data["answer"]
    assert data["sources"][0]["source_ref"] == "S1"
    assert data["diagnostics"]["llm_called"] is True
    assert data["diagnostics"]["request_id"] == "chat-project"
    assert fake_chat.last_request.query == "СоИ AD как происходит авторизация пользователей?"
    assert fake_chat.last_request.mode == "hybrid"
    assert fake_chat.last_request.top_k == 5
    assert fake_chat.last_request.model == "qwen3.5:4b"
    assert fake_chat.last_request.max_tokens == 500
    assert fake_chat.last_request.timeout_sec == 300


def test_chat_endpoint_refused_query_does_not_call_llm() -> None:
    client, fake_chat = build_client()
    try:
        response = client.post("/chat", json={"query": "Какая погода завтра в Москве?", "mode": "hybrid", "top_k": 5})
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "refused"
    assert data["diagnostics"]["llm_called"] is False
    assert data["sources"] == []
    assert fake_chat.last_request.max_tokens == 1400


def test_chat_endpoint_clarify_query_does_not_call_llm() -> None:
    client, _fake_chat = build_client()
    try:
        response = client.post("/chat", json={"query": "Расскажи подробнее", "mode": "hybrid", "top_k": 5})
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "clarify"
    assert data["diagnostics"]["llm_called"] is False


def test_chat_endpoint_empty_llm_response() -> None:
    client, _fake_chat = build_client()
    try:
        response = client.post("/chat", json={"query": "Проектный запрос с пустой LLM", "mode": "hybrid", "top_k": 5})
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "llm_empty_response"
    assert data["diagnostics"]["llm_called"] is True
    assert data["diagnostics"]["llm_finish_reason"] == "length"


def test_chat_endpoint_validation_error_on_unknown_field() -> None:
    client, _fake_chat = build_client()
    try:
        response = client.post("/chat", json={"query": "test", "unknown": "field"})
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 422
    data = response.json()
    assert data["status"] == "error"
    assert data["error_code"] == "validation_error"


def test_chat_endpoint_rejects_too_long_query() -> None:
    client, _fake_chat = build_client()
    try:
        response = client.post("/chat", json={"query": "x" * (MAX_QUERY_CHARS + 1)})
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 422
    data = response.json()
    assert data["status"] == "error"
    assert data["error_code"] == "validation_error"
