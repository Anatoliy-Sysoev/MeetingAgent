# Контекст Подпроекта Asu June Bot

Обновлено: 2026-05-12.

## Назначение

Asu June Bot — отдельный подпроект внутри MeetingAgent для разработки локального AI-агента по проекту ЦП УПКС.

Бот должен отвечать не как универсальный ChatGPT, а как проектный ассистент системного аналитика:

- искать факты в проектной документации;
- давать структурированные ответы;
- ссылаться на документы, разделы, пункты и фрагменты;
- явно отделять подтвержденные факты от вывода;
- отказывать на вопросы вне проекта или без источников.

## Ключевое Решение По v2

Asu June Bot теперь строит собственный независимый pipeline v2 и не опирается на старый `scripts/02_extract_text.py`.

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
run_asu_june_bot_rebuild_v2.ps1
  -> scripts/asu_june_bot_extract_text_v2.py
  -> scripts/asu_june_bot_build_chunks_v2.py
  -> future: scripts/asu_june_bot_build_index_v2.py
```

Все новые runtime-данные пишутся в:

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

`09_chat.py` допускается оставить как prototype, но новая реализация должна идти модульно.

## Что уже реализовано

### 1. Search MVP v1

Начат первый технический слой Asu June Bot: search MVP поверх текущего v1 corpus.

Добавлено:

```text
src/asu_june_bot/
  __init__.py
  core/config.py
  retrieval/models.py
  retrieval/metadata.py
  retrieval/source_policy.py
  retrieval/bm25.py
  retrieval/vector.py
  retrieval/hybrid.py
  retrieval/chunks.py
  retrieval/query_expansion.py
scripts/asu_june_bot_search.py
configs/asu_june_bot/retrieval.yaml
configs/asu_june_bot/source_policy.yaml
configs/asu_june_bot/query_expansion.yaml
configs/asu_june_bot/llm.yaml
configs/asu_june_bot/guardrails.yaml
```

Что умеет текущий слой:

- загружать основной `config.yaml` и конфиги Asu June Bot;
- читать текущий `data/chunks.jsonl` MeetingAgent;
- использовать существующий `data/numpy_index` через adapter;
- строить BM25 in-memory без внешних зависимостей;
- объединять vector и BM25 выдачу в `HybridRetriever`;
- расширять запрос через `query_expansion.yaml`;
- вычислять `source_type`, `document_type`, `module`, `stage`, `section`, `sections` эвристически по пути и тексту chunk;
- применять `SourcePolicy`, чтобы по умолчанию отдавать приоритет проектным документам и не тащить `system_export` без явного запроса;
- запускать CLI-поиск через `scripts/asu_june_bot_search.py`.

### 2. Extraction v2

Добавлен самостоятельный extractor v2:

```text
scripts/asu_june_bot_extract_text_v2.py
src/asu_june_bot/ingestion/
```

Extractor v2 заново сканирует `project_root` из `config.yaml` и не читает старую папку `data/extracted_text`.

Что делает extractor v2:

- заново сканирует исходные файлы проекта;
- поддерживает DOCX, XLSX/XLSB, PDF, PPTX, HTML и текстовые форматы;
- для DOCX читает paragraph/table в исходном порядке документа;
- для DOCX таблиц создает blocks `table` и `table_row`;
- для XLSX/XLSB создает blocks `sheet` и `table_row`;
- для PDF создает page blocks;
- для PPTX создает slide/shape_text blocks;
- пишет структурный результат в `data/asu_june_bot/extracted_v2/`.

Выход extractor v2:

```text
data/asu_june_bot/extracted_v2/documents.jsonl
data/asu_june_bot/extracted_v2/blocks.jsonl
data/asu_june_bot/extracted_v2/extraction_v2_report.json
data/asu_june_bot/extracted_v2/extraction_v2_report.md
```

### 3. Chunking v2

Зафиксирована стратегия структурного chunking v2:

```text
docs/subprojects/asu-june-bot/chunking_strategy.md
```

Добавлен сборщик v2:

```text
scripts/asu_june_bot_build_chunks_v2.py
run_asu_june_bot_chunks_v2.ps1
run_asu_june_bot_rebuild_v2.ps1
```

Chunking v2 читает только:

```text
data/asu_june_bot/extracted_v2/blocks.jsonl
```

Что делает v2-сборщик:

- строит parent/child chunks из blocks v2;
- превращает строки таблиц в child chunks;
- пытается заполнить `requirement_id`, `sections`, `document_type`, `source_type`, `integration`, `protocol`;
- пишет результат в `data/asu_june_bot/chunks_v2.jsonl`;
- пишет отчеты `chunking_v2_report.json` и `chunking_v2_report.md`;
- не трогает `data/chunks.jsonl`, `data/embeddings_cache.jsonl`, `data/numpy_index` и `run_full_rag.ps1`.

Проверочные команды:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_extract_text_v2.py --dry-run --limit 5
.\.venv\Scripts\python.exe scripts\asu_june_bot_extract_text_v2.py --path-contains "ФТТ"
.\.venv\Scripts\python.exe scripts\asu_june_bot_build_chunks_v2.py --dry-run --limit 5
.\run_asu_june_bot_rebuild_v2.ps1
```

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
- маппинги НСИ / СоИ / MDR.

## Ближайшая цель

Проверить новый independent v2 pipeline локально.

Ожидаемый следующий шаг:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_extract_text_v2.py --dry-run --limit 5
.\.venv\Scripts\python.exe scripts\asu_june_bot_extract_text_v2.py --path-contains "ФТТ"
.\.venv\Scripts\python.exe scripts\asu_june_bot_build_chunks_v2.py --dry-run --limit 5
.\run_asu_june_bot_rebuild_v2.ps1
```

После проверки:

- исправить import/runtime ошибки;
- оценить `blocks.jsonl` по DOCX и XLSX;
- оценить `chunks_v2.jsonl` по ФТТ и Паспорт ИС;
- сравнить v1 и v2 на baseline;
- только потом проектировать `numpy_index_v2` и подключение v2 к `/search`.
