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


def search_error_payload() -> dict:
    return {
        "status": "error",
        "query": "Паспорт ИС",
        "answer": "Поиск завершился ошибкой.",
        "error": "index_not_ready",
        "context": {"primary_sources": [], "supporting_sources": [], "excluded_sources": [], "diagnostics": {}},
        "results": [],
        "guard": {"decision": "allow"},
        "diagnostics": {"search_service": {"retrieval_called": False}},
    }


def nsi_inventory_payload() -> dict:
    return {
        "status": "ok",
        "query": "Какие справочники НСИ перечислены в корпусе?",
        "context": {
            "primary_sources": [
                {
                    "chunk_id": "nsi-table8",
                    "source_id": "doc-soi-nsi",
                    "title": "Цели и задачи интеграции",
                    "document_type": "СоИ Справочники",
                    "document": "Этап 1.1/11. Соглашения об интеграции для интерфейсов/ЦП УПКС_СоИ_Справочники_v2.2.1.docx",
                    "source_url": "https://example.test/soi-nsi",
                    "source_type": "project_doc",
                    "text": "Справочники: Единицы измерения; Должности; Отделы; Контрагенты; Организации; Объекты строительства.",
                }
            ],
            "supporting_sources": [],
            "excluded_sources": [],
            "diagnostics": {},
        },
        "results": [{"chunk_id": "nsi-table8"}],
        "guard": {"decision": "allow"},
        "diagnostics": {"search_service": {"retrieval_called": True}},
    }


def passport_related_documents_payload() -> dict:
    return {
        "status": "ok",
        "query": "Что входит в Паспорт ИС и какие связанные документы в нём указаны?",
        "context": {
            "primary_sources": [
                {
                    "chunk_id": "passport-table2-expanded",
                    "source_id": "doc-passport",
                    "title": "ЦП УПКС_Паспорт ИС_v1.3.3.docx",
                    "document_type": "Паспорт ИС",
                    "document": "Этап 1.2/8. Паспорт информационной системы/ЦП УПКС_Паспорт ИС_v1.3.3.docx",
                    "source_url": "https://example.test/passport",
                    "source_type": "project_doc",
                    "text": "Документ: Паспорт ИС. Таблица: Table 2. Строка: 2 Название документа: Проектное решение «Модуль СМР (Строительный контроль)» Номер версии /Имя файла: 1.ЦП_УПКС_ПР_СМР_Строительный_контроль_v_ Дата: .03.2026. Документ: Паспорт ИС. Таблица: Table 2. Строка: 3 Название документа: Целевая техническая архитектура (ЦТА) Номер версии /Имя файла: 1./ЦТА_ЦП_УПКС_Этап_1 Дата: .2026. Документ: Паспорт ИС. Таблица: Table 2. Строка: 4 Название документа: Соглашение об интеграции (Active Directory) Номер версии /Имя файла: 1.1/ЦП УПКС_СоИ_AD Дата: .03.2026.",
                }
            ],
            "supporting_sources": [],
            "excluded_sources": [],
            "diagnostics": {},
        },
        "results": [{"chunk_id": "passport-table2-expanded"}],
        "guard": {"decision": "allow"},
        "diagnostics": {"search_service": {"retrieval_called": True}},
    }


def passport_appendices_payload() -> dict:
    return {
        "status": "ok",
        "query": "Какие приложения перечислены в Паспорте ИС?",
        "context": {
            "primary_sources": [
                {
                    "chunk_id": "passport-table3-expanded",
                    "source_id": "doc-passport",
                    "title": "ЦП УПКС_Паспорт ИС_v1.3.3.docx",
                    "document_type": "Паспорт ИС",
                    "document": "Этап 1.2/8. Паспорт информационной системы/ЦП УПКС_Паспорт ИС_v1.3.3.docx",
                    "source_url": "https://example.test/passport",
                    "source_type": "project_doc",
                    "text": "Документ: Паспорт ИС. Таблица: Table 3. Заголовки: Приложение №1 План послеаварийного восстановления | План послеаварийного восстановления. Документ: Паспорт ИС. Таблица: Table 3. Строка: 3 Приложение №1 План послеаварийного восстановления: Приложение №2 Список источников План послеаварийного восстановления: Список источников.",
                }
            ],
            "supporting_sources": [],
            "excluded_sources": [],
            "diagnostics": {},
        },
        "results": [{"chunk_id": "passport-table3-expanded"}],
        "guard": {"decision": "allow"},
        "diagnostics": {"search_service": {"retrieval_called": True}},
    }


