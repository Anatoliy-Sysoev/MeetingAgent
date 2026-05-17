# Архитектура Project Knowledge Bot

Обновлено: 2026-05-16.

## 1. Цель архитектуры

Project Knowledge Bot — локальный project-only RAG/Chat сервис для анализа проектной документации информационной системы.

Архитектура должна обеспечить:

- локальную обработку документов;
- ответы только по загруженному корпусу источников;
- pre-retrieval guardrails;
- гибридный поиск по смыслу и точным идентификаторам;
- формирование управляемого контекста для LLM;
- ответ с citations;
- отказ без вызова LLM для внепроектных и смешанных запросов;
- наблюдаемость и baseline-оценку качества;
- локальный Web UI;
- Telegram adapter поверх локального `/chat`;
- возможность последующего выделения в отдельный репозиторий.

## 2. Архитектурные принципы

### 2.1 Разделение ответственности

```text
/search -> evidence/context
/chat   -> answer with citations
/ui     -> local browser client over /chat
Telegram adapter -> long polling client over local /chat
```

`/search` не генерирует осмысленный ответ. Он возвращает источники, context buckets, guard diagnostics и retrieval diagnostics.

`/chat` не реализует собственный retrieval. Он использует `ChatService`, который вызывает `SearchService`.

### 2.2 Pre-retrieval safety

Вопрос проходит через `ProjectGuard v2` до retrieval.

```text
refused -> retrieval не вызывается, LLM не вызывается
clarify -> retrieval не вызывается, LLM не вызывается
allow   -> retrieval выполняется
```

Критический критерий:

```text
false_allow = 0
```

### 2.3 Local-first

На MVP данные не отправляются во внешние LLM API. Runtime использует локальную Ollama через OpenAI-compatible endpoint.

Telegram adapter использует внешний Telegram Bot API только для транспорта сообщений. Содержательный RAG/LLM ответ формируется локальным `/chat`.

### 2.4 Evidence-first

Ответ может быть сформирован только по `primary_sources` и `supporting_sources`.

`excluded_sources` не передаются в LLM prompt.

### 2.5 Измеримость изменений

Изменения retrieval/context/quality должны сравниваться с baseline eval. QH-1 создал baseline/eval-контур, QH-2/QH-3/QH-4 добавлены как измеримые слои с diagnostics и тестами.

## 3. Текущий статус архитектуры

Реализовано:

```text
Extraction/Chunking v2.1
Index/Search v2
Search Quality v2.2
ProjectGuard v2
SearchService
FastAPI GET /health
FastAPI POST /search
ChatService
CLI chat
FastAPI POST /chat
Local Web UI GET / and GET /ui
Telegram adapter over local /chat
ChatRunsLogger
QH-1 Eval Baseline
QH-2 Source Quality Filter
QH-3 Parent Expansion
QH-4 Semantic Warnings / Manual Labels
QH-5 Release Gate
```

Ожидает локальной проверки:

```text
API/UI/Telegram smoke на рабочем ПК
QH after_qh eval
QH-5 local validation
```

Рабочая LLM для MVP:

```text
qwen2.5:7b-instruct
```

Не использовать как default:

```text
qwen3:4b
qwen3:8b
```

Причины:

```text
qwen3:4b -> llm_empty_response / finish_reason=length
qwen3:8b -> timeout/обрыв на локальном CPU runtime
```

## 4. Логическая архитектура

```text
User
  -> CLI / FastAPI / Web UI / Telegram adapter
  -> SearchService
      -> QueryIntent
      -> ProjectGuard v2
      -> BM25 Search
      -> Vector Search
      -> Hybrid merge
      -> PostReranker
      -> ContextBuilder
          -> QH-2 Source Quality Filter
          -> QH-3 Parent Expansion
  -> ChatService
      -> PromptBuilder
      -> LLMClient
      -> AnswerValidator
      -> QH-4 SemanticWarningAnalyzer
      -> ResponseFormatter
      -> ChatRunsLogger
  -> Response
```

## 5. Runtime-компоненты

### 5.1 Ingestion Layer

Файлы:

```text
scripts/asu_june_bot_extract_text_v2.py
src/asu_june_bot/ingestion/
```

Назначение:

- чтение `project_root` из `config.yaml`;
- исключение временных файлов, архивов, HTML/system exports;
- извлечение blocks из DOCX/XLSX/PDF/PPTX/HTML/text;
- сохранение `data/asu_june_bot/extracted_v2/blocks.jsonl`.

### 5.2 Chunking Layer

Файл:

```text
scripts/asu_june_bot_build_chunks_v2.py
```

Назначение:

- сборка parent/child chunks;
- преобразование таблиц в chunk-строки;
- заполнение metadata;
- запись `data/asu_june_bot/chunks_v2.jsonl`.

