# Контекст Подпроекта Asu June Bot

Обновлено: 2026-05-14.

## Назначение

Asu June Bot — отдельный подпроект внутри MeetingAgent для разработки локального AI-агента по проекту ЦП УПКС.

Бот должен отвечать не как универсальный ChatGPT, а как проектный ассистент системного аналитика:

- искать факты в проектной документации;
- давать структурированные ответы;
- ссылаться на документы, разделы, пункты и фрагменты;
- явно отделять подтвержденные факты от вывода;
- отказывать на вопросы вне проекта или без источников.

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

### Config / audit v2.1

Добавлено:

```text
scripts/asu_june_bot_apply_config_v2_1.py
scripts/asu_june_bot_audit_sources_v2.py
```

`apply_config_v2_1` обновляет локальный `config.yaml` и делает backup.

`audit_sources_v2` проверяет покрытие и причины исключения файлов.

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

## Результаты search smoke

### `Что входит в Паспорт ИС?`

После rerank BM25 top-1/top-2 поднимает правильный chunk из Паспорт ИС с границами описания: архитектурные и эксплуатационные сведения, платформа ЦП УПКС, модуль СМР и базовые сервисы Front/Core/Disk/Building/Approvals/Notifications/Catalog/Help/Mdr.

Проблема: в top-8 всё ещё есть chunks по программному обеспечению, поддержке и vector-only шум. Для Chat MVP нужен intent-aware context builder, а не прямая отправка всего top-k в LLM.

### `Какие интеграции заявлены в проекте?`

Retrieval достаточен для API Search MVP:

- ЦТА поднимает `Blitz, AD, S3 Minio, Exchange, КШД`;
- Паспорт ИС поднимает `Active Directory, Blitz IDP, MDR, почтовый сервер, SIEM`;
- ФТТ поднимает КШД/SOAP;
- ПР поднимает взаимодействие со смежными модулями.

### `ФТТ 4.2.5 НОВАДОК ЭЦП`

Retrieval практически пригоден:

- BM25/hybrid поднимают ФТТ в top-1/top-2;
- в top-5 есть интеграционная строка `ЦП УПКС -> НОВАДОК`;
- встреча `ФТТ_ИД` поднимается как полезный аналитический источник;
- проблема: metadata `section/requirement_id` шумит и иногда показывает `10.2`, хотя текст содержит `4.2.5`.

## Ближайшая цель

Не переходить напрямую к Chat MVP. Сначала выполнить Search Quality v2.2:

```text
query_intent -> post_rerank -> context_builder -> search diagnostics -> smoke report
```

Нужно добавить:

- `src/asu_june_bot/retrieval/query_intent.py`;
- `src/asu_june_bot/retrieval/post_rerank.py`;
- `src/asu_june_bot/retrieval/context_builder.py`;
- diagnostics в JSON search output: `query_intent`, `rerank_labels`, `primary_sources`, `supporting_sources`;
- markdown smoke-отчет `docs/subprojects/asu-june-bot/search_smoke_report_2026-05-14.md`.

К API Search переходить только после успешного smoke с primary/supporting sources.
