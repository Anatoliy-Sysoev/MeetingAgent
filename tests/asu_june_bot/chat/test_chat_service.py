from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.chat import ChatRequest, ChatService  # noqa: E402
from asu_june_bot.llm import LLMRequest, LLMResponse  # noqa: E402
from asu_june_bot.search.models import SearchResponse  # noqa: E402


class FakeSearchService:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.called = False
        self.last_request = None

    def search(self, request):
        self.called = True
        self.last_request = request
        return SearchResponse(self.payload)


class FakeLLMClient:
    def __init__(self, text: str) -> None:
        self.text = text
        self.called = False
        self.last_request: LLMRequest | None = None

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.called = True
        self.last_request = request
        return LLMResponse(text=self.text, model=request.model or "fake-model")


def project_payload(long_supporting: bool = False) -> dict:
    supporting = []
    if long_supporting:
        supporting = [
            {
                "chunk_id": "chunk-supporting-long",
                "source_id": "doc-supporting",
                "title": "Длинный дополнительный источник",
                "section": "Тест",
                "source_type": "project_doc",
                "text": "длинный текст " * 3000,
            }
        ]
    return {
        "status": "ok",
        "query": "СоИ AD как происходит авторизация пользователей?",
        "context": {
            "primary_sources": [
                {
                    "chunk_id": "chunk-1",
                    "source_id": "doc-ad",
                    "title": "ЦП УПКС_СоИ_AD",
                    "section": "Цели и задачи интеграции",
                    "source_type": "project_doc",
                    "text": "Цель интеграции — получить актуальный перечень пользователей ЦП УПКС на основании членства пользователей в группах безопасности корпоративной Active Directory.",
                }
            ],
            "supporting_sources": supporting,
            "excluded_sources": [
                {
                    "chunk_id": "excluded-1",
                    "text": "Этот источник запрещено передавать в LLM",
                }
            ],
            "diagnostics": {},
        },
        "results": [{"chunk_id": "chunk-1"}],
        "guard": {"decision": "allow"},
        "diagnostics": {"search_service": {"retrieval_called": True}},
    }


def refused_payload() -> dict:
    return {
        "status": "refused",
        "query": "Какая погода завтра?",
        "answer": "Я отвечаю только по материалам проекта ЦП УПКС.",
        "context": {"primary_sources": [], "supporting_sources": [], "excluded_sources": [], "diagnostics": {}},
        "results": [],
        "guard": {"decision": "refuse"},
        "diagnostics": {"search_service": {"retrieval_called": False}},
    }


def clarify_payload() -> dict:
    return {
        "status": "clarify",
        "query": "Расскажи подробнее",
        "answer": "Уточните проектный объект поиска.",
        "context": {"primary_sources": [], "supporting_sources": [], "excluded_sources": [], "diagnostics": {}},
        "results": [],
        "guard": {"decision": "clarify"},
        "diagnostics": {"search_service": {"retrieval_called": False}},
    }


def test_chat_refused_does_not_call_llm() -> None:
    search = FakeSearchService(refused_payload())
    llm = FakeLLMClient("should not be used")
    service = ChatService(search_service=search, llm_client=llm)

    response = service.chat(ChatRequest(query="Какая погода завтра?"))

    assert response.status == "refused"
    assert search.called is True
    assert llm.called is False
    assert response.diagnostics["llm_called"] is False


def test_chat_clarify_does_not_call_llm() -> None:
    search = FakeSearchService(clarify_payload())
    llm = FakeLLMClient("should not be used")
    service = ChatService(search_service=search, llm_client=llm)

    response = service.chat(ChatRequest(query="Расскажи подробнее"))

    assert response.status == "clarify"
    assert llm.called is False
    assert response.diagnostics["llm_called"] is False


def test_chat_project_query_calls_llm_with_context_only() -> None:
    search = FakeSearchService(project_payload())
    llm = FakeLLMClient("Краткий ответ\nАвторизация использует данные AD. [S1]\n\nОбоснование\n- Пользователи определяются по группам AD. [S1]")
    service = ChatService(search_service=search, llm_client=llm)

    response = service.chat(ChatRequest(query="СоИ AD как происходит авторизация пользователей?", model="fake-model"))

    assert response.status == "answered"
    assert llm.called is True
    assert response.diagnostics["llm_called"] is True
    assert response.sources[0].source_ref == "S1"
    assert response.sources[0].bucket == "primary_sources"
    assert "[S1]" in response.answer
    assert "excluded_sources" not in llm.last_request.prompt
    assert "Этот источник запрещено" not in llm.last_request.prompt
    assert "Цель интеграции" in llm.last_request.prompt


def test_chat_prompt_has_context_budget_diagnostics() -> None:
    search = FakeSearchService(project_payload(long_supporting=True))
    llm = FakeLLMClient("Краткий ответ\nАвторизация использует данные AD. [S1]\n\nОбоснование\n- Пользователи определяются по группам AD. [S1]")
    service = ChatService(search_service=search, llm_client=llm)

    response = service.chat(ChatRequest(query="СоИ AD как происходит авторизация пользователей?", model="fake-model"))

    assert response.status == "answered"
    assert response.diagnostics["prompt"]["selected_sources"] >= 1
    assert response.diagnostics["prompt"]["used_context_chars"] <= response.diagnostics["prompt"]["max_context_chars"]


def test_chat_empty_llm_response_is_not_answered() -> None:
    search = FakeSearchService(project_payload())
    llm = FakeLLMClient("")
    service = ChatService(search_service=search, llm_client=llm)

    response = service.chat(ChatRequest(query="СоИ AD как происходит авторизация пользователей?"))

    assert response.status == "llm_empty_response"
    assert response.diagnostics["llm_called"] is True


def test_chat_answer_without_source_reference_fails_validation() -> None:
    search = FakeSearchService(project_payload())
    llm = FakeLLMClient("Авторизация использует данные AD, но ссылка не указана.")
    service = ChatService(search_service=search, llm_client=llm)

    response = service.chat(ChatRequest(query="СоИ AD как происходит авторизация пользователей?"))

    assert response.status == "validation_failed"
    assert "missing_source_references" in response.diagnostics["validation_errors"]


def test_chat_answer_with_unknown_source_reference_fails_validation() -> None:
    search = FakeSearchService(project_payload())
    llm = FakeLLMClient("Авторизация использует данные AD. [S99]")
    service = ChatService(search_service=search, llm_client=llm)

    response = service.chat(ChatRequest(query="СоИ AD как происходит авторизация пользователей?"))

    assert response.status == "validation_failed"
    assert "unknown_source_references:S99" in response.diagnostics["validation_errors"]
