# TODO Asu June Bot

Обновлено: 2026-05-14.

## Сейчас

- Считать старый RAG MeetingAgent только v1/baseline.
- Новый Asu June Bot v2.1 строить независимо: `apply_config_v2_1 -> extract_text_v2 -> chunks_v2 -> audit_sources_v2 -> build_index_v2 -> search_v2`.
- Не опираться на старый `scripts/02_extract_text.py` для v2.1.
- Не менять старый `run_full_rag.ps1`, `data/chunks.jsonl`, `data/embeddings_cache.jsonl` и `data/numpy_index` при проверке v2.1.
- `Система`, `asu_docs_export`, `asu_admin_export`, `site_review_runs`, `playwright`, `exports`, `.har`, временные файлы и медиа/архивы исключены из основного корпуса.
- Локальная проверка extraction/chunking v2.1 пройдена: `documents=213`, `blocks=31076`, `chunks=31302`, `system_export` отсутствует в `by_source_type`.
- Полный `embeddings_cache_v2` собран: `cached_after=31285`, `missing_after=0`, `embedding_model=bge-m3`, `max_embedding_chars=3000`.
- `numpy_index_v2` собран: `index_built=true`, `index_count=31285`, `embedding_dim=1024`.
- Из индекса исключены `code` chunks: `chunks_skipped_by_source_type=17`.
- Следующий практический шаг: прогнать `search_v2` в режимах `hybrid`, `vector`, `bm25`, оценить качество retrieval и после этого переходить к API Search.

## Сделано В Этом Срезе

### Search MVP v1

