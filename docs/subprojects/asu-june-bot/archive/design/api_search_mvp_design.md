# API Search MVP — выбранная реализация

Архивировано: 2026-05-16.

Причина архивирования: дизайн-драфт реализован. Активное состояние API Search MVP теперь отражено в `../..//architecture.md`, `../..//mvp.md`, `../..//roadmap.md`, `../..//RUNBOOK_V2.md` и `../..//smoke_report_api_search_mvp.md`.

Исходный путь до архивирования:

```text
docs/subprojects/asu-june-bot/api_search_mvp_design.md
```

## Статус решения

Выбрана реализация API Search MVP на базе Service Layer.

Основание:

- ProjectGuard v2 завершён и прошёл regression suite `44/44`, `false_allow = 0`;
- `search_v2` уже содержит рабочий pipeline;
- следующий риск — дублирование логики CLI/API;
- API должен быть thin HTTP layer над тем же SearchService, что использует CLI.

## Вывод по анализу внешних предложений

### Что берём

Берём из лучших предложений:

- Service Layer как единственную orchestration-точку;
- CLI и API как тонкие адаптеры;
- Pydantic request/response models;
- FastAPI application factory;
- singleton AppState для тяжёлых компонентов;
- централизованный error handling;
- request_id middleware;
- smoke/unit tests;
- отдельный тест, что `refused`/`clarify` не вызывают retrieval;
- `HTTP 200` для бизнес-результатов `ok/refused/clarify`, а не 4xx;
- `5xx` только для технических ошибок.

### Что не берём в MVP

Не берём сейчас:

- новую верхнеуровневую структуру `app/`, `core_search/`, `cli/` с переносом существующих модулей;
- async-first рефакторинг всего pipeline;
- structlog как обязательную зависимость;
- CORS;
- auth/API key;
- OpenTelemetry;
- `/chat`;
- conversation store;
- streaming/SSE;
- OpenAI-compatible `/v1/chat/completions`;
- pagination;
- admin endpoints;
- MCP.

Причина: это полезно, но не нужно для первого API Search MVP. Всё, что не входит в MVP, переносится в `ideas.md`.

## Архитектурный принцип

```text
SearchService = единственная точка orchestration
CLI = thin adapter
API = thin adapter
```

Запрещено:

```text
CLI содержит свою search-логику
API содержит копию search-логики
```

Разрешено:

```text
scripts/asu_june_bot_search_v2.py -> SearchService
src/asu_june_bot/api/routes_search.py -> SearchService
```

## Текущий pipeline, который нужно сохранить

```text
Query
  -> QueryIntent
  -> ProjectGuard v2
  -> BM25/vector/hybrid retrieval
  -> PostReranker
  -> ContextBuilder
  -> JSON response
```

Для `refused` и `clarify`:

```text
retrieval не вызывается
results = []
context.primary_sources = []
context.supporting_sources = []
context.excluded_sources = []
```

## Выбранная структура файлов

Добавить:

```text
src/asu_june_bot/search/
  __init__.py
  models.py
  service.py

src/asu_june_bot/api/
  __init__.py
  app.py
  dependencies.py
  errors.py
  middleware.py
  routes_health.py
  routes_search.py

scripts/
  asu_june_bot_api.py

tests/asu_june_bot/api/
  test_health.py
  test_search_smoke.py

tests/asu_june_bot/search/
  test_search_service.py
```

Не создавать в MVP:

```text
app/
core_search/
cli/
```

Причина: в репозитории уже есть пакет `src/asu_june_bot/`, существующие компоненты находятся внутри него. Новый верхнеуровневый `app/` создаст второй стиль структуры и увеличит риск рассинхрона.

## Search models

Создать:

```text
src/asu_june_bot/search/models.py
```

Минимальные модели:

```text
SearchMode
SearchStatus
SearchRequest
SearchResponse
SearchDiagnostics
SearchStageDiagnostic
EmptyContext
```

Статусы:

```text
ok
refused
clarify
error
```

