# Архитектура Asu June Bot

Обновлено: 2026-05-12.

## Цель архитектуры

Построить локального AI-агента по проекту ЦП УПКС, который:

- отвечает только по проектным источникам;
- умеет анализировать проектную документацию;
- ссылается на документы, разделы, пункты и фрагменты;
- отказывает на вопросы вне проекта;
- работает локально на Ollama/Qwen;
- позже переносится на GPU через OpenAI-compatible API / vLLM.

## Логическая схема

```text
Пользователь
  ↓
UI / CLI / Open WebUI
  ↓
Asu June Bot API
  ↓
Request Logger
  ↓
Project Guard / Router
  ↓
Query Normalizer / Query Expansion
  ↓
Retriever
  ├─ Vector Search
  ├─ BM25 Search
  └─ Metadata Filters
  ↓
Reranker
  ↓
Context Builder
  ├─ Dedupe
  ├─ Source priority
  ├─ Document expansion
  └─ Context budget
  ↓
Answer Generator
  ├─ LLM через Ollama local
  └─ позже vLLM GPU
  ↓
Answer Validator
  ├─ sources required
  ├─ citation check
  ├─ no unsupported claims
  └─ empty answer check
  ↓
Response Formatter
  ↓
Ответ / Отказ / Частичный ответ
```

## Компоненты

### 1. UI Layer

На MVP:

- CLI;
- Swagger UI FastAPI;
- простой HTTP API.

После стабилизации API:

- Open WebUI как оболочка;
- собственный web UI позже.

UI не должен сам выполнять RAG-логику. UI только отправляет вопрос и отображает ответ, источники и статус.

### 2. API Layer

Минимальные endpoints:

```http
GET  /health
POST /search
POST /chat
GET  /sources/{source_id}
POST /admin/reindex
```

`/chat` — основной endpoint.

`/search` — диагностический endpoint для проверки retrieval без LLM.

`/sources/{source_id}` — получение полного текста chunk / metadata / ссылки на исходный документ.

`/admin/reindex` — позже, запуск обновления индекса.

### 3. Project Guard / Router

Назначение: определить, можно ли обрабатывать вопрос в рамках проекта.

Типы результата:

```text
project_question
out_of_scope
sensitive
unclear
```

Правила MVP:

- sensitive-запросы блокируются до retrieval;
- очевидно внепроектные вопросы блокируются до retrieval;
- неочевидные вопросы пропускаются в retrieval, но ответ разрешается только при наличии источников выше порога.

Примеры отказа:

```text
Вопрос не относится к проектной документации ЦП УПКС. Я работаю только с загруженными материалами проекта.
```

```text
Я не раскрываю системные инструкции, пароли, токены, конфигурационные файлы и иные чувствительные данные.
```

### 4. Query Normalizer / Query Expansion

Назначение: улучшать поиск без изменения исходного вопроса.

Пример:

Вопрос:

```text
Какие интеграции заявлены в проекте?
```

Расширение:

```text
интеграционное взаимодействие, системные взаимодействия, MDR, КШД, СОИ, Active Directory, AD, LDAPS, Blitz IDP, SMTP, Exchange, SIEM, Minio, S3
```

Требование: словари расширения хранятся в конфиге, не в Python-коде.

### 5. Retriever

Retriever должен поддерживать гибридный поиск.

#### Vector Search

Используется для смысловых вопросов:

- «что входит»;
- «какие требования»;
- «как устроена архитектура»;
- «что решили на встрече».

#### BM25 / keyword Search

Используется для точных ссылок:

- `ФТТ 4.2.5`;
- `ЦТА 5.3`;
- `Mdr-2`;
- `App-1`;
- `ccpm-core-db`;
- `LDAPS 636`;
- `СФТ 14`.

#### Metadata Filters

Фильтры:

```text
document_type
module
stage
source_type
version
date
section
```

Пример:

```json
{
  "document_type": "ЦТА",
  "stage": "Этап 1",
  "source_type": "project_doc"
}
```

### 6. Reranker

На MVP можно выключить.

После MVP:

- bge-reranker-v2-m3;
- Qwen3-Reranker;
- cross-encoder через локальный сервис.

