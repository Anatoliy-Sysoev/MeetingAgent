# TODO Asu June Bot

Обновлено: 2026-05-12.

## Сейчас

- Утвердить рабочее название `Asu June Bot` или заменить его до расширения кодовой базы.
- Не развивать дальше `scripts/09_chat.py` как основной продуктовый контур.
- Использовать `scripts/09_chat.py` только как prototype и источник выводов.
- Считать старый RAG MeetingAgent только v1/baseline.
- Новый Asu June Bot v2 строить независимо: `extract_text_v2 -> chunks_v2 -> index_v2`.
- Не опираться на старый `scripts/02_extract_text.py` для v2.
- Не менять старый `run_full_rag.ps1`, `data/chunks.jsonl`, `data/embeddings_cache.jsonl` и `data/numpy_index` при проверке v2.
- Проверить локально extractor v2: `scripts/asu_june_bot_extract_text_v2.py`.
- Проверить локально chunking v2: `scripts/asu_june_bot_build_chunks_v2.py`.
- После локальной проверки исправить runtime/import ошибки, если они появятся.
- Оценить качество `blocks.jsonl` по DOCX/XLSX: порядок paragraph/table, table_row, headers, cells.
- Оценить качество `chunks_v2.jsonl` по ФТТ и Паспорт ИС до подключения v2 к поиску.

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
- эвристическое enrichment metadata: `source_type`, `document_type`, `module`, `stage`, `section`, `sections`.
- CLI `scripts/asu_june_bot_search.py`.

### Extraction v2

Создано:

```text
src/asu_june_bot/ingestion/__init__.py
src/asu_june_bot/ingestion/models.py
src/asu_june_bot/ingestion/utils.py
scripts/asu_june_bot_extract_text_v2.py
run_asu_june_bot_rebuild_v2.ps1
```

Реализовано:

- самостоятельное сканирование `project_root` из `config.yaml`;
- DOCX extraction в исходном порядке paragraph/table;
- DOCX blocks: `heading`, `paragraph`, `table`, `table_row`;
- XLSX/XLSB blocks: `sheet`, `table_row`;
- PDF blocks: `page`;
- PPTX blocks: `slide`, `shape_text`;
- HTML/text blocks;
- `documents.jsonl`, `blocks.jsonl`, `extraction_v2_report.json`, `extraction_v2_report.md` в `data/asu_june_bot/extracted_v2/`.

### Chunking v2

Создано:

```text
docs/subprojects/asu-june-bot/chunking_strategy.md
scripts/asu_june_bot_build_chunks_v2.py
run_asu_june_bot_chunks_v2.ps1
run_asu_june_bot_rebuild_v2.ps1
```

Реализовано:

- сборка chunks v2 из `data/asu_june_bot/extracted_v2/blocks.jsonl`;
- parent/child chunks;
- child chunks по строкам таблиц;
- metadata v2: `chunker_version`, `chunk_level`, `parent_chunk_id`, `block_id`, `block_type`, `requirement_id`, `sections`, `table_id`, `row_id`, `headers`, `cells`, `integration`, `protocol`;
- отчеты `chunking_v2_report.json` и `chunking_v2_report.md`;
- dry-run режим без записи файлов;
- отдельные wrappers со своими логами.

## Команды Локальной Проверки

### Extraction v2

Dry-run без записи файлов:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_extract_text_v2.py --dry-run --limit 5
```

Extraction только по ФТТ:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_extract_text_v2.py --path-contains "ФТТ"
```

Проверка результата extraction:

```powershell
Get-Content .\data\asu_june_bot\extracted_v2\extraction_v2_report.json
(Get-Content .\data\asu_june_bot\extracted_v2\blocks.jsonl).Count
Select-String -Path .\data\asu_june_bot\extracted_v2\blocks.jsonl -Pattern '"block_type": "table_row"' | Select-Object -First 10
```

### Chunking v2

Dry-run после extraction:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_build_chunks_v2.py --dry-run --limit 5
```

Сборка chunks только по ФТТ из blocks v2:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_build_chunks_v2.py --path-contains "ФТТ"
```

Полная v2-пересборка extraction + chunks:

```powershell
.\run_asu_june_bot_rebuild_v2.ps1
```

Проверка результата chunking:

```powershell
Get-Content .\data\asu_june_bot\chunking_v2_report.json
(Get-Content .\data\asu_june_bot\chunks_v2.jsonl).Count
Select-String -Path .\data\asu_june_bot\chunks_v2.jsonl -Pattern '"requirement_id": "4.2.5"'
```