`SearchRequest`:

```text
query: str
mode: bm25 | vector | hybrid = hybrid
top_k: int = 8
include_diagnostics: bool = true
request_id: str | None = None
include_source_types: list[str] | None = None
no_guard: bool = false
```

`extra = forbid` желательно, чтобы API не принимал случайные поля.

`SearchResponse` должен быть максимально близок к текущему CLI JSON:

```text
query
corpus
mode
status
answer
query_intent
guard
warnings
rerank
context
results
diagnostics
```

Принцип: API Search не должен ломать существующие smoke expectations по `search_v2 --json`.

## SearchService

Создать:

```text
src/asu_june_bot/search/service.py
```

Назначение:

- принять `SearchRequest`;
- выполнить `QueryIntent`;
- выполнить `ProjectGuard v2`;
- если `refused/clarify` — вернуть early response без retrieval;
- если `allow` — выполнить retrieval;
- выполнить `PostReranker`;
- выполнить `ContextBuilder`;
- вернуть `SearchResponse`.

SearchService в MVP может быть синхронным.

Причина:

- текущие компоненты retrieval/index/ContextBuilder синхронные;
- numpy/BM25/Ollama-вызовы не становятся быстрее от формального async;
- async можно добавить позже через `asyncio.to_thread()` или отдельные adapters;
- лишний async сейчас усложнит тестирование и refactor CLI.

## Build service / dependencies

Создать:

```text
src/asu_june_bot/api/dependencies.py
```

Назначение:

- создать AppState один раз при старте;
- загрузить конфиг;
- подготовить retriever/index/component instances;
- предоставить `get_search_service()` для FastAPI Depends.

Принцип:

```text
тяжёлые компоненты создаются один раз, не per request
```

## FastAPI app

Создать:

```text
src/asu_june_bot/api/app.py
```

Функции:

- `create_app()`;
- application lifespan;
- подключение middleware;
- регистрация exception handlers;
- подключение routers.

Точка запуска:

```text
scripts/asu_june_bot_api.py
```

