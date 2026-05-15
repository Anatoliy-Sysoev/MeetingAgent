# Контекст Подпроекта Asu June Bot

Обновлено: 2026-05-15.

## Назначение

Asu June Bot — отдельный подпроект внутри MeetingAgent для разработки локального AI-агента по проекту ЦП УПКС.

Бот должен отвечать не как универсальный ChatGPT, а как проектный ассистент системного аналитика:

- искать факты в проектной документации;
- давать структурированные ответы;
- ссылаться на документы, разделы, пункты и фрагменты;
- явно отделять подтвержденные факты от вывода;
- отказывать на вопросы вне проекта или без источников;
- не запускать retrieval для внепроектных, mixed-scope и ambiguous-запросов.

## Текущий статус

Asu June Bot v2.1/v2.2 доведён до уровня **API Search MVP**.

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

Следующий этап:

```text
Chat MVP
```

## Почему /search не даёт осмысленный ответ

`POST /search` — это endpoint поиска, а не чат.

Он возвращает:

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

Его задача — доказать, что retrieval безопасен и качественен:

```text
project query -> sources/context
out-of-project query -> refused без retrieval
ambiguous query -> clarify без retrieval
project + unknown tail -> refused без retrieval
```

Осмысленный ответ должен появиться на следующем этапе — **Chat MVP**.

Chat MVP будет использовать `/search`/`SearchService` как источник evidence/context:

```text
Question
  -> SearchService.search()
  -> ContextBuilder context
  -> PromptBuilder
  -> LLMClient
  -> AnswerGenerator
  -> AnswerValidator
  -> ResponseFormatter
  -> answer with citations
```

## Ключевое решение v2.1

Asu June Bot строит собственный независимый pipeline v2.1 и не опирается на старый `scripts/02_extract_text.py`.

Старый pipeline MeetingAgent остается только как v1/baseline:

```text
run_full_rag.ps1
  -> scripts/01_inventory.py
  -> scripts/02_extract_text.py
  -> scripts/03_build_index.py
  -> scripts/05_build_numpy_index.py
```

Новый pipeline Asu June Bot:

```text
scripts/asu_june_bot_apply_config_v2_1.py
  -> scripts/asu_june_bot_extract_text_v2.py
  -> scripts/asu_june_bot_build_chunks_v2.py
  -> scripts/asu_june_bot_audit_sources_v2.py
  -> scripts/asu_june_bot_build_index_v2.py
  -> scripts/asu_june_bot_health_v2.py
  -> scripts/asu_june_bot_search_v2.py
  -> src/asu_june_bot/search/service.py
  -> src/asu_june_bot/api/app.py
```

Все runtime-данные v2 пишутся в:

```text
data/asu_june_bot/
```

и не перезаписывают:

```text
data/chunks.jsonl
data/embeddings_cache.jsonl
data/numpy_index/
```

## Почему выделен отдельный подпроект

Попытка развивать project-only чат в `scripts/09_chat.py` показала архитектурный риск: один скрипт начал смешивать CLI, guard, retrieval, query expansion, document expansion, LLM-вызов, fallback и форматирование ответа.

Решение: не продолжать раздувать `09_chat.py`, а выделить Asu June Bot в отдельный подпроект с собственной архитектурой, документацией, API-контрактом и eval-набором.

`09_chat.py` остается prototype, но новая реализация должна идти модульно.

## Проектная область знаний

Основная предметная область — проект ЦП УПКС: «Цифровая платформа управления проектами капитального строительства».

Ключевые документы и источники:

- ФТТ;
- ЦТА;
- проектные решения по модулям;
- соглашения об интеграции;
- Паспорт ИС;
- ПМИ и сценарии испытаний;
- руководства администратора ИС и ИБ;
- протоколы встреч;
- решения, задачи, риски и открытые вопросы;
- маппинги НСИ / СоИ / MDR;
- BPMN/PUML/Drawio схемы.

## Что исключено из основного корпуса v2.1

Папка `Система` и связанные технические выгрузки исключаются из основного project-only corpus:

```text
**/Система/**
**/asu_docs_export/**
**/asu_admin_export/**
**/docs_html/**
**/docs_text/**
**/pages_html/**
**/pages_text/**
**/site_review_runs/**
**/playwright/**
**/exports/**
**/screenshots/**
**/*.har
```

Причина: это технические HTML/JSON/HAR выгрузки сайта/админки. Они создают `system_export`, `html_text` и `unknown` chunks и ухудшают качество поиска по проектной документации.

Если такие данные понадобятся, их нужно выделять в отдельный `system_export_corpus`, а не смешивать с основным корпусом проектной документации.

## Реализовано

### Extraction v2.1

Добавлен самостоятельный extractor v2.1:

```text
scripts/asu_june_bot_extract_text_v2.py
src/asu_june_bot/ingestion/
```

Extractor v2.1:

- заново сканирует `project_root` из `config.yaml`;
- не читает старую папку `data/extracted_text`;
- поддерживает DOCX, XLSX/XLSB, PDF, PPTX, HTML и текстовые форматы;
- для DOCX читает paragraph/table в исходном порядке документа;
- для DOCX таблиц определяет вероятную строку заголовков;
- для DOCX таблиц создает blocks `table` и `table_row`;
- для XLSX использует `openpyxl`, извлекает листы, строки, headers и cells;
- для XLSB использует `pandas` + `pyxlsb`;
- жестко исключает шумные system exports и временные файлы.