def passport_purpose_payload() -> dict:
    return {
        "status": "ok",
        "query": "Какие сведения о системе и назначении ИС указаны в Паспорте ИС?",
        "context": {
            "primary_sources": [
                {
                    "chunk_id": "passport-purpose",
                    "source_id": "doc-passport",
                    "title": "Описание и область применения",
                    "document_type": "Паспорт ИС",
                    "document": "Этап 1.2/8. Паспорт информационной системы/ЦП УПКС_Паспорт ИС_v1.3.3.docx",
                    "source_url": "https://example.test/passport",
                    "source_type": "project_doc",
                    "text": "Система предназначена для формирования единой информационной среды для автоматизации и цифровизации бизнес-процессов управления строительными проектами от стадии проектирования до ввода в эксплуатацию.",
                }
            ],
            "supporting_sources": [],
            "excluded_sources": [],
            "diagnostics": {},
        },
        "results": [{"chunk_id": "passport-purpose"}],
        "guard": {"decision": "allow"},
        "diagnostics": {"search_service": {"retrieval_called": True}},
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


def test_chat_search_error_does_not_call_llm() -> None:
    search = FakeSearchService(search_error_payload())
    llm = FakeLLMClient("should not be used")
    service = ChatService(search_service=search, llm_client=llm)

    response = service.chat(ChatRequest(query="Паспорт ИС"))

    assert response.status == "search_error"
    assert llm.called is False
    assert response.diagnostics["llm_called"] is False
    assert response.diagnostics["search_error"] == "index_not_ready"


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


def test_chat_no_answer_marker_returns_no_answer_status() -> None:
    search = FakeSearchService(project_payload())
    llm = FakeLLMClient("Краткий ответ\nВ переданных источниках данных недостаточно для ответа.\n\nОбоснование\n- Найдены только косвенные упоминания. [S1]")
    service = ChatService(search_service=search, llm_client=llm)

    response = service.chat(ChatRequest(query="Протокол ПСИ"))

    assert response.status == "no_answer"
    assert response.diagnostics["llm_called"] is True
    assert response.diagnostics["no_answer_marker_present"] is True
    assert response.diagnostics["validation_errors"] == []


def test_chat_inventory_prompt_includes_source_metadata_and_list_policy() -> None:
    search = FakeSearchService(nsi_inventory_payload())
    llm = FakeLLMClient("Краткий ответ\nВ корпусе найдены справочники: Единицы измерения, Должности, Отделы. [S1]\n\nОбоснование\n- Перечень указан в источнике СоИ Справочники. [S1]")
    service = ChatService(search_service=search, llm_client=llm)

    response = service.chat(ChatRequest(query="Какие справочники НСИ перечислены в корпусе?", model="fake-model"))

    assert response.status == "answered"
    assert "СоИ Справочники" in llm.last_request.prompt
    assert "ЦП УПКС_СоИ_Справочники_v2.2.1.docx" in llm.last_request.prompt
    assert "https://example.test/soi-nsi" in llm.last_request.prompt
    assert "используй названия, типы, пути и ссылки источников" in llm.last_request.prompt


def test_chat_inventory_fallback_converts_false_no_answer_to_source_list() -> None:
    search = FakeSearchService(nsi_inventory_payload())
    llm = FakeLLMClient("Краткий ответ\nВ переданных источниках данных недостаточно для ответа.\n\nОбоснование\n- Модель не извлекла перечень. [S1]")
    service = ChatService(search_service=search, llm_client=llm)

    response = service.chat(ChatRequest(query="Какие справочники НСИ перечислены в корпусе?", model="fake-model"))

    assert response.status == "answered"
    assert response.diagnostics["inventory_fallback_answer"] is True
    assert "Единицы измерения" in response.answer
    assert "[S1]" in response.answer


def test_chat_passport_related_documents_fallback_converts_false_no_answer() -> None:
    search = FakeSearchService(passport_related_documents_payload())
    llm = FakeLLMClient("Краткий ответ\nВ переданных источниках данных недостаточно для ответа.\n\nОбоснование\n- Модель не извлекла перечень. [S1]")
    service = ChatService(search_service=search, llm_client=llm)

    response = service.chat(ChatRequest(query="Что входит в Паспорт ИС и какие связанные документы в нём указаны?", model="fake-model"))

    assert response.status == "answered"
    assert response.diagnostics["inventory_fallback_answer"] is True
    assert "Проектное решение" in response.answer
    assert "Целевая техническая архитектура" in response.answer
    assert "Соглашение об интеграции" in response.answer
    assert "[S1]" in response.answer


def test_chat_passport_appendices_fallback_converts_false_no_answer() -> None:
    search = FakeSearchService(passport_appendices_payload())
    llm = FakeLLMClient("Краткий ответ\nВ переданных источниках данных недостаточно для ответа.\n\nОбоснование\n- Модель не извлекла перечень. [S1]")
    service = ChatService(search_service=search, llm_client=llm)

    response = service.chat(ChatRequest(query="Какие приложения перечислены в Паспорте ИС?", model="fake-model"))

    assert response.status == "answered"
    assert response.diagnostics["inventory_fallback_answer"] is True
    assert "План послеаварийного восстановления" in response.answer
    assert "Список источников" in response.answer
    assert "[S1]" in response.answer


def test_chat_passport_purpose_fallback_converts_false_no_answer() -> None:
    search = FakeSearchService(passport_purpose_payload())
    llm = FakeLLMClient("Краткий ответ\nВ переданных источниках данных недостаточно для ответа.\n\nОбоснование\n- Модель не извлекла назначение. [S1]")
    service = ChatService(search_service=search, llm_client=llm)

    response = service.chat(ChatRequest(query="Какие сведения о системе и назначении ИС указаны в Паспорте ИС?", model="fake-model"))

    assert response.status == "answered"
    assert response.diagnostics["inventory_fallback_answer"] is True
    assert "Система предназначена" in response.answer
    assert "единой информационной среды" in response.answer
    assert "[S1]" in response.answer