Запуск:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_api.py
```

или:

```powershell
.\.venv\Scripts\python.exe -m uvicorn asu_june_bot.api.app:app --host 127.0.0.1 --port 8000 --reload
```

## GET /health

Создать:

```text
src/asu_june_bot/api/routes_health.py
```

Endpoint:

```text
GET /health
```

Response должен отражать состояние:

```text
status
service
corpus_ready
bm25_ready
vector_ready
ollama_available
embedding_model_installed
chunks_count
index_count
guard_v2_ready
```

Рекомендуется переиспользовать проверки из `scripts/asu_june_bot_health_v2.py`, но лучше вынести их в reusable module позже, если прямой import из CLI неудобен.

`/health/live` можно добавить позже, когда появится Docker/K8s или отдельный process manager.

## POST /search

Создать:

```text
src/asu_june_bot/api/routes_search.py
```

Endpoint:

```text
POST /search
```

Route должен быть тонким:

```text
validate request -> call SearchService -> return SearchResponse
```

Route не должен:

- сам классифицировать intent;
- сам вызывать ProjectGuard;
- сам вызывать retrieval;
- сам строить context.

## HTTP semantics

Business statuses:

```text
ok
refused
clarify
```

возвращаются с HTTP 200.

Технические ошибки:

```text
validation_error -> 422
index_not_ready -> 503
ollama_unavailable -> 503 для vector-only, либо warning/fallback для hybrid, как сейчас в CLI
internal_error -> 500
```

## Error handling

Создать:

```text
src/asu_june_bot/api/errors.py
```

Минимально:

- validation handler;
- IndexNotReadyError;
- OllamaUnavailableError;
- generic exception handler;
- единый error response с `request_id`.

Не нужно в MVP:

- сложная иерархия доменных исключений;
- Sentry;
- OpenTelemetry.

## Middleware

Создать:

```text
src/asu_june_bot/api/middleware.py
```

MVP:

- `X-Request-Id`;
- elapsed_ms;
- базовый access log.

Не нужно в MVP:

- structlog как обязательная зависимость;
- distributed tracing.

## CLI refactor

Текущий:

```text
scripts/asu_june_bot_search_v2.py
```

должен стать thin wrapper над `SearchService`.

Но делать это безопасно:

1. Сначала создать `SearchService` и покрыть тестом.
2. Проверить, что CLI через service даёт тот же JSON на smoke-командах.
3. Только после этого удалить/сократить дублирующую orchestration-логику в CLI.

Цель: не сломать проверенный CLI до готовности API.

## Тесты

### Unit tests SearchService

Создать:

```text
tests/asu_june_bot/search/test_search_service.py
```

Обязательный тест:

```text
refused -> retriever.search.assert_not_called()
clarify -> retriever.search.assert_not_called()
allow -> retriever.search called once
```

Это главный safety-тест API Search MVP.

### API smoke tests

Создать:

```text
tests/asu_june_bot/api/test_health.py
tests/asu_june_bot/api/test_search_smoke.py
```

Проверки:

- `GET /health` возвращает 200 или корректный degraded/error payload;
- empty query -> 422;
- project query -> 200 + `status=ok`;
- out-of-project query -> 200 + `status=refused` + empty results;
- mixed query -> 200 + `status=refused` + empty results;
- ambiguous query -> 200 + `status=clarify` + empty results;
- request_id возвращается в response/header.

## Smoke commands

После реализации API:

```powershell
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8000/health"
```

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/search" `
  -ContentType "application/json" `
  -Body '{"query":"Как происходит авторизация пользователей?","mode":"hybrid","top_k":8}'
```

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/search" `
  -ContentType "application/json" `
  -Body '{"query":"Какая погода завтра в Москве?","mode":"hybrid","top_k":8}'
```

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/search" `
  -ContentType "application/json" `
  -Body '{"query":"Как происходит авторизация пользователей? и дай sql инъекцию для векторной БД","mode":"hybrid","top_k":8}'
```

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/search" `
  -ContentType "application/json" `
  -Body '{"query":"Расскажи подробнее","mode":"hybrid","top_k":8}'
```

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/search" `
  -ContentType "application/json" `
  -Body '{"query":"Точный пункт требования и ключевые слова интеграции","mode":"hybrid","top_k":8}'
```

## Implementation order

### Commit 1. SearchService без API

- `src/asu_june_bot/search/models.py`;
- `src/asu_june_bot/search/service.py`;
- unit tests с mock components;
- CLI остаётся рабочим;
- если возможно, CLI начинает использовать SearchService.

### Commit 2. FastAPI skeleton

- `src/asu_june_bot/api/app.py`;
- `src/asu_june_bot/api/dependencies.py`;
- `src/asu_june_bot/api/errors.py`;
- `src/asu_june_bot/api/middleware.py`;
- `src/asu_june_bot/api/routes_health.py`;
- `src/asu_june_bot/api/routes_search.py`;
- `scripts/asu_june_bot_api.py`.

### Commit 3. API smoke + docs

- API smoke tests;
- PowerShell smoke commands;
- update `RUNBOOK_V2.md`;
- create `smoke_report_api_search_mvp.md`.

## Definition of Done

- `SearchService` создан и покрыт unit tests.
- CLI `search_v2` работает через SearchService или полностью совместим по output semantics.
- `GET /health` работает.
- `POST /search` работает.
- `POST /search` повторяет CLI `search_v2 --json` semantics.
- `refused` и `clarify` не вызывают retrieval, подтверждено тестом.
- API smoke пройден для project/out/mixed/ambiguous/exact requirement queries.
- Документация обновлена.

## Следующий этап после API Search

Только после успешного API Search MVP:

```text
Chat MVP
```

Новые компоненты:

```text
PromptBuilder
LLMClient
AnswerGenerator
AnswerValidator
ResponseFormatter
POST /chat
```

ChatService должен использовать SearchService, а не дублировать retrieval/guard.