Создано:

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
configs/asu_june_bot/llm.yaml
configs/asu_june_bot/retrieval.yaml
configs/asu_june_bot/guardrails.yaml
configs/asu_june_bot/query_expansion.yaml
configs/asu_june_bot/source_policy.yaml
```

Реализовано:

- `VectorSearchAdapter` поверх текущего numpy index MeetingAgent.
- `BM25SearchAdapter` поверх `data/chunks.jsonl`.
- `HybridRetriever`.
- `QueryExpander`.
- `SourcePolicy`.
- enrichment metadata: `source_type`, `document_type`, `module`, `stage`, `section`, `sections`.
- CLI `scripts/asu_june_bot_search.py`.

### Extraction v2.1

Создано/обновлено:

```text
src/asu_june_bot/ingestion/__init__.py
src/asu_june_bot/ingestion/models.py
src/asu_june_bot/ingestion/utils.py
scripts/asu_june_bot_extract_text_v2.py
scripts/asu_june_bot_apply_config_v2_1.py
run_asu_june_bot_rebuild_v2.ps1
```

Реализовано:

- самостоятельное сканирование `project_root` из `config.yaml`;
- локальное применение фильтров v2.1 к `config.yaml`;
- жесткие исключения шумных источников на уровне ingestion-кода;
- DOCX extraction в исходном порядке paragraph/table;
- DOCX blocks: `heading`, `paragraph`, `table`, `table_row`;
- эвристика определения заголовочной строки в DOCX-таблицах;
- XLSX extraction через `openpyxl`;
- XLSB extraction через `pandas` + `pyxlsb`;
- эвристика определения заголовочной строки в Excel;
- PDF blocks: `page`;
- PPTX blocks: `slide`, `shape_text`;
- text blocks для md/txt/json/yaml/drawio/puml/bpmn/srt;
- `documents.jsonl`, `blocks.jsonl`, `extraction_v2_report.json`, `extraction_v2_report.md` в `data/asu_june_bot/extracted_v2/`.

### Chunking v2.1

Создано/обновлено:

```text
docs/subprojects/asu-june-bot/chunking_strategy.md
scripts/asu_june_bot_build_chunks_v2.py
scripts/asu_june_bot_audit_sources_v2.py
run_asu_june_bot_chunks_v2.ps1
run_asu_june_bot_rebuild_v2.ps1
```

Реализовано:

- сборка chunks v2 из `data/asu_june_bot/extracted_v2/blocks.jsonl`;
- parent/child chunks;
- child chunks по строкам таблиц;
- metadata v2: `chunker_version`, `chunk_level`, `parent_chunk_id`, `block_id`, `block_type`, `requirement_id`, `sections`, `table_id`, `row_id`, `headers`, `cells`, `integration`, `protocol`;
- отчеты `chunking_v2_report.json` и `chunking_v2_report.md`;
- аудит покрытия `source_audit_v2_report.json`;
- детальные причины исключений: `hard_excluded_path`, `hard_excluded_directory`, `hard_excluded_extension`, `office_temp_file`, `extension_not_in_config`;
- dry-run режим без записи файлов;
- отдельные wrappers со своими логами.

### Source Policy v2.1

Обновлено:

```text
configs/asu_june_bot/source_policy.yaml
src/asu_june_bot/retrieval/source_policy.py
src/asu_june_bot/retrieval/metadata.py
```

Реализовано:

- `system_export` не входит в default corpus;
- `system_export` получает низкий вес `0.12`;
- `system_export` подключается только при явном запросе по маркерам;
- усилены веса ФТТ, ЦТА, ПР, СоИ, Паспорт ИС, ПМИ;
- улучшено распознавание `document_type` по имени файла и пути.

### Index/Search v2

Создано:

```text
scripts/asu_june_bot_build_index_v2.py
scripts/asu_june_bot_search_v2.py
monitor_asu_june_bot_index_v2.ps1
register_asu_june_bot_index_v2_watchdog.ps1
```

Реализовано:

- отдельный embeddings cache: `data/asu_june_bot/embeddings_cache_v2.jsonl`;
- отдельный numpy index: `data/asu_june_bot/numpy_index_v2/`;
- resume для embeddings cache по `chunk_id`;
- режим `--embed-only`;
- режим `--index-only`;
- режим `--limit` для smoke-проверки;
- отчет `data/asu_june_bot/index_v2_report.json`;
- отдельный CLI-поиск по v2 corpus: `scripts/asu_june_bot_search_v2.py`;
- режимы поиска `bm25`, `vector`, `hybrid` по `chunks_v2` и `numpy_index_v2`;
- отдельный watchdog для `--embed-only`: если процесс пропал до завершения cache, он перезапускается без удаления накопленных embeddings;
- фильтрация индексируемых source types: `project_doc`, `meeting_artifact`, `analytical_note`, `instruction`.

Локальный результат полного index v2:

```text
chunks_total_before_filter = 31302
chunks_total = 31285
chunks_skipped_by_source_type = 17
cached_after = 31285
missing_after = 0
index_built = true
index_count = 31285
embedding_model = bge-m3
embedding_dim = 1024
```

## Команды Локальной Проверки v2.1

### 1. Проверка отчетов с правильной кодировкой

Windows PowerShell 5.1 требует `-Encoding UTF8`.

```powershell
Get-Content .\data\asu_june_bot\extracted_v2\extraction_v2_report.json -Encoding UTF8
Get-Content .\data\asu_june_bot\chunking_v2_report.json -Encoding UTF8
Get-Content .\data\asu_june_bot\source_audit_v2_report.json -Encoding UTF8
Get-Content .\data\asu_june_bot\index_v2_report.json -Encoding UTF8
Get-Content .\data\asu_june_bot\numpy_index_v2\manifest.json -Encoding UTF8
```

### 2. BM25 smoke

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Что входит в Паспорт ИС?" --mode bm25 --top-k 5
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Какие интеграции заявлены в проекте?" --mode bm25 --top-k 5
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "ФТТ 4.2.5 НОВАДОК ЭЦП" --mode bm25 --top-k 5
```

### 3. Vector smoke

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Что входит в Паспорт ИС?" --mode vector --top-k 8
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Какие интеграции заявлены в проекте?" --mode vector --top-k 8
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "ФТТ 4.2.5 НОВАДОК ЭЦП" --mode vector --top-k 8
```

### 4. Hybrid smoke

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Что входит в Паспорт ИС?" --mode hybrid --top-k 8
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Какие интеграции заявлены в проекте?" --mode hybrid --top-k 8
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "ФТТ 4.2.5 НОВАДОК ЭЦП" --mode hybrid --top-k 8
```

