# TODO Asu June Bot

Обновлено: 2026-05-15.

## Текущий статус

Этап ProjectGuard v2 завершён.

Финальный regression результат:

```json
{
  "total": 44,
  "passed": 44,
  "failed": 0,
  "false_allow": 0,
  "false_refuse": 0,
  "false_clarify": 0,
  "failed_ids": [],
  "false_allow_ids": [],
  "false_refuse_ids": [],
  "false_clarify_ids": []
}
```

Критический критерий выполнен:

```text
false_allow = 0
```

Это означает, что внепроектные, mixed-scope, offensive/security и prompt-injection запросы не проходят дальше в retrieval/LLM.

Финальный отчёт:

```text
docs/subprojects/asu-june-bot/smoke_report_project_guard_v2.md
```

## Выбранный дизайн API Search MVP

Дизайн зафиксирован:

```text
docs/subprojects/asu-june-bot/api_search_mvp_design.md
```

Выбранный принцип:

```text
SearchService = единственная orchestration-точка
CLI = thin adapter
API = thin adapter
```

Не делаем две разные реализации поиска для CLI и API.

## Текущий runtime-пайплайн

```text
Query
  -> QueryIntent
  -> ProjectGuard v2
  -> BM25/vector/hybrid retrieval
  -> PostReranker
  -> ContextBuilder
  -> JSON response
```

При `refused` или `clarify` retrieval не вызывается.

## Commit 1. SearchService без API

Статус: реализовано и локально проверено.

Добавлено:

```text
src/asu_june_bot/search/__init__.py
src/asu_june_bot/search/models.py
src/asu_june_bot/search/service.py
tests/asu_june_bot/search/test_search_service.py
```

Обновлено:

```text
scripts/asu_june_bot_search_v2.py
```

Проверено:

```text
SearchService unit tests: 4 passed
ProjectGuard base tests: 8 passed
ProjectGuard regression cases: 44 passed
refused smoke: retrieval_called=false
project smoke: retrieval_called=true
```

Отчёт:

```text
docs/subprojects/asu-june-bot/smoke_report_search_service_commit1.md
```

## Commit 2. FastAPI skeleton

Статус: реализовано, требуется локальный прогон.

Добавлено reusable health layer:

```text
src/asu_june_bot/health/__init__.py
src/asu_june_bot/health/service.py
```

Добавлен API layer:

```text
src/asu_june_bot/api/__init__.py
src/asu_june_bot/api/app.py
src/asu_june_bot/api/dependencies.py
src/asu_june_bot/api/errors.py
src/asu_june_bot/api/middleware.py
src/asu_june_bot/api/routes_health.py
src/asu_june_bot/api/routes_search.py
```

Добавлен запуск API:

```text
scripts/asu_june_bot_api.py
```

Добавлены tests:

```text
tests/asu_june_bot/api/test_health.py
tests/asu_june_bot/api/test_search_smoke.py
```

Что реализовано:

- FastAPI application factory `create_app()`;
- application lifespan с `AppState`;
- singleton `SearchService` и `HealthService` на приложение;
- request id middleware: `X-Request-Id`;
- elapsed time header: `X-Elapsed-Ms`;
- error handlers: validation/api/internal;
- `GET /health` через `HealthService`;
- `POST /search` через `SearchService`;
- Pydantic request model для `/search`, совместимый с Pydantic v1;
- API tests с fake services без реального индекса.

Проверить локально:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\api\test_health.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\api\test_search_smoke.py -q
```

Если FastAPI/uvicorn не установлены:

```powershell
.\.venv\Scripts\python.exe -m pip install fastapi uvicorn
```

Запуск API:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_api.py --host 127.0.0.1 --port 8000
```

Smoke после запуска:

