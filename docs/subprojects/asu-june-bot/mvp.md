# MVP Asu June Bot

Обновлено: 2026-05-12.

## Цель MVP

Сделать локального AI-агента по проекту ЦП УПКС, который:

- принимает вопрос пользователя;
- проверяет, относится ли вопрос к проекту;
- ищет релевантные источники в проектной базе;
- генерирует ответ только по найденным источникам;
- показывает документы, разделы, пункты и фрагменты;
- отказывает на вопросы вне проекта или без подтверждения.

## Scope MVP

### Входит

1. Локальный запуск.
2. CLI и FastAPI API.
3. `/search` для диагностики retrieval.
4. `/chat` для ответа с источниками.
5. Project guard.
6. Hybrid retrieval: vector + BM25.
7. Source metadata.
8. Простая source policy.
9. LLM через Ollama / OpenAI-compatible adapter.
10. Ответ с citations.
11. Baseline из 30+ вопросов.
12. Локальное логирование.

### Не входит

1. Полноценный UI.
2. RBAC.
3. Многопользовательский режим.
4. Подключение внешних коннекторов: Confluence, SharePoint, Yandex Disk API.
5. Автоматическая синхронизация прав доступа.
6. NeMo Guardrails.
7. Dify/RAGFlow как основной runtime.
8. Полный LLM-as-judge.
9. Промышленная эксплуатация.

## Стартовая модель

```text
qwen3:4b через Ollama
```

Модели для сравнения:

```text
qwen3:8b
qwen2.5:7b-instruct
mistral:7b-instruct
```

Правило:

- если `qwen3:4b` дает слабое качество, но быстро отвечает — использовать для локального MVP;
- если `qwen3:8b` слишком медленная — оставить только для офлайн-сравнения;
- если Qwen3 печатает reasoning — отключать thinking через API-параметры/adapter, а не только промптом.

## MVP Pipeline

```text
Question
  -> Guard
  -> Query Expansion
  -> Hybrid Retrieval
  -> Rerank optional
  -> Context Builder
  -> LLM Answer
  -> Validator
  -> Response
```

## Структура кода MVP

```text
src/asu_june_bot/
  __init__.py
  api/
    app.py
    routes_chat.py
    routes_search.py
    routes_health.py
  agent/
    router.py
    guard.py
    prompt_builder.py
    answerer.py
    validator.py
    formatter.py
  retrieval/
    vector.py
    bm25.py
    hybrid.py
    source_policy.py
    context_builder.py
  ingestion/
    metadata.py
    chunk_schema.py
  llm/
    client.py
    ollama_openai.py
  eval/
    runner.py
scripts/
  asu_june_bot_chat.py
  asu_june_bot_search.py
configs/asu_june_bot/
  llm.yaml
  retrieval.yaml
  guardrails.yaml
  query_expansion.yaml
  source_policy.yaml
```

## API Контракт

### POST /chat

Request:

```json
{
  "question": "Какие интеграции заявлены в проекте?",
  "mode": "strict",
  "top_k": 8,
  "filters": {
    "project": "ЦП УПКС"
  }
}
```

Response answered:

```json
{
  "status": "answered",
  "answer_mode": "llm",
  "answer": "...",
  "citations": [
    {
      "source_id": "SRC-001",
      "document": "ЦТА_ЦП_УПКС_Этап_1_v1.2.2.docx",
      "document_type": "ЦТА",
      "section": "4.1.4",
      "title": "Перечень потоков",
      "quote": "...",
      "score": 0.87,
      "url": null
    }
  ],
  "limitations": [],
  "confidence": 0.84
}
```

Response refused:

```json
{
  "status": "refused",
  "refusal_reason": "out_of_project_scope",
  "answer": "Вопрос не относится к проектной документации ЦП УПКС. Я работаю только с загруженными материалами проекта.",
  "citations": [],
  "confidence": 0.0
}
```

Response partial:

```json
{
  "status": "partial",
  "answer_mode": "extractive_fallback",
  "answer": "...",
  "warning": "LLM не вернула ответ; сформирована выжимка по найденным источникам.",
  "citations": [...],
  "confidence": 0.52
}
```

### POST /search

Request:

```json
{
  "query": "AD LDAPS группы пользователей ЦП УПКС",
  "top_k": 10,
  "filters": {
    "document_type": "СоИ",
    "source_type": "project_doc"
  }
}
```

Response:

```json
{
  "query": "AD LDAPS группы пользователей ЦП УПКС",
  "results": [
    {
      "source_id": "SRC-001",
      "document": "ЦП УПКС_СоИ_AD.DOCX",
      "section": "3.5.5",
      "score": 0.91,
      "text_preview": "..."
    }
  ]
}
```

## Функциональные требования MVP

### AJB-MVP-01. Project-only режим

Бот отвечает только по проектным источникам.

Критерии:

- без источников — отказ;
- ответ содержит citations;
- общие вопросы получают отказ.

### AJB-MVP-02. Поиск по проектной документации

Бот умеет искать по ФТТ, ЦТА, ПР, СоИ, ПМИ, Паспорт ИС.

Критерии:

- `/search` возвращает top-k источников;
- в результатах есть document_type и section;
- exact queries по пунктам не теряются.

### AJB-MVP-03. Ответ с источниками

Каждый ответ содержит:

- документ;
- раздел/пункт, если известен;
- короткий фрагмент;
- score;
- ссылку, если есть mapping.

### AJB-MVP-04. Отказ вне проекта

Вопросы типа:

- какая погода;
- курс доллара;
- рецепты;
- текущая дата;
- личные советы;
- код не по проекту;

должны возвращать отказ до LLM или после неудачного retrieval.

### AJB-MVP-05. Локальная LLM

Бот работает с локальной моделью через Ollama.

Критерии:

- Qwen3 4B запускается локально;
- timeout не ломает API;
- при timeout возможен `partial`, но не ложный `answered`.

### AJB-MVP-06. Eval baseline

Есть контрольный набор вопросов.

Критерии:

- не менее 30 вопросов;
- есть проектные, внепроектные, sensitive и negative cases;
- результаты можно сохранять в JSON/Markdown.

## Метрики MVP

```text
0 ответов без sources
100% отказов на obvious out-of-scope
>= 80% проектных вопросов имеют релевантный источник в top-5
>= 70% проектных вопросов дают полезный answer/partial
0 выводов паролей, токенов, .env, config.yaml
```

## Команды будущего запуска

CLI:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_chat.py "Какие интеграции заявлены в проекте?" --json
```

API:

```powershell
uvicorn src.asu_june_bot.api.app:app --reload --host 127.0.0.1 --port 8000
```

Search:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_search.py "ФТТ 4.2.5 НОВАДОК ЭЦП" --json
```

## Первый демонстрационный сценарий

Вопрос:

```text
Какие интеграции заявлены в проекте?
```

Ожидаемый ответ:

- MDR/КШД/СОИ — если подтверждено источниками;
- AD/LDAPS — если подтверждено источниками;
- Blitz IDP — если подтверждено источниками;
- Exchange/SMTP — если подтверждено источниками;
- Minio S3, PostgreSQL, SIEM/logging — только если вопрос допускает системные взаимодействия и источники подтверждают;
- по каждому пункту источник.

## Второй демонстрационный сценарий

Вопрос:

```text
Сколько пользователей на первом этапе?
```

Ожидаемый ответ:

- целевая система: 2520 пользователей, около 600 одновременно;
- Этап 1: не более 120 одновременно работающих;
- источник: ЦТА, раздел требований к производительности.

## Третий демонстрационный сценарий

Вопрос:

```text
Какая погода сегодня?
```

Ожидаемый ответ:

```text
Вопрос не относится к проектной документации ЦП УПКС. Я работаю только с загруженными материалами проекта.
```
