# Архитектура Asu June Bot

Обновлено: 2026-05-15.

## Цель архитектуры

Построить локального AI-агента по проекту ЦП УПКС, который:

- отвечает только по проектным источникам;
- умеет анализировать проектную документацию;
- ссылается на документы, разделы, пункты и фрагменты;
- отказывает на вопросы вне проекта;
- блокирует mixed-scope, offensive/security и prompt-injection запросы до retrieval;
- возвращает `clarify` для неоднозначных запросов;
- работает локально на Ollama/Qwen;
- позже переносится на GPU через OpenAI-compatible API / vLLM.

## Текущий статус архитектуры

Реализованы и проверены:

```text
Extraction/Chunking v2.1
Index/Search v2
Search Quality v2.2
ProjectGuard v2
```

ProjectGuard v2 regression suite:

```text
44/44 passed
false_allow = 0
```

Следующий архитектурный этап:

```text
API Search MVP
```

## Текущая логическая схема Search MVP

```text
Пользователь / CLI / API
  ↓
QueryIntent
  ↓
ProjectGuard v2
  ├─ refused -> response без retrieval
  ├─ clarify -> response без retrieval
  └─ allow
       ↓
Hybrid Retrieval
  ├─ BM25 Search
  ├─ Vector Search
  └─ Hybrid merge
       ↓
PostReranker
       ↓
ContextBuilder
  ├─ primary_sources
  ├─ supporting_sources
  └─ excluded_sources
       ↓
Search JSON response
```

## Целевая схема Chat MVP

```text
Пользователь
  ↓
UI / CLI / Open WebUI
  ↓
Asu June Bot API
  ↓
Request Logger
  ↓
QueryIntent
  ↓
ProjectGuard v2
  ├─ refused -> отказ
  ├─ clarify -> уточнение
  └─ allow
       ↓
Hybrid Retrieval
       ↓
PostReranker
       ↓
ContextBuilder
       ↓
PromptBuilder
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

Ближайшие endpoints:

```http
GET  /health
POST /search
```

Позже:

```http
POST /chat
GET  /sources/{source_id}
POST /admin/reindex
```

`/search` — диагностический endpoint для проверки retrieval без LLM.

`/chat` — основной endpoint после стабилизации `/search`.

`/sources/{source_id}` — получение полного текста chunk / metadata / ссылки на исходный документ.

`/admin/reindex` — позже, запуск обновления индекса.

API `/search` должен быть thin HTTP layer над уже проверенным CLI pipeline `search_v2`, без дублирования логики.

### 3. QueryIntent

Назначение: определить тип запроса для retrieval/context:

```text
document_overview
integration_overview
requirement_lookup
general_project_question
out_of_scope_candidate
```

QueryIntent не является единственным guard-решением. Окончательное allow/refuse/clarify принимает ProjectGuard v2.

### 4. ProjectGuard v2

Назначение: определить, можно ли обрабатывать вопрос в рамках проекта до retrieval.

Pipeline:

```text
QuerySegmenter
  -> RuleBasedScopeClassifier
  -> ScopeAggregator
  -> GuardPolicy
  -> ProjectGuard
```

Возможные статусы:

```text
allow
refuse
clarify
```

Правила MVP:

- pure project query -> `allow`;
- pure out-of-project query -> `refuse`;
- mixed-scope query -> `refuse`;
- offensive/security query -> `refuse`;
- prompt-injection/jailbreak query -> `refuse`;
- ambiguous query -> `clarify`.

Критерий качества:

```text
false_allow = 0
```

Диагностика возвращается в JSON:

```text
guard.guard_v2.aggregate.segments[]
```

В этом блоке видно, какая часть запроса признана `in_project`, `out_of_project`, `mixed`, `meta` или `ambiguous`.

### 5. Query Normalizer / Query Expansion

Назначение: улучшать поиск без изменения исходного вопроса.

Пример:

```text
Какие интеграции заявлены в проекте?
```

Расширение:

```text
интеграционное взаимодействие, системные взаимодействия, MDR, КШД, СОИ, Active Directory, AD, LDAPS, Blitz IDP, SMTP, Exchange, SIEM, Minio, S3
```

Требование: словари расширения хранить в конфиге, не в Python-коде.

### 6. Retriever

Retriever поддерживает гибридный поиск.

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

### 7. PostReranker

Назначение: улучшить порядок candidates после BM25/vector/hybrid.

Реализованные правила:

- штрафовать vector-only chunks для overview/exact queries;
- штрафовать software/support/front matter/glossary chunks;
- усиливать Паспорт ИС для `document_overview`;
- усиливать ЦТА/Паспорт/СоИ/ФТТ для вопросов по интеграциям;
- усиливать точные пункты ФТТ для `requirement_lookup`;
- добавлять `rerank_labels` в diagnostics.

### 8. ContextBuilder

Назначение: собрать компактный и полезный context для API/LLM.

Функции:

- отделить `primary_sources` от `supporting_sources`;
- вынести шум в `excluded_sources`;
- не дублировать один chunk между buckets;
- для точного `requirement_lookup` держать в primary только точный пункт;
- для `document_overview` держать в primary обзорный chunk, а не таблицы ПО/поддержки.

Контекст для будущего LLM должен содержать:

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

### 9. Answer Generator

Используется только после успешного retrieval и ContextBuilder.

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

### 10. Answer Validator

Проверки:

- `answer` не пустой;
- есть `sources`;
- источники имеют `document`, `section`, `chunk_id`;
- ответ содержит ссылки на `[SRC-*]` или отдельный блок источников;
- в ответе нет утверждений без подтверждения, если включен LLM-as-judge;
- вопрос вне проекта не получил содержательный ответ.

На MVP часть проверок может быть эвристической.

После MVP — LLM-as-judge / Giskard / Promptfoo / DeepEval.

### 11. Response Formatter

Единый формат будущего `/chat` ответа:

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

### Search/API status

```text
ok
refused
clarify
error
```

### Chat status

```text
answered
refused
partial
error
```

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
- mixed-scope запросы блокируются;
- source links не должны раскрывать приватные токены;
- future RBAC по источникам.

## Логирование

Логировать:

- timestamp;
- question hash;
- route decision;
- guard segments;
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
