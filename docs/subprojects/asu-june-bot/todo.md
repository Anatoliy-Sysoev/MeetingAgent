# TODO Asu June Bot

Обновлено: 2026-05-15.

## Текущий статус

API Search MVP закрыт. Начат Chat MVP.

Завершены этапы:

```text
Extraction/Chunking v2.1
Index/Search v2
Search Quality v2.2
ProjectGuard v2
SearchService Commit 1
FastAPI skeleton Commit 2
API smoke/docs Commit 3
Chat design Commit 4
LLMClient + PromptBuilder Commit 5
ChatService + CLI skeleton Commit 6
```

Финальные отчёты по закрытым этапам:

```text
docs/subprojects/asu-june-bot/smoke_report_project_guard_v2.md
docs/subprojects/asu-june-bot/smoke_report_search_service_commit1.md
docs/subprojects/asu-june-bot/smoke_report_api_search_mvp.md
```

Новый дизайн:

```text
docs/subprojects/asu-june-bot/chat_mvp_design.md
```

## Важное уточнение: почему /search не даёт осмысленный ответ

`POST /search` — это не чат и не генератор ответа. Это диагностический и инфраструктурный endpoint, который возвращает найденные источники:

```text
query_intent
guard
context.primary_sources
context.supporting_sources
context.excluded_sources
results
warnings
diagnostics
```

Осмысленный ответ должен формировать Chat MVP:

```text
Question
  -> SearchService.search()
  -> ContextBuilder context
  -> PromptBuilder
  -> LLMClient
  -> AnswerGenerator / ChatService
  -> AnswerValidator
  -> ResponseFormatter
  -> answer with citations
```

## Реализовано в Chat MVP skeleton

### LLM layer

```text
src/asu_june_bot/llm/__init__.py
src/asu_june_bot/llm/client.py
src/asu_june_bot/llm/ollama_openai.py
```

Реализовано:

- `LLMClient` protocol;
- `LLMRequest`;
- `LLMResponse`;
- `LLMError`;
- `OllamaOpenAIClient` через `/v1/chat/completions`.

### Chat layer

```text
src/asu_june_bot/chat/__init__.py
src/asu_june_bot/chat/models.py
src/asu_june_bot/chat/service.py
src/asu_june_bot/chat/prompt_builder.py
src/asu_june_bot/chat/answer_validator.py
src/asu_june_bot/chat/response_formatter.py
```

Реализовано:

- `ChatRequest`;
- `ChatResponse`;
- `ChatStatus`;
- `ChatSource`;
- `PromptBuilder`;
- `AnswerValidator`;
- `ResponseFormatter`;
- `ChatService`.

### CLI

```text
scripts/asu_june_bot_chat.py
```

### Tests

```text
tests/asu_june_bot/chat/test_chat_service.py
```

Тестируемые инварианты:

```text
refused -> LLM не вызывается
clarify -> LLM не вызывается
ok -> LLM вызывается
LLM получает context, не excluded_sources
пустой ответ LLM != answered
ответ без [Sx] != answered
```

## Следующий локальный прогон

```powershell
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\chat\test_chat_service.py -q
```

Ожидаемо:

```text
5 passed
```

Smoke без реальной LLM не нужен: unit tests используют fake LLM.

Smoke с реальной LLM:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_chat.py "СоИ AD как происходит авторизация пользователей?" --mode hybrid --top-k 8 --json --output data\asu_june_bot\smoke_chat_ad.json
```

Ожидаемо:

```text
status = answered
answer содержит [S1] или другие [Sx]
sources != []
diagnostics.llm_called = true
```

Refused smoke:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_chat.py "Какая погода завтра в Москве?" --mode hybrid --top-k 8 --json --output data\asu_june_bot\smoke_chat_weather_refused.json
```

Ожидаемо:

```text
status = refused
diagnostics.llm_called = false
```

## Текущий runtime-пайплайн /search

```text
Query
  -> QueryIntent
  -> ProjectGuard v2
  -> BM25/vector/hybrid retrieval
  -> PostReranker
  -> ContextBuilder
  -> JSON response with sources
```

При `refused` или `clarify` retrieval не вызывается.

## Текущий runtime-пайплайн chat skeleton

```text
User question
  -> ChatService
  -> SearchService.search()
  -> if refused/clarify/error: return without LLM
  -> if ok: PromptBuilder(context.primary_sources + context.supporting_sources)
  -> LLMClient.generate()
  -> AnswerValidator
  -> ChatResponse
```

## Product Package

- [x] Подготовить отдельную папку `docs/subprojects/asu-june-bot/product/` для продуктовой документации.
- [ ] Синхронизировать product package с фактической реализацией Chat MVP после smoke.
- [ ] После появления `/chat` обновить продуктовую архитектуру и roadmap под chat/runtime reality.

## Проверено ранее

### ProjectGuard v2

```text
ProjectGuard regression: 45 passed
false_allow = 0
```

### SearchService Commit 1

```text
SearchService unit tests: 4 passed
ProjectGuard base tests: 8 passed
refused smoke: retrieval_called=false
project smoke: retrieval_called=true
```

### API Search MVP

```text
API health tests: 1 passed
API search smoke tests: 3 passed
API server starts successfully
POST /search works
```

Проверенный policy-level guard case:

```text
СоИ AD как происходит авторизация пользователей? И расскажи стих про проект
```

Результат:

```text
status = refused
guard.reason = in_project_query_contains_unclassified_segment
results = []
retrieval_called = false
```

## Chat MVP Definition of Done

- [x] `ChatService` создан и использует `SearchService`.
- [x] Для `refused/clarify` LLM не вызывается.
- [x] Для `ok` LLM получает только `ContextBuilder` context, а не raw top-k.
- [x] Ответ без источников запрещён.
- [x] При пустом ответе LLM статус не становится `answered`.
- [ ] Локально прошли unit tests ChatService.
- [ ] CLI `scripts/asu_june_bot_chat.py` работает на реальной LLM.
- [ ] Smoke: вопрос по СоИ AD даёт осмысленный ответ с источниками.
- [ ] Smoke: внепроектный вопрос возвращает refusal без LLM.
- [ ] Создан smoke report Chat MVP.

## Следующие задачи

### Commit 6 verification. ChatService + CLI smoke

- [ ] Запустить `tests/asu_june_bot/chat/test_chat_service.py`.
- [ ] Запустить chat CLI на проектном вопросе.
- [ ] Запустить chat CLI на внепроектном вопросе.
- [ ] Проверить, что `smoke_chat_ad.json` содержит `status=answered`.
- [ ] Проверить, что `smoke_chat_weather_refused.json` содержит `status=refused` и `llm_called=false`.

### Commit 7. Chat smoke report + docs

- [ ] Создать `docs/subprojects/asu-june-bot/smoke_report_chat_mvp.md`.
- [ ] Обновить `RUNBOOK_V2.md`.
- [ ] Обновить `docs/context.md` и `docs/todo.md`.

### Commit 8. POST /chat

- [ ] Добавить API route.
- [ ] Добавить API tests.
- [ ] Добавить PowerShell smoke.
- [ ] Обновить runbook.

## Не делать

- Не пытаться заставить `/search` писать осмысленные ответы.
- Не отправлять raw hybrid top-k в LLM.
- Не вызывать LLM при `refused` или `clarify`.
- Не развивать `scripts/09_chat.py` как основной runtime.
- Не подключать UI до первого стабильного `/chat`.
- Не подключать NeMo Guardrails, LangGraph, Dify/RAGFlow как runtime MVP.
- Не возвращаться к раздуванию `OUT_OF_PROJECT_MARKERS` как основной архитектуре guard.