```powershell
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8000/health"

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/search" `
  -ContentType "application/json" `
  -Body '{"query":"Какая погода завтра в Москве?","mode":"hybrid","top_k":8}'

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/search" `
  -ContentType "application/json" `
  -Body '{"query":"СоИ AD как происходит авторизация пользователей?","mode":"hybrid","top_k":8}'
```

Ожидаемо:

```text
/health: status=ok, service=asu_june_bot
weather search: status=refused, results=[], retrieval_called=false
project search: status=ok, results!=[], retrieval_called=true
```

## Готово в v2.1 / Search Quality v2.2

- независимый pipeline v2.1: `apply_config_v2_1 -> extract_text_v2 -> chunks_v2 -> audit_sources_v2 -> build_index_v2 -> health_v2 -> search_v2`;
- основной corpus очищен от `Система`, `asu_docs_export`, `asu_admin_export`, `site_review_runs`, `playwright`, `exports`, `.har`, временных файлов, медиа и архивов;
- extraction/chunking v2.1 пройдены: `documents=213`, `blocks=31076`, `chunks=31302`;
- `system_export` отсутствует в основном корпусе;
- `embeddings_cache_v2` собран: `cached_after=31285`, `missing_after=0`, `embedding_model=bge-m3`, `max_embedding_chars=3000`;
- `numpy_index_v2` собран: `index_built=true`, `index_count=31285`, `embedding_dim=1024`;
- из индекса исключены `code` chunks: `chunks_skipped_by_source_type=17`;
- `health_v2`: `status=ok`, `vector_ready=true`, `bm25_ready=true`, `ollama_available=true`, `embedding_model_installed=true`;
- `search_v2` поддерживает `bm25`, `vector`, `hybrid`;
- `search_v2` поддерживает `--output` для UTF-8 JSON без PowerShell redirection;
- `search_v2` возвращает `query_intent`, `guard`, `rerank`, `context.primary_sources`, `context.supporting_sources`, `context.excluded_sources`;
- `QueryIntent` реализован;
- `PostReranker` реализован;
- `ContextBuilder` реализован;
- ProjectGuard v2 реализован и проверен regression suite;
- для точного `requirement_lookup` primary содержит точный пункт, а не смежные требования;
- один chunk не должен дублироваться между context buckets;
- JSON smoke-файлы сохраняются без mojibake.

## Готово в ProjectGuard v2

Модули:

```text
src/asu_june_bot/guardrails/models.py
src/asu_june_bot/guardrails/segmenter.py
src/asu_june_bot/guardrails/scope_classifier.py
src/asu_june_bot/guardrails/aggregator.py
src/asu_june_bot/guardrails/policy.py
src/asu_june_bot/guardrails/project_guard.py
```

Тесты и eval:

```text
tests/asu_june_bot/test_project_guard_v2.py
tests/asu_june_bot/guard_v2_cases.jsonl
tests/asu_june_bot/test_project_guard_v2_cases.py
scripts/asu_june_bot_guard_v2_eval.py
```

Покрытые категории:

```text
project
out_of_project
mixed weather/lifestyle
mixed code/game
mixed security/offensive
jailbreak/prompt-injection
ambiguous
boundary project-tech vs arbitrary-code
hidden out-of-scope tail
```