### 5.3 Index Layer

Файлы:

```text
scripts/asu_june_bot_build_index_v2.py
data/asu_june_bot/embeddings_cache_v2.jsonl
data/asu_june_bot/numpy_index_v2/
```

Назначение:

- embeddings через `bge-m3`;
- resumable cache;
- numpy vector index;
- metadata index.

Индексируются только source types:

```text
project_doc
meeting_artifact
analytical_note
instruction
```

### 5.4 Retrieval Layer

Файлы:

```text
src/asu_june_bot/retrieval/bm25.py
src/asu_june_bot/retrieval/vector.py
src/asu_june_bot/retrieval/hybrid.py
src/asu_june_bot/retrieval/query_intent.py
src/asu_june_bot/retrieval/post_rerank.py
src/asu_june_bot/retrieval/context_builder.py
src/asu_june_bot/retrieval/source_quality.py
src/asu_june_bot/retrieval/parent_expansion.py
```

Назначение:

- BM25 для точных пунктов, кодов, аббревиатур и имен компонентов;
- vector search для смысловых вопросов;
- hybrid merge;
- rerank по intent;
- QH-2 оценка качества источников;
- QH-3 bounded expansion слабых источников;
- сборка context buckets.

### 5.5 Guardrails Layer

Файлы:

```text
src/asu_june_bot/guardrails/models.py
src/asu_june_bot/guardrails/segmenter.py
src/asu_june_bot/guardrails/scope_classifier.py
src/asu_june_bot/guardrails/aggregator.py
src/asu_june_bot/guardrails/policy.py
src/asu_june_bot/guardrails/project_guard.py
```

Решения:

```text
allow
refuse
clarify
```

### 5.6 SearchService

Файлы:

```text
src/asu_june_bot/search/models.py
src/asu_june_bot/search/service.py
scripts/asu_june_bot_search_v2.py
```

Назначение:

- единая orchestration-точка поиска для CLI и API;
- выполнение guard до retrieval;
- возврат `SearchResponse`.

### 5.7 API + Web UI Layer

Файлы:

```text
src/asu_june_bot/api/app.py
src/asu_june_bot/api/dependencies.py
src/asu_june_bot/api/routes_health.py
src/asu_june_bot/api/routes_search.py
src/asu_june_bot/api/routes_chat.py
src/asu_june_bot/api/routes_ui.py
src/asu_june_bot/api/middleware.py
src/asu_june_bot/api/errors.py
scripts/asu_june_bot_api.py
```

Endpoints:

```http
GET  /
GET  /ui
GET  /health
POST /search
POST /chat
```

### 5.8 Chat Layer

Файлы:

```text
src/asu_june_bot/chat/models.py
src/asu_june_bot/chat/service.py
src/asu_june_bot/chat/prompt_builder.py
src/asu_june_bot/chat/answer_validator.py
src/asu_june_bot/chat/response_formatter.py
src/asu_june_bot/chat/semantic_warnings.py
src/asu_june_bot/llm/client.py
src/asu_june_bot/llm/ollama_openai.py
scripts/asu_june_bot_chat.py
```

Pipeline:

```text
ChatRequest
  -> SearchService.search()
  -> if refused/clarify/error: return without LLM
  -> PromptBuilder(context.primary_sources + context.supporting_sources)
  -> LLMClient.generate()
  -> AnswerValidator
  -> SemanticWarningAnalyzer
  -> ChatResponse
  -> ChatRunsLogger
```

### 5.9 Telegram Adapter

Файлы:

```text
src/asu_june_bot/telegram_bot.py
scripts/asu_june_bot_telegram.py
docs/subprojects/asu-june-bot/telegram.md
```

Назначение:

- long polling Telegram Bot API;
- отправка текстового вопроса в локальный `POST /chat`;
- возврат ответа и источников в Telegram;
- ограничение доступа через `ASU_JUNE_BOT_ALLOWED_CHAT_IDS`.

### 5.10 Observability Layer

Файлы:

```text
src/asu_june_bot/observability/chat_runs.py
data/asu_june_bot/chat_runs.jsonl
```

Назначение:

- append-only логирование chat-запусков;
- накопление dataset;
- ручная разметка `manual_label` / `manual_issue`;
- анализ latency, модели, sources, validation errors и semantic warnings.

### 5.11 Evaluation Layer

Файлы:

```text
src/asu_june_bot/eval/models.py
src/asu_june_bot/eval/checks.py
src/asu_june_bot/eval/runner.py
src/asu_june_bot/eval/report.py
src/asu_june_bot/eval/loader.py
scripts/asu_june_bot_chat_eval.py
eval/cases/base.jsonl
eval/golden_answers/*.md
```

