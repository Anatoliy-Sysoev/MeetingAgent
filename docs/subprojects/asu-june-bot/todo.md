# TODO Asu June Bot

Обновлено: 2026-05-13.

## Сейчас

- Считать старый RAG MeetingAgent только v1/baseline.
- Новый Asu June Bot v2.1 строить независимо: `apply_config_v2_1 -> extract_text_v2 -> chunks_v2 -> audit_sources_v2 -> index_v2`.
- Не опираться на старый `scripts/02_extract_text.py` для v2.1.
- Не менять старый `run_full_rag.ps1`, `data/chunks.jsonl`, `data/embeddings_cache.jsonl` и `data/numpy_index` при проверке v2.1.
- Применить локальный `config.yaml` через `scripts/asu_june_bot_apply_config_v2_1.py`.
- Исключить из основного корпуса `**/Система/**`, `asu_docs_export`, `asu_admin_export`, `site_review_runs`, `playwright`, `exports`, `.har`, временные файлы и медиа/архивы.
- Проверить локально extractor v2.1: `scripts/asu_june_bot_extract_text_v2.py`.
- Проверить локально chunking v2.1: `scripts/asu_june_bot_build_chunks_v2.py`.
- Проверить покрытие через `scripts/asu_june_bot_audit_sources_v2.py`.
- Убедиться, что `documents.jsonl` не содержит `/Система/`, `asu_admin_export`, `asu_docs_export`, `site_review_runs`, `playwright`, `.har`.
- Оценить качество `blocks.jsonl` по DOCX/XLSX: порядок paragraph/table, table_row, headers, cells.
- Оценить качество `chunks_v2.jsonl` по ФТТ, ЦТА, Паспорт ИС и СоИ до подключения v2.1 к поиску.
- После успешной проверки v2.1 готовить `scripts/asu_june_bot_build_index_v2.py`.

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

## Команды Локальной Проверки v2.1

### 1. Применить config v2.1

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_apply_config_v2_1.py --project-root "C:\Users\Сотрудник\Desktop\!Проектные документы АСУ"
```

### 2. Dry-run extraction

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_extract_text_v2.py --dry-run --limit 5
```

### 3. Полная пересборка v2.1

```powershell
Remove-Item .\logs\asu_june_bot_rebuild_v2_*.done.txt -ErrorAction SilentlyContinue
Remove-Item .\logs\asu_june_bot_rebuild_v2_*.failed.txt -ErrorAction SilentlyContinue

.\.venv\Scripts\python.exe scripts\asu_june_bot_extract_text_v2.py --reset
.\.venv\Scripts\python.exe scripts\asu_june_bot_build_chunks_v2.py
.\.venv\Scripts\python.exe scripts\asu_june_bot_audit_sources_v2.py
```

### 4. Проверка исключения шумных источников

```powershell
Select-String -Path .\data\asu_june_bot\extracted_v2\documents.jsonl -Pattern '/Система/'
Select-String -Path .\data\asu_june_bot\extracted_v2\documents.jsonl -Pattern 'asu_admin_export|asu_docs_export|site_review_runs|playwright|\.har'
```

Ожидаемо: строки не найдены.

### 5. Проверка отчетов

```powershell
Get-Content .\data\asu_june_bot\extracted_v2\extraction_v2_report.json
Get-Content .\data\asu_june_bot\chunking_v2_report.json
Get-Content .\data\asu_june_bot\source_audit_v2_report.json
```

## Следующие Задачи Разработки

### 1. Проверить Extraction/Chunking v2.1 Локально

- Запустить `apply_config_v2_1`.
- Запустить dry-run `--limit 5`.
- Запустить full rebuild с `--reset`.
- Проверить, что `data/asu_june_bot/extracted_v2/blocks.jsonl` создается.
- Проверить, что `data/asu_june_bot/chunks_v2.jsonl` создается.
- Проверить, что `data/asu_june_bot/source_audit_v2_report.json` создается.
- Проверить, что DOCX сохраняет исходный порядок `paragraph/table`.
- Проверить, что DOCX-таблицы дают `table` и `table_row` blocks.
- Проверить, что XLSX дает `sheet` и `table_row` blocks.
- Проверить наличие `headers` и `cells` у `table_row`.
- Проверить, что `Система` исключена из основного корпуса.

### 2. Сравнить v1 и v2.1

Минимальный baseline:

```text
ФТТ 4.2.5 НОВАДОК ЭЦП
Какие интеграции заявлены в проекте?
Что входит в Паспорт ИС?
Как работает интеграция с AD?
Какие справочники передаются через MDR?
Какие сценарии ПМИ покрывают ФТТ 4.1?
```

Пока сравнение ручное:

- v1: `scripts/asu_june_bot_search.py` по текущему `data/chunks.jsonl`.
- v2.1: просмотр `blocks.jsonl`, `chunks_v2.jsonl`, `chunking_v2_report.json`.

### 3. Подготовить Search По Chunks v2.1

После локального smoke:

- добавить CLI-флаг или отдельный скрипт для поиска по `chunks_v2.jsonl`;
- сделать отдельный embeddings cache v2: `data/asu_june_bot/embeddings_cache_v2.jsonl`;
- подготовить `data/asu_june_bot/numpy_index_v2/`, но не подключать его к основному search без сравнения.

### 4. Подготовить API Search

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

### 5. Подготовить Chat MVP Только После Search

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
7. Какой формат embeddings cache v2 утвердить?
8. Нужно ли выделять `Система` в отдельный `system_export_corpus` позже?

## Рекомендуемые решения по вопросам

1. Название можно оставить временно, но в коде использовать нейтральный пакет `asu_june_bot`.
2. Стартовать с numpy index v2, Qdrant добавить после стабилизации API.
3. BM25 строить in-memory по `chunks_v2.jsonl` на старте.
4. Ссылки на Яндекс.Диск сначала через ручной `data/asu_june_bot/source_links.json`.
5. В baseline включить ФТТ, ЦТА, ПР СМР, СоИ AD, СоИ Справочники, Паспорт ИС, ПМИ.
6. Режимы нужны:
   - `strict` — только подтвержденные факты;
   - `analyst` — допускает выводы, но с явным отделением от фактов.
7. Для v2 лучше сделать отдельный cache `data/asu_june_bot/embeddings_cache_v2.jsonl`, чтобы не смешивать chunk-id разных стратегий.
8. `Система` не включать в основной корпус; при необходимости сделать отдельный корпус и отдельный режим поиска.

## Definition of Done для v2.1

v2.1 считается готовым для перехода к index v2, если:

- `scripts/asu_june_bot_apply_config_v2_1.py` успешно обновляет локальный `config.yaml`.
- `scripts/asu_june_bot_extract_text_v2.py --dry-run --limit 5` работает без ошибок.
- Full rebuild создает `blocks.jsonl`, `chunks_v2.jsonl`, `source_audit_v2_report.json`.
- Старые `data/chunks.jsonl` и `data/numpy_index` не изменяются.
- У всех v2 chunks есть `chunker_version = v2`.
- Есть `parent` и `child` chunks.
- Табличные child chunks имеют `table_id`, `row_id`, `headers`, `cells`.
- ФТТ-пункты по возможности имеют `requirement_id`.
- `documents.jsonl` не содержит `/Система/`, `asu_admin_export`, `asu_docs_export`, `site_review_runs`, `playwright`, `.har`.
- `unknown` и `system_export` не доминируют в `chunking_v2_report.json`.

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