Команды проверки:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\test_project_guard_v2.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\test_project_guard_v2_cases.py -q
.\.venv\Scripts\python.exe scripts\asu_june_bot_guard_v2_eval.py --print-failed --fail-on-error
```

## Проверенный baseline retrieval/context

### Паспорт ИС overview

```text
status = ok
intent = document_overview
guard = allow
primary_sources = 1
supporting_sources = 0
excluded_sources = 15
```

Primary source — обзорный chunk `Границы описания` из `ЦП УПКС_Паспорт ИС_v1.3.2`.

### ФТТ 4.2.5 НОВАДОК ЭЦП

```text
status = ok
intent = requirement_lookup
guard = allow
mentioned_sections = [4.2.5]
primary_sources = 1
supporting_sources = 5
excluded_sources = 10
```

Primary source — ФТТ, Таблица 8, строка 44, № `4.2.5`.

### Интеграции

Retrieval/context пригоден для API Search MVP:

- ЦТА;
- Паспорт ИС;
- ФТТ;
- СоИ AD;
- СоИ Справочники;
- дополнительные supporting chunks по КШД/SOAP, LDAPS/SMTP, S3/Minio, SIEM.

## Commit 3. API smoke + docs

Следующий этап после локальной проверки Commit 2:

- [ ] Добавить PowerShell smoke-команды в `RUNBOOK_V2.md`.
- [ ] Создать `docs/subprojects/asu-june-bot/smoke_report_api_search_mvp.md`.
- [ ] Обновить `docs/context.md` и `docs/todo.md` по результатам API smoke.

## Минимальные endpoints

```text
GET /health
POST /search
```

### Требования к GET /health

Должен возвращать состояние:

```text
service = ok
corpus_ready
bm25_ready
vector_ready
ollama_available
embedding_model_installed
index_count
chunks_count
guard_v2_ready
```

### Требования к POST /search

Должен использовать тот же pipeline, что CLI `search_v2`:

```text
QueryIntent -> ProjectGuard v2 -> Retrieval -> PostReranker -> ContextBuilder -> JSON response
```

При `refused` или `clarify` retrieval не вызывается.

Response должен содержать:

```text
status
query
query_intent
guard
context.primary_sources
context.supporting_sources
context.excluded_sources
results
warnings
diagnostics
```

## Definition of Done для API Search

- [x] `SearchService` создан и покрыт unit tests.
- [x] CLI `search_v2` работает через `SearchService` или полностью совместим по output semantics.
- [x] `GET /health` реализован.
- [x] `POST /search` реализован.
- [ ] `GET /health` работает локально.
- [ ] `POST /search` работает локально.
- [ ] `POST /search` возвращает `refused` без retrieval для внепроектных запросов.
- [ ] `POST /search` возвращает `clarify` без retrieval для ambiguous-запросов.
- [ ] `POST /search` возвращает `ok` и context для проектных запросов.
- [ ] Формат ответа совпадает с CLI `search_v2 --json` semantics.
- [ ] Есть smoke-команды curl/PowerShell для API.
- [ ] Документация API добавлена в runbook.

## После API Search

Следующий этап после стабильного `/search` — Chat MVP:

- [ ] `PromptBuilder`.
- [ ] `LLMClient` через OpenAI-compatible API.
- [ ] `AnswerValidator`.
- [ ] `ResponseFormatter`.
- [ ] CLI `scripts/asu_june_bot_chat.py`.
- [ ] API `POST /chat`.

Правило: не отправлять raw hybrid top-k напрямую в LLM. В LLM передавать только подготовленный `ContextBuilder` context.

## Рекомендуемые решения

- Qdrant пока не подключать; numpy index v2 достаточен для MVP.
- BM25 in-memory оставить до API Search; storage потребуется позже.
- `Система` не возвращать в основной corpus; при необходимости сделать отдельный `system_export_corpus`.
- Ссылки на Яндекс.Диск добавлять позже через `data/asu_june_bot/source_links.json`.
- До Chat MVP не делать fine-tuning, UI и agentic tool-use.
- Не возвращаться к бесконечному расширению одного списка regex как основной архитектуре guard.

## Не делать

- Не переходить к Chat MVP напрямую от CLI `search_v2`.
- Не отправлять в LLM все top-8 как есть.
- Не индексировать `Система` в основной corpus.
- Не развивать старый `scripts/09_chat.py` как основной runtime.
- Не делать UI до API Search.
- Не подключать NeMo Guardrails, LangGraph, Dify/RAGFlow как runtime MVP.
- Не вводить top-level `app/` / `core_search/` структуру в текущем репозитории.
- Не делать async-first рефакторинг всего pipeline в API Search MVP.