Назначение:

- deterministic baseline checks;
- отчеты JSON/Markdown;
- сравнение `baseline` и `after_qh`.

### 5.12 QH Release Gate

Файлы:

```text
src/asu_june_bot/qh/release_gate.py
scripts/asu_june_bot_qh_gate.py
```

Назначение:

- фиксировать, что QH-1..QH-4 реализованы;
- не считать QH-5 пройденным без локального regression/smoke/eval;
- не начинать Docker до фактического QH-5 passed.

## 6. API-контракты

### 6.1 GET /health

Назначение: проверка готовности корпуса, индекса, guard, Ollama и embedding-модели.

### 6.2 POST /search

Назначение: диагностический поиск без генерации ответа.

Request:

```json
{
  "query": "Как происходит авторизация пользователей?",
  "mode": "hybrid",
  "top_k": 8
}
```

Response:

```text
status
query_intent
guard
context.primary_sources
context.supporting_sources
context.excluded_sources
context.diagnostics.source_quality_filter
context.diagnostics.parent_expansion
results
warnings
diagnostics
```

### 6.3 POST /chat

Назначение: ответ с источниками.

Request:

```json
{
  "query": "Как происходит авторизация пользователей?",
  "mode": "hybrid",
  "top_k": 5,
  "model": "qwen2.5:7b-instruct",
  "max_tokens": 500,
  "timeout_sec": 300
}
```

Response:

```text
status
query
answer
sources
search
warnings.semantic
diagnostics.semantic_warnings
diagnostics
```

Основные statuses:

```text
answered
refused
clarify
no_sources
llm_error
llm_empty_response
validation_failed
```

### 6.4 Input limits

Единый лимит:

```text
MAX_QUERY_CHARS = 2000
```

Применяется в:

```text
SearchRequest
ChatRequest
POST /search
POST /chat
Web UI
Telegram adapter
```

## 7. Данные и артефакты runtime

Runtime-данные не коммитятся:

```text
data/asu_june_bot/extracted_v2/
data/asu_june_bot/chunks_v2.jsonl
data/asu_june_bot/embeddings_cache_v2.jsonl
data/asu_june_bot/numpy_index_v2/
data/asu_june_bot/chat_runs.jsonl
eval/reports/
```

Версионируются:

```text
eval/cases/base.jsonl
eval/golden_answers/*.md
docs/subprojects/asu-june-bot/**/*.md
```

## 8. Безопасность и приватность

Правила:

- проектные источники не отправляются во внешние LLM API;
- отказные и уточняющие запросы не доходят до LLM;
- sensitive-запросы блокируются до retrieval;
- Telegram token не коммитится;
- runtime logs не должны содержать секреты;
- `.env`, токены, пароли, config secrets не индексируются и не раскрываются;
- future RBAC по источникам должен добавляться до многопользовательского режима.

## 9. Качество и ограничения

Текущий `AnswerValidator` выполняет structural validation:

```text
пустой ответ
наличие sources
наличие ссылок [Sx]
unknown citations
external knowledge markers
answer length
citation density / coverage
```

QH-2 добавляет source quality diagnostics:

```text
weak_sources
weak_reasons
primary eligibility
```

QH-3 добавляет bounded parent expansion:

```text
только weak source
только соседний/родительский кандидат из уже найденного набора
max_parent_chars
```

QH-4 добавляет warning-only слой:

```text
weak_sources_present
weak_primary_fallback
parent_expansion_applied
low_source_count
low_citation_coverage
structural_validation_errors
```

Не выполняется hard-fail semantic/factual validation:

```text
поддерживается ли каждое утверждение конкретным source text;
не сделала ли модель спорный вывод из короткого UML/heading/caption chunk;
нет ли semantic hallucination при формально корректных [Sx].
```

## 10. Планируемые контуры зрелости

### MVP local

```text
один пользователь
локальный корпус
локальный индекс
локальная LLM
CLI + FastAPI + Web UI + Telegram adapter
```

### Team local/server

```text
общий сервер индекса
API service
простая web оболочка
централизованные eval reports
```

### Enterprise-ready

```text
RBAC по источникам
аудит запросов
job queue для reindex
object storage для runtime artifacts
GPU inference через vLLM
monitoring dashboards
```

## 11. Связь с продуктовой документацией

Архитектура связана с:

```text
README.md                      входная точка
TOMORROW_START.md              восстановление и сдачный smoke
QH_STATUS.md                   статус QH этапов
mvp.md                         функционально-технический scope
roadmap.md                     план-график
RUNBOOK_V2.md                  эксплуатация и проверки
decisions.md                   архитектурные решения
product/                       продуктовый контур
smoke_report_*.md              доказательства прохождения этапов
```