### 5. JSON smoke для анализа качества retrieval

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Какие интеграции заявлены в проекте?" --mode hybrid --top-k 12 --json > .\data\asu_june_bot\smoke_integrations_hybrid.json
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Что входит в Паспорт ИС?" --mode hybrid --top-k 12 --json > .\data\asu_june_bot\smoke_passport_hybrid.json
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "ФТТ 4.2.5 НОВАДОК ЭЦП" --mode hybrid --top-k 12 --json > .\data\asu_june_bot\smoke_ftt_425_hybrid.json
```

## Следующие Задачи Разработки

### 1. Проверить Search v2 Локально

- Запустить BM25 smoke по baseline.
- Запустить vector smoke по baseline.
- Запустить hybrid smoke по baseline.
- Проверить, что топ-8 содержит Паспорт ИС, ФТТ, ЦТА, ПР, СоИ для соответствующих вопросов.
- Сохранить JSON smoke для трех baseline-вопросов.
- По результатам решить, нужен ли reranker перед API Search.

### 2. Подготовить API Search

После CLI-smoke v2.1:

```text
src/asu_june_bot/api/app.py
src/asu_june_bot/api/routes_search.py
```

Endpoint:

```text
POST /search
GET /health
```

### 3. Подготовить Chat MVP Только После Search

Реализовать:

- `ProjectGuard`.
- `ContextBuilder`.
- `PromptBuilder`.
- `LLMClient`.
- `AnswerValidator`.
- `ResponseFormatter`.
- CLI `scripts/asu_june_bot_chat.py`.

## Вопросы для решения

1. Оставляем ли название `Asu June Bot`?
2. Нужно ли сразу добавлять Qdrant local или стартуем с numpy index v2?
3. Нужен ли отдельный BM25 storage или достаточно строить BM25 in-memory при запуске?
4. Как формировать ссылки на Яндекс.Диск: вручную через `source_links.json` или через будущий connector?
5. Какие документы первого приоритета должны быть в baseline?
6. Нужен ли режим `strict` и `analyst` отдельно?
7. Нужно ли выделять `Система` в отдельный `system_export_corpus` позже?
8. Нужен ли reranker до API Search или достаточно текущего hybrid на MVP?

## Рекомендуемые решения по вопросам

1. Название можно оставить временно, но в коде использовать нейтральный пакет `asu_june_bot`.
2. Стартовать с numpy index v2, Qdrant добавить после стабилизации API.
3. BM25 строить in-memory по `chunks_v2.jsonl` на старте.
4. Ссылки на Яндекс.Диск сначала через ручной `data/asu_june_bot/source_links.json`.
5. В baseline включить ФТТ, ЦТА, ПР СМР, СоИ AD, СоИ Справочники, Паспорт ИС, ПМИ.
6. Режимы нужны:
   - `strict` — только подтвержденные факты;
   - `analyst` — допускает выводы, но с явным отделением от фактов.
7. `Система` не включать в основной корпус; при необходимости сделать отдельный корпус и отдельный режим поиска.
8. Reranker вводить только если hybrid smoke показывает смешивание нерелевантных chunks в top-5/top-8.

## Definition of Done для v2.1

v2.1 считается готовым для перехода к API search, если:

- `documents.jsonl` не содержит `/Система/`, `asu_admin_export`, `asu_docs_export`, `site_review_runs`, `playwright`, `.har`.
- `chunking_v2_report.json` показывает отсутствие `system_export` в основном корпусе.
- `chunks_v2.jsonl` содержит `parent` и `child` chunks.
- Табличные child chunks имеют `table_id`, `row_id`, `headers`, `cells`.
- ФТТ-пункты по возможности имеют `requirement_id`.
- `embeddings_cache_v2.jsonl` создан.
- `numpy_index_v2/manifest.json` создан.
- `search_v2 --mode bm25` проходит baseline smoke.
- `search_v2 --mode vector` проходит baseline smoke.
- `search_v2 --mode hybrid` проходит baseline smoke.
- Старые `data/chunks.jsonl`, `data/embeddings_cache.jsonl`, `data/numpy_index` не изменяются.

## Не делать

- Не добавлять новые if/regex прямо в старый `09_chat.py`.
- Не менять старый `run_full_rag.ps1` под v2.
- Не использовать старый `data/extracted_text/_metadata.jsonl` как вход для v2.
- Не перезаписывать `data/chunks.jsonl` при сборке v2.
- Не считать embeddings v2 в том же скрипте `asu_june_bot_build_chunks_v2.py`.
- Не переносить Dify/RAGFlow в основной runtime.
- Не начинать UI до API.
- Не делать fine-tuning.
- Не делать agentic tool-use до стабилизации project-only RAG.
- Не индексировать `Система` в основной project-only corpus.
