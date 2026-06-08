from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.chat import ChatRequest, ChatService  # noqa: E402
from asu_june_bot.chat.ftt_integration_answer import build_ftt_integration_deterministic_answer  # noqa: E402
from asu_june_bot.chat.models import ChatSource  # noqa: E402
from asu_june_bot.llm import LLMRequest, LLMResponse  # noqa: E402
from asu_june_bot.search.models import SearchResponse  # noqa: E402


class FakeSearchService:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def search(self, request):
        return SearchResponse(self.payload)


class FakeLLMClient:
    def __init__(self, text: str = "") -> None:
        self.text = text
        self.called = False
        self.last_request: LLMRequest | None = None

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.called = True
        self.last_request = request
        return LLMResponse(text=self.text, model=request.model or "fake-model", finish_reason="stop")


def ftt_source(text: str, *, source_ref: str = "S1") -> ChatSource:
    return ChatSource(
        source_ref=source_ref,
        source_id="ftt-integration",
        chunk_id="ftt-integration-protocol",
        title="Требования к интеграции и системным взаимодействиям",
        path="ФТТ.docx",
        source_type="project_doc",
        text_preview=text,
        bucket="primary_sources",
    )


def search_payload() -> dict:
    return {
        "status": "ok",
        "query": "Согласно ФТТ какой протокол передачи данных используется для системного взаимодействия?",
        "context": {
            "primary_sources": [
                {
                    "chunk_id": "ftt-integration-protocol",
                    "source_id": "ftt-integration",
                    "title": "Требования к интеграции и системным взаимодействиям",
                    "document_type": "ФТТ",
                    "document": "ФТТ.docx",
                    "source_type": "project_doc",
                    "text": "Протокол передачи данных: https. Формат сообщений: JSON, XML. Тип аутентификации: Basic-аутентификация.",
                }
            ],
            "supporting_sources": [],
            "excluded_sources": [],
            "diagnostics": {},
        },
        "results": [{"chunk_id": "ftt-integration-protocol"}],
        "guard": {"decision": "allow"},
        "diagnostics": {"search_service": {"retrieval_called": True}},
    }


def test_ftt_integration_protocol_answer_uses_https_source() -> None:
    answer = build_ftt_integration_deterministic_answer(
        "Согласно ФТТ какой протокол передачи данных используется для системного взаимодействия?",
        [ftt_source("Протокол передачи данных: https. Формат сообщений: JSON, XML.")],
    )

    assert answer is not None
    assert "HTTPS" in answer
    assert "[S1]" in answer


def test_ftt_integration_answer_requires_matching_ftt_anchor() -> None:
    answer = build_ftt_integration_deterministic_answer(
        "Согласно ФТТ какой протокол передачи данных используется для системного взаимодействия?",
        [ftt_source("Формат сообщений: JSON, XML.")],
    )

    assert answer is None


def test_chat_service_answers_ftt_integration_protocol_before_llm() -> None:
    search = FakeSearchService(search_payload())
    llm = FakeLLMClient("Краткий ответ\nВ переданных источниках данных недостаточно для ответа. [S1]")
    service = ChatService(search_service=search, llm_client=llm)

    response = service.chat(
        ChatRequest(query="Согласно ФТТ какой протокол передачи данных используется для системного взаимодействия?")
    )

    assert response.status == "answered"
    assert "HTTPS" in (response.answer or "")
    assert "[S1]" in (response.answer or "")
    assert llm.called is False
    assert response.diagnostics["llm_called"] is False
    assert response.diagnostics["pre_llm_deterministic_answer"] is True
    assert response.diagnostics["ftt_integration_deterministic_answer"] is True
