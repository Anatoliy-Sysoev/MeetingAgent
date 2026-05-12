# TODO Asu June Bot

Обновлено: 2026-05-12.

## Сейчас

- Утвердить рабочее название `Asu June Bot` или заменить его до расширения кодовой базы.
- Не развивать дальше `scripts/09_chat.py` как основной продуктовый контур.
- Использовать `scripts/09_chat.py` только как prototype и источник выводов.
- Использовать текущий corpus MeetingAgent и `data/numpy_index` как исходную базу для search MVP.
- Проверить локально первый search MVP: `scripts/asu_june_bot_search.py`.
- После локальной проверки исправить runtime/import ошибки, если они появятся.
- Оценить качество выдачи по 3 запросам: интеграции, точный пункт ФТТ, Паспорт ИС.

## Сделано В Этом Срезе

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
- `SourcePolicy`.
- эвристическое enrichment metadata: `source_type`, `document_type`, `module`, `stage`, `section`.
- CLI `scripts/asu_june_bot_search.py`.

## Команды Локальной Проверки

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

### 1. Проверить Search MVP Локально

- Запустить 3 базовые команды.
- Проверить, что импорт `rag_numpy_backend` работает через `scripts/`.
- Проверить, что `config.yaml`, `data/chunks.jsonl` и `data/numpy_index` находятся.
- Проверить, что Ollama доступна для vector search.
- Если нужен быстрый smoke без Ollama, использовать `--mode bm25`.

### 2. Исправить По Результату Smoke

- Исправить runtime/import ошибки.
- Уточнить source type inference.
- Уточнить document_type inference.
- Проверить, не режет ли `SourcePolicy` нужные источники.
- Проверить, не вытесняет ли BM25 слишком много vector-результатов.

### 3. Реализовать QueryExpander Runtime

- Прочитать `configs/asu_june_bot/query_expansion.yaml`.
- Расширять query для retrieval.
- Исходный вопрос не менять для ответа.
- Добавить diagnostics: какие expansion terms применены.

### 4. Подготовить API Search

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

### 5. Подготовить Chat MVP Только После Search

Реализовать:

- `ProjectGuard`.
- `ContextBuilder`.
- `PromptBuilder`.
- `LLMClient`.
- `AnswerValidator`.
- `ResponseFormatter`.
- CLI `scripts/asu_june_bot_chat.py`.

### 6. Evaluation

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
- Не переносить Dify/RAGFlow в основной runtime.
- Не начинать UI до API.
- Не делать fine-tuning.
- Не делать agentic tool-use до стабилизации project-only RAG.
- Не смешивать протоколы встреч MeetingAgent и чат-агента в одном pipeline.
