# TODO Asu June Bot

Обновлено: 2026-05-15.

## Текущий статус

API Search MVP закрыт.

Завершены этапы:

```text
Extraction/Chunking v2.1
Index/Search v2
Search Quality v2.2
ProjectGuard v2
SearchService Commit 1
FastAPI skeleton Commit 2
API smoke/docs Commit 3
```

Финальные отчёты:

```text
docs/subprojects/asu-june-bot/smoke_report_project_guard_v2.md
docs/subprojects/asu-june-bot/smoke_report_search_service_commit1.md
docs/subprojects/asu-june-bot/smoke_report_api_search_mvp.md
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

Его задача — доказать, что retrieval работает правильно и безопасно:

```text
проектный запрос -> найденные источники
внепроектный запрос -> refused без retrieval
ambiguous запрос -> clarify без retrieval
project + unknown tail -> refused без retrieval
```

Осмысленный ответ появится на следующем этапе — **Chat MVP**:

```text
Question
  -> SearchService /search
  -> ContextBuilder context
  -> PromptBuilder
  -> LLMClient
  -> AnswerGenerator
  -> AnswerValidator
  -> ResponseFormatter
  -> /chat response
```

Именно `/chat` должен будет отвечать нормальным текстом, но только на основании `primary_sources` и `supporting_sources`.

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

## Проверено

### ProjectGuard v2

```text
ProjectGuard regression: 45 passed
```

Критерий:

```text
false_allow = 0
```

### SearchService Commit 1

```text
SearchService unit tests: 4 passed
ProjectGuard base tests: 8 passed
ProjectGuard regression cases: passed
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

Архитектурное решение: не расширять marker DB частными темами; `project + unknown tail` блокировать на уровне GuardPolicy.

## Следующий этап: Chat MVP

### Цель

Сделать первый осмысленный project-only ответ поверх уже готового `/search`.

`ChatService` не должен заново выполнять guard/retrieval/rerank/context. Он должен использовать `SearchService`.

### Будущий pipeline

```text
User question
  -> ChatService
  -> SearchService.search()
  -> if refused/clarify: вернуть отказ/уточнение без LLM
  -> if ok: взять context.primary_sources + context.supporting_sources
  -> PromptBuilder
  -> LLMClient
  -> AnswerGenerator
  -> AnswerValidator
  -> ResponseFormatter
  -> answer with citations
```

### Компоненты к реализации

```text
src/asu_june_bot/chat/__init__.py
src/asu_june_bot/chat/models.py
src/asu_june_bot/chat/service.py
src/asu_june_bot/chat/prompt_builder.py
src/asu_june_bot/chat/answer_validator.py
src/asu_june_bot/chat/response_formatter.py

src/asu_june_bot/llm/__init__.py
src/asu_june_bot/llm/client.py
src/asu_june_bot/llm/ollama_openai.py

scripts/asu_june_bot_chat.py
```

Позже добавить API endpoint:

```text
POST /chat
```

### Chat MVP Definition of Done

- [ ] `ChatService` создан и использует `SearchService`.
- [ ] Для `refused/clarify` LLM не вызывается.
- [ ] Для `ok` LLM получает только `ContextBuilder` context, а не raw top-k.
- [ ] Ответ содержит короткий вывод, обоснование и источники.
- [ ] Ответ без источников запрещён.
- [ ] При пустом ответе LLM статус не становится `answered`.
- [ ] При timeout LLM возвращается `partial` или `error`, но не ложный `answered`.
- [ ] CLI `scripts/asu_june_bot_chat.py` работает.
- [ ] Smoke: вопрос по СоИ AD даёт осмысленный ответ с источниками.
- [ ] Smoke: внепроектный вопрос возвращает refusal без LLM.

## Следующие задачи

### Commit 4. Chat design

- [ ] Зафиксировать `chat_mvp_design.md`.
- [ ] Описать статусы `answered/refused/partial/error`.
- [ ] Описать prompt contract.
- [ ] Описать citation contract.
- [ ] Описать правила AnswerValidator.

### Commit 5. LLMClient + PromptBuilder

- [ ] Добавить OpenAI-compatible LLM client.
- [ ] Настроить Ollama base URL.
- [ ] Добавить `PromptBuilder`, который принимает `SearchResponse.context`.
- [ ] Не использовать общие знания модели без sources.

### Commit 6. ChatService + CLI

- [ ] Добавить `ChatService`.
- [ ] Добавить `scripts/asu_june_bot_chat.py`.
- [ ] Добавить smoke tests.
- [ ] Добавить markdown smoke report.

### Commit 7. POST /chat

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