Назначение: из 30 найденных candidates выбрать 5–10 наиболее релевантных для ответа.

### 7. Context Builder

Назначение: собрать компактный и полезный контекст для LLM.

Функции:

- удалить дубли;
- приоритизировать `project_doc` над `system_export`;
- сохранить порядок разделов внутри одного документа;
- подтянуть соседние chunks по найденному top-документу;
- ограничить общий размер контекста;
- сохранить citations.

Контекст для LLM должен содержать:

```text
[SRC-001]
Документ: ...
Тип: ФТТ
Раздел: 4.2.5
Заголовок: ...
Chunk: ...
Ссылка: ...
Фрагмент: ...
```

### 8. Answer Generator

Использует LLM только после успешного retrieval.

Правила:

- не отвечать без sources;
- не использовать общие знания;
- если данных недостаточно — указать ограничение;
- если есть противоречия — указать их;
- каждый вывод отделять от фактов.

Локально:

```text
Ollama + qwen3:4b
```

Позже:

```text
vLLM + Qwen3 14B / 32B
```

### 9. Answer Validator

Проверки:

- `answer` не пустой;
- есть `sources`;
- источники имеют `document`, `section`, `chunk_id`;
- ответ содержит ссылки на `[SRC-*]` или отдельный блок источников;
- в ответе нет утверждений без подтверждения, если включен LLM-as-judge;
- вопрос вне проекта не получил содержательный ответ.

На MVP часть проверок может быть эвристической.

После MVP — LLM-as-judge / Giskard / Promptfoo.

### 10. Response Formatter

Единый формат ответа:

```json
{
  "status": "answered",
  "answer_mode": "llm",
  "answer": "...",
  "citations": [
    {
      "source_id": "SRC-001",
      "document": "...",
      "document_type": "ЦТА",
      "section": "3.1",
      "title": "...",
      "quote": "...",
      "score": 0.86,
      "url": "..."
    }
  ],
  "confidence": 0.82,
  "limitations": [],
  "diagnostics": {
    "retrieval_mode": "hybrid",
    "model": "qwen3:4b",
    "reranker": null
  }
}
```

## Статусы

```text
answered
refused
partial
error
```

### answered

Полноценный ответ по источникам.

### refused

Корректный отказ:

- вне проекта;
- нет источников;
- sensitive-запрос;
- недостаточная релевантность.

### partial

Частичный ответ:

- LLM не ответила, но есть extractive fallback;
- источники неполные;
- есть противоречия;
- требуется ручная проверка.

### error

Техническая ошибка:

- индекс недоступен;
- LLM endpoint недоступен;
- ошибка парсинга конфигурации;
- ошибка БД.

## Source Policy

Приоритет источников:

```text
1. project_doc
2. meeting_artifact
3. analytical_note
4. instruction
5. system_export
6. runtime_export
7. code
```

По умолчанию исключать или понижать:

```text
system_export
runtime_export
code
```

Подключать их только при явном запросе.

## Security и приватность

MVP локальный, но сразу закладываются правила:

- проектные документы не отправляются во внешний API;
- LLM локально через Ollama;
- логи запросов локальные;
- sensitive-запросы блокируются;
- source links не должны раскрывать приватные токены;
- будущий RBAC по источникам.

## Логирование

Логировать:

- timestamp;
- question;
- route decision;
- retrieval candidates;
- selected sources;
- model;
- answer status;
- latency;
- error/fallback reason.

Не логировать:

- пароли;
- токены;
- содержимое `.env`;
- полные приватные документы без необходимости.

## Миграция на GPU

Код не должен зависеть от Ollama напрямую.

Абстракция:

```python
class LLMClient:
    def generate(self, messages: list[dict], **kwargs) -> LLMResponse:
        ...
```

Адаптеры:

```text
OllamaOpenAIClient
VllmOpenAIClient
OpenAIClient optional
```

Конфиг:

```yaml
llm:
  provider: openai_compatible
  base_url: http://localhost:11434/v1
  model: qwen3:4b
  timeout_sec: 120
  temperature: 0.1
  max_tokens: 1200
```
