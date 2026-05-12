# TODO Asu June Bot

Обновлено: 2026-05-12.

## Сейчас

- Утвердить рабочее название `Asu June Bot` или заменить его до расширения кодовой базы.
- Не развивать дальше `scripts/09_chat.py` как основной продуктовый контур.
- Использовать `scripts/09_chat.py` только как prototype и источник выводов.
- Использовать текущий corpus MeetingAgent и `data/numpy_index` как исходную базу для search MVP.
- Проверить локально search MVP: `scripts/asu_june_bot_search.py`.
- Проверить локально chunking v2: `scripts/asu_june_bot_build_chunks_v2.py`.
- Не менять старый `run_full_rag.ps1`, `data/chunks.jsonl`, `data/embeddings_cache.jsonl` и `data/numpy_index` при проверке v2.
- После локальной проверки исправить runtime/import ошибки, если они появятся.
- Оценить качество выдачи по 3 запросам: интеграции, точный пункт ФТТ, Паспорт ИС.
- Оценить качество `chunks_v2.jsonl` по ФТТ и Паспорт ИС до подключения v2 к поиску.

## Сделано В Этом Срезе

### Search MVP

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

### Chunking v2

Создано:

```text
docs/subprojects/asu-june-bot/chunking_strategy.md
scripts/asu_june_bot_build_chunks_v2.py
run_asu_june_bot_chunks_v2.ps1
```

Реализовано:

- безопасная сборка chunks v2 в `data/asu_june_bot/chunks_v2.jsonl`;
- parent/child chunks;
- child chunks по строкам таблиц;
- metadata v2: `chunker_version`, `chunk_level`, `parent_chunk_id`, `requirement_id`, `sections`, `table_id`, `row_id`, `integration`, `protocol`;
- отчеты `chunking_v2_report.json` и `chunking_v2_report.md`;
- dry-run режим без записи файлов;
- отдельный wrapper `run_asu_june_bot_chunks_v2.ps1` со своими логами.

## Команды Локальной Проверки

### Chunking v2

Dry-run без записи файлов:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_build_chunks_v2.py --dry-run --limit 5
```

Сборка только по ФТТ:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_build_chunks_v2.py --path-contains "ФТТ"
```

Полная сборка v2:

```powershell
.\run_asu_june_bot_chunks_v2.ps1
```

Проверка результата:

```powershell
Get-Content .\data\asu_june_bot\chunking_v2_report.json
(Get-Content .\data\asu_june_bot\chunks_v2.jsonl).Count
Select-String -Path .\data\asu_june_bot\chunks_v2.jsonl -Pattern '"requirement_id": "4.2.5"'
```

### Search MVP

Hybrid search:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_search.py "Какие интеграции заявлены в проекте?" --top-k 10 --json
```

BM25 exact search:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_search.py "ФТТ 4.2.5 НОВАДОК ЭЦП" --mode bm25 --top-k 10 --json
```

Document overview search:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_search.py "Что входит в Паспорт ИС?" --top-k 10 --json
```

Проверка source policy с system_export:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_search.py "пользователи админка роли" --include-source-type system_export --top-k 10 --json
```

## Следующие Задачи Разработки

### 1. Проверить Chunking v2 Локально

- Запустить dry-run `--limit 5`.
- Запустить сборку только по ФТТ.
- Проверить, что `data/chunks.jsonl` не меняется.
- Проверить, что `data/asu_june_bot/chunks_v2.jsonl` создается.
- Проверить наличие `parent` и `child` chunks.
- Проверить, что таблицы дают child chunks с `table_id` и `row_id`.
- Проверить, что ФТТ-пункты получают `requirement_id`, где это возможно.

### 2. Сравнить v1 и v2

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
- v2: просмотр `chunks_v2.jsonl` и будущий отдельный search adapter.

### 3. Исправить По Результату Smoke

- Исправить runtime/import ошибки.
- Уточнить source type inference.
- Уточнить document_type inference.
- Проверить, не режет ли `SourcePolicy` нужные источники.
- Проверить, не вытесняет ли BM25 слишком много vector-результатов.
- Проверить, не генерирует ли chunking v2 слишком много мелких бесполезных chunks.

### 4. Подготовить Search По Chunks v2

После локального smoke:

- добавить CLI-флаг или отдельный скрипт для поиска по `chunks_v2.jsonl`;
- решить, нужен ли отдельный embeddings cache v2;
- подготовить `data/asu_june_bot/numpy_index_v2/`, но не подключать его к основному search без сравнения.

### 5. Подготовить API Search

После CLI-smoke:

```text
src/asu_june_bot/api/app.py
src/asu_june_bot/api/routes_search.py
```