### Search MVP v1

Hybrid search:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_search.py "Какие интеграции заявлены в проекте?" --top-k 10 --json
```

BM25 exact search:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_search.py "ФТТ 4.2.5 НОВАДОК ЭЦП" --mode bm25 --top-k 10 --json
```

## Следующие Задачи Разработки

### 1. Проверить Extraction v2 Локально

- Запустить dry-run `--limit 5`.
- Запустить extraction только по ФТТ.
- Проверить, что `data/asu_june_bot/extracted_v2/blocks.jsonl` создается.
- Проверить, что DOCX сохраняет исходный порядок `paragraph/table`.
- Проверить, что DOCX-таблицы дают `table` и `table_row` blocks.
- Проверить, что XLSX дает `sheet` и `table_row` blocks.
- Проверить наличие `headers` и `cells` у `table_row`.

### 2. Проверить Chunking v2 Локально

- Запустить dry-run `--limit 5` после extraction.
- Запустить сборку chunks только по ФТТ.
- Проверить, что `data/chunks.jsonl` не меняется.
- Проверить, что `data/asu_june_bot/chunks_v2.jsonl` создается.
- Проверить наличие `parent` и `child` chunks.
- Проверить, что табличные child chunks имеют `table_id`, `row_id`, `headers`, `cells`.
- Проверить, что ФТТ-пункты получают `requirement_id`, где это возможно.

### 3. Сравнить v1 и v2

Минимальный baseline:

```text
ФТТ 4.2.5 НОВАДОК ЭЦП
Какие интеграции заявлены в проекте?
Что входит в Паспорт ИС?
Как работает интеграция с AD?
Какие справочники передаются через MDR?
```

Пока сравнение ручное:

- v1: `scripts/asu_june_bot_search.py` по текущему `data/chunks.jsonl`.
- v2: просмотр `blocks.jsonl` и `chunks_v2.jsonl`.

### 4. Исправить По Результату Smoke

- Исправить runtime/import ошибки.
- Уточнить source type inference.
- Уточнить document_type inference.
- Проверить, не генерирует ли extraction v2 слишком много шумных blocks.
- Проверить, не генерирует ли chunking v2 слишком много мелких бесполезных chunks.
- Улучшить обнаружение заголовков/таблиц в DOCX по результату реального ФТТ/ЦТА/Паспорта ИС.

### 5. Подготовить Search По Chunks v2

После локального smoke:

- добавить CLI-флаг или отдельный скрипт для поиска по `chunks_v2.jsonl`;
- сделать отдельный embeddings cache v2: `data/asu_june_bot/embeddings_cache_v2.jsonl`;
- подготовить `data/asu_june_bot/numpy_index_v2/`, но не подключать его к основному search без сравнения.

### 6. Подготовить API Search

После CLI-smoke v2:

```text
src/asu_june_bot/api/app.py
src/asu_june_bot/api/routes_search.py
```

Endpoint:

```text
POST /search
GET /health
```

### 7. Подготовить Chat MVP Только После Search

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

## Definition of Done для Extraction v2

Extraction v2 считается готовым для первого сравнения, если:

- `scripts/asu_june_bot_extract_text_v2.py --dry-run --limit 5` работает без ошибок.
- `scripts/asu_june_bot_extract_text_v2.py --path-contains "ФТТ"` создает `blocks.jsonl`.
- У DOCX сохраняется исходный порядок paragraph/table.
- DOCX-таблицы дают `table_row` blocks.
- XLSX/XLSB дают `sheet` и `table_row` blocks.
- У `table_row` есть `headers` и `cells`.
- Создаются `extraction_v2_report.json` и `extraction_v2_report.md`.

## Definition of Done для Chunking v2

Chunking v2 считается готовым для первого сравнения, если:

- `scripts/asu_june_bot_build_chunks_v2.py --dry-run --limit 5` работает без ошибок после extraction.
- `scripts/asu_june_bot_build_chunks_v2.py --path-contains "ФТТ"` создает `chunks_v2.jsonl`.
- Старые `data/chunks.jsonl` и `data/numpy_index` не изменяются.
- У всех v2 chunks есть `chunker_version = v2`.
- Есть `parent` и `child` chunks.
- Табличные child chunks имеют `table_id`, `row_id`, `headers`, `cells`.
- ФТТ-пункты по возможности имеют `requirement_id`.
- Создаются `chunking_v2_report.json` и `chunking_v2_report.md`.

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
