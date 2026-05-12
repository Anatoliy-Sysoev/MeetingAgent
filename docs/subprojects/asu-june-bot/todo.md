# TODO Asu June Bot

Обновлено: 2026-05-12.

## Сейчас

- Утвердить рабочее название `Asu June Bot` или заменить его до появления кода.
- Не развивать дальше `scripts/09_chat.py` как основной продуктовый контур.
- Использовать `scripts/09_chat.py` только как prototype и источник выводов.
- Зафиксировать подпроект в документации MeetingAgent.
- Создать модульную структуру `src/asu_june_bot/`.
- Создать конфиги `configs/asu_june_bot/`.
- Описать chunk schema для проектных документов.
- Добавить source type policy.
- Подготовить baseline-вопросы.

## Ближайшие задачи разработки

### 1. Каркас кода

Создать:

```text
src/asu_june_bot/
  __init__.py
  api/
  agent/
  retrieval/
  ingestion/
  llm/
  eval/
configs/asu_june_bot/
```

### 2. Конфигурации

Создать:

```text
configs/asu_june_bot/llm.yaml
configs/asu_june_bot/retrieval.yaml
configs/asu_june_bot/guardrails.yaml
configs/asu_june_bot/query_expansion.yaml
configs/asu_june_bot/source_policy.yaml
```

### 3. Search MVP

Реализовать:

- `VectorSearchAdapter` поверх текущего numpy index MeetingAgent.
- `BM25SearchAdapter` поверх `data/chunks.jsonl`.
- `HybridRetriever`.
- `SourcePolicy`.
- CLI `scripts/asu_june_bot_search.py`.

### 4. Chat MVP

Реализовать:

- `ProjectGuard`.
- `QueryExpander`.
- `ContextBuilder`.
- `PromptBuilder`.
- `LLMClient`.
- `AnswerValidator`.
- `ResponseFormatter`.
- CLI `scripts/asu_june_bot_chat.py`.

### 5. FastAPI MVP

Реализовать endpoints:

```text
GET /health
POST /search
POST /chat
GET /sources/{source_id}
```

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