Endpoint:

```text
POST /search
GET /health
```

### 6. Подготовить Chat MVP Только После Search

Реализовать:

- `ProjectGuard`.
- `ContextBuilder`.
- `PromptBuilder`.
- `LLMClient`.
- `AnswerValidator`.
- `ResponseFormatter`.
- CLI `scripts/asu_june_bot_chat.py`.

### 7. Evaluation

Реализовать:

- `eval_questions.yaml`;
- `scripts/asu_june_bot_eval.py`;
- отчет Markdown;
- отчет JSON.

## Вопросы для решения

1. Оставляем ли название `Asu June Bot`?
2. Где физически хранить raw project docs для Asu June Bot: использовать текущий `project_root` MeetingAgent или отдельную папку?
3. Нужно ли сразу добавлять Qdrant local или стартуем с текущего numpy index?
4. Нужен ли отдельный BM25 storage или достаточно строить BM25 in-memory при запуске?
5. Как формировать ссылки на Яндекс.Диск: вручную через `source_links.json` или через будущий connector?
6. Какие документы первого приоритета должны быть в baseline?
7. Нужен ли режим `strict` и `analyst` отдельно?
8. Нужен ли отдельный embeddings cache v2 или можно переиспользовать старый cache только для chunks, где совпал `chunk_id`?

## Рекомендуемые решения по вопросам

1. Название можно оставить временно, но в коде использовать нейтральный пакет `asu_june_bot`.
2. На MVP использовать текущий corpus MeetingAgent.
3. Стартовать с numpy index, Qdrant добавить после стабилизации API.
4. BM25 строить in-memory по `chunks.jsonl` на старте.
5. Ссылки на Яндекс.Диск сначала через ручной `data/source_links.json`.
6. В baseline включить ФТТ, ЦТА, ПР СМР, СоИ AD, СоИ Справочники, Паспорт ИС, ПМИ.
7. Режимы нужны:
   - `strict` — только подтвержденные факты;
   - `analyst` — допускает выводы, но с явным отделением от фактов.
8. Для v2 лучше сделать отдельный cache `data/asu_june_bot/embeddings_cache_v2.jsonl`, чтобы не смешивать chunk-id разных стратегий.

## Definition of Done для Chunking v2

Chunking v2 считается готовым для первого сравнения, если:

- `scripts/asu_june_bot_build_chunks_v2.py --dry-run --limit 5` работает без ошибок.
- `scripts/asu_june_bot_build_chunks_v2.py --path-contains "ФТТ"` создает `chunks_v2.jsonl`.
- Старые `data/chunks.jsonl` и `data/numpy_index` не изменяются.
- У всех v2 chunks есть `chunker_version = v2`.
- Есть `parent` и `child` chunks.
- Табличные child chunks имеют `table_id` и `row_id`.
- ФТТ-пункты по возможности имеют `requirement_id`.
- Создаются `chunking_v2_report.json` и `chunking_v2_report.md`.

## Definition of Done для Search MVP

Search MVP считается готовым, если:

- CLI `scripts/asu_june_bot_search.py` запускается без ошибок.
- `--mode bm25` работает без Ollama.
- `--mode vector` работает через текущий numpy index и Ollama embeddings.
- `--mode hybrid` объединяет результаты vector и BM25.
- В результатах есть `source_type`, `document_type`, `module`, `stage`, `section`, `chunk_index`, `chunk_id`.
- По запросу про интеграции в top-10 есть ЦТА / СоИ / ФТТ источники.
- По точному запросу ФТТ пункт поднимается через BM25.
- `system_export` не попадает в top по умолчанию, если вопрос не про админку/экспорт.

## Definition of Done для MVP

MVP считается готовым, если:

- `/search` работает по текущему corpus;
- `/chat` отвечает на проектные вопросы с citations;
- внепроектные вопросы получают отказ;
- нет ответов без источников;
- есть baseline-отчет;
- архитектура модульная, без раздувания одного скрипта;
- локальная модель может быть заменена через конфиг;
- есть понятный путь миграции на GPU.

## Не делать

- Не добавлять новые if/regex прямо в старый `09_chat.py`.
- Не менять старый `run_full_rag.ps1` под v2.
- Не перезаписывать `data/chunks.jsonl` при сборке v2.
- Не считать embeddings v2 в том же скрипте `asu_june_bot_build_chunks_v2.py`.
- Не переносить Dify/RAGFlow в основной runtime.
- Не начинать UI до API.
- Не делать fine-tuning.
- Не делать agentic tool-use до стабилизации project-only RAG.
- Не смешивать протоколы встреч MeetingAgent и чат-агента в одном pipeline.