Выход extractor v2.1:

```text
data/asu_june_bot/extracted_v2/documents.jsonl
data/asu_june_bot/extracted_v2/blocks.jsonl
data/asu_june_bot/extracted_v2/extraction_v2_report.json
data/asu_june_bot/extracted_v2/extraction_v2_report.md
```

### Chunking v2.1

Chunking v2 читает только:

```text
data/asu_june_bot/extracted_v2/blocks.jsonl
```

Сборщик:

- строит parent/child chunks из blocks v2;
- превращает строки таблиц в child chunks;
- заполняет `requirement_id`, `sections`, `document_type`, `source_type`, `integration`, `protocol`;
- пишет `data/asu_june_bot/chunks_v2.jsonl`;
- пишет `chunking_v2_report.json` и `chunking_v2_report.md`;
- не трогает старые `data/chunks.jsonl`, `data/embeddings_cache.jsonl`, `data/numpy_index`.

### Index/Search v2

Добавлены:

```text
scripts/asu_june_bot_build_index_v2.py
scripts/asu_june_bot_health_v2.py
scripts/asu_june_bot_search_v2.py
monitor_asu_june_bot_index_v2.ps1
register_asu_june_bot_index_v2_watchdog.ps1
```

Выходы index v2:

```text
data/asu_june_bot/embeddings_cache_v2.jsonl
data/asu_june_bot/numpy_index_v2/
data/asu_june_bot/index_v2_report.json
```

Индекс v2 использует только source types:

```text
project_doc
meeting_artifact
analytical_note
instruction
```

`code`, `runtime_export`, `system_export`, `unknown` не индексируются в основном project-only индексе.

### Search Quality v2.2

Реализовано:

```text
src/asu_june_bot/retrieval/query_intent.py
src/asu_june_bot/retrieval/post_rerank.py
src/asu_june_bot/retrieval/context_builder.py
```

`search_v2` теперь возвращает:

```text
query_intent
guard
rerank
context.primary_sources
context.supporting_sources
context.excluded_sources
results
warnings
```

Проверено:

- `Паспорт ИС overview` возвращает обзорный chunk в `primary_sources`;
- `ФТТ 4.2.5` возвращает точную строку ФТТ в `primary_sources`;
- `Интеграции` возвращают ЦТА/Паспорт ИС/ФТТ/СоИ как primary/supporting context;
- JSON сохраняется через `--output` без mojibake.

### ProjectGuard v2

Реализовано:

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

Проверено:

```text
45 regression cases passed
false_allow = 0
```

Важное policy-level правило:

```text
project + unknown tail -> refused / in_project_query_contains_unclassified_segment
```

### SearchService

Реализовано:

```text
src/asu_june_bot/search/__init__.py
src/asu_june_bot/search/models.py
src/asu_june_bot/search/service.py
```

CLI `scripts/asu_june_bot_search_v2.py` теперь является thin wrapper над `SearchService`.

Проверено:

```text
SearchService unit tests: 4 passed
refused smoke: retrieval_called=false
project smoke: retrieval_called=true
```

### API Search MVP

Реализовано:

```text
src/asu_june_bot/health/__init__.py
src/asu_june_bot/health/service.py
src/asu_june_bot/api/__init__.py
src/asu_june_bot/api/app.py
src/asu_june_bot/api/dependencies.py
src/asu_june_bot/api/errors.py
src/asu_june_bot/api/middleware.py
src/asu_june_bot/api/routes_health.py
src/asu_june_bot/api/routes_search.py
scripts/asu_june_bot_api.py
```

Endpoints:

```text
GET /health
POST /search
```

Проверено:

```text
API health tests: 1 passed
API search smoke tests: 3 passed
API server starts successfully
POST /search works
```

## Текущий локальный результат

### Corpus / index

```text
documents = 213
blocks = 31076
chunks_v2 = 31302
indexed_chunks = 31285
skipped_code_chunks = 17
embedding_model = bge-m3
embedding_dim = 1024
```

### Health

`asu_june_bot_health_v2.py` показывает:

```text
status = ok
vector_ready = true
bm25_ready = true
chunks_v2 = 31302
embeddings_cache_v2 = 31285
manifest_count = 31285
index_metadata = 31285
ollama_available = true
embedding_model_installed = true
```

## Ближайшая цель

Следующий шаг — Chat MVP:

```text
src/asu_june_bot/chat/
src/asu_june_bot/llm/
scripts/asu_june_bot_chat.py
```

Chat MVP должен использовать уже готовый `SearchService`, а не дублировать guard/retrieval/context.

## Не делать дальше

- Не пытаться заставить `/search` писать осмысленные ответы.
- Не отправлять raw hybrid top-k в LLM.
- Не развивать старый `scripts/09_chat.py` как основной runtime.
- Не индексировать `Система` в основной project-only корпус.
- Не подключать NeMo Guardrails, LangGraph, Dify/RAGFlow как runtime MVP.
