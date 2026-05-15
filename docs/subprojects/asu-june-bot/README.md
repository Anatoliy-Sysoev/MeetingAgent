# Asu June Bot

Статус: подпроект / локальный Search MVP готов к API Search.

Обновлено: 2026-05-15.

## Назначение

Asu June Bot — локальный AI-агент по проекту ЦП УПКС, который отвечает только по загруженной проектной документации и артефактам проекта.

Цель подпроекта — выделить развитие project-only чат-бота из общего MeetingAgent в самостоятельный контур, чтобы не смешивать:

- обработку встреч;
- RAG-память проекта;
- генерацию протоколов;
- AI-агента для анализа проектной документации.

Asu June Bot должен стать рабочим ассистентом системного аналитика по проекту ЦП УПКС: отвечать на вопросы по ФТТ, ЦТА, проектным решениям, соглашениям об интеграции, ПМИ, паспорту ИС, руководствам, протоколам встреч и решениям.

## Текущий статус

Готово:

```text
Extraction/Chunking v2.1
Index/Search v2
Search Quality v2.2
ProjectGuard v2
```

Финальный ProjectGuard v2 regression результат:

```json
{
  "total": 44,
  "passed": 44,
  "failed": 0,
  "false_allow": 0,
  "false_refuse": 0,
  "false_clarify": 0
}
```

Следующий этап:

```text
API Search MVP
```

## Рабочее название

Текущее название: `Asu June Bot`.

Название временное. Возможные будущие варианты:

- ASU Project Bot;
- ASU Knowledge Bot;
- ASU Analyst Agent;
- ЦП УПКС Agent;
- Project Knowledge Agent.

До утверждения названия в коде и документации использовать `Asu June Bot`.

## Что бот должен уметь

Минимально:

1. Отвечать только по проектным источникам.
2. Отказывать на вопросы вне проекта.
3. Отказывать на mixed-scope запросы, где есть проектная и внепроектная часть.
4. Возвращать `clarify` для неоднозначных запросов без проектного объекта.
5. Давать ссылки на документы, разделы, пункты и chunks.
6. Показывать ограничения ответа, если данных недостаточно.
7. Иметь общее представление о проекте ЦП УПКС: модули, этапы, архитектура, интеграции, ИБ, ПМИ, паспорт ИС.
8. Анализировать связи между документами: ФТТ ↔ ПР ↔ ЦТА ↔ ПМИ ↔ СоИ ↔ протоколы.
9. Работать локально на CPU / локальной GPU через Ollama.
10. Сохранять путь миграции на GPU-сервер через OpenAI-compatible API / vLLM.

## Что бот не должен делать

- Отвечать на общие вопросы: погода, курс валют, рецепты, новости, бытовые советы.
- Отвечать по общим знаниям LLM, если нет подтверждения в источниках.
- Генерировать неподтвержденные факты о проекте.
- Запускать retrieval для `refused` и `clarify` запросов.
- Раскрывать `.env`, `config.yaml`, токены, пароли, технические секреты.
- Подменять проектную документацию своим предположением.
- Считать аварийную extractive-выжимку полноценным LLM-ответом.

## Базовая архитектура

```text
Пользователь
  -> UI / CLI / Open WebUI
  -> FastAPI Asu June Bot API
  -> QueryIntent
  -> ProjectGuard v2
  -> Hybrid Retrieval: vector + BM25
  -> PostReranker
  -> ContextBuilder
  -> LLM Answerer: Ollama локально, vLLM позже
  -> Answer Validator
  -> Ответ с источниками или отказ
```

## Локальный стек MVP

- Python + FastAPI.
- Ollama.
- Qwen3 4B как стартовая локальная LLM.
- Qwen3 8B / qwen2.5:7b-instruct как модели сравнения.
- BGE-M3 embeddings.
- Numpy index v2 для MVP.
- BM25 для точного поиска по номерам пунктов, ФТТ, кодам потоков, сервисам и аббревиатурам.
- Open WebUI как будущая оболочка, но не как основной RAG-движок.

## Реализованные runtime-компоненты

```text
scripts/asu_june_bot_extract_text_v2.py
scripts/asu_june_bot_build_chunks_v2.py
scripts/asu_june_bot_audit_sources_v2.py
scripts/asu_june_bot_build_index_v2.py
scripts/asu_june_bot_health_v2.py
scripts/asu_june_bot_search_v2.py
scripts/asu_june_bot_guard_v2_eval.py
```

```text
src/asu_june_bot/retrieval/query_intent.py
src/asu_june_bot/retrieval/post_rerank.py
src/asu_june_bot/retrieval/context_builder.py
src/asu_june_bot/guardrails/models.py
src/asu_june_bot/guardrails/segmenter.py
src/asu_june_bot/guardrails/scope_classifier.py
src/asu_june_bot/guardrails/aggregator.py
src/asu_june_bot/guardrails/policy.py
src/asu_june_bot/guardrails/project_guard.py
```

## Принцип ответа

Каждый будущий chat-ответ должен иметь структуру:

```text
Краткий ответ

Обоснование по источникам

Вывод / интерпретация

Ограничения

Источники
```

Если источников нет:

```text
В проектных источниках не найдено подтверждение для ответа на этот вопрос.
Я отвечаю только по загруженной документации проекта ЦП УПКС.
```

## Документы подпроекта

- `context.md` — текущий контекст подпроекта.
- `decisions.md` — архитектурные и продуктовые решения.
- `architecture.md` — целевая архитектура.
- `mvp.md` — состав локального MVP.
- `roadmap.md` — этапы развития.
- `todo.md` — ближайшие задачи.
- `eval_questions.md` — набор проверочных вопросов.
- `ideas.md` — research backlog.
- `RUNBOOK_V2.md` — команды запуска, мониторинга и восстановления pipeline v2.
- `product/` — отдельный комплект продуктовой документации для размещения в Git.
- `smoke_report_project_guard_v2.md` — финальный smoke-отчёт ProjectGuard v2.

## Связь с MeetingAgent

MeetingAgent остается базовым продуктом для:

- сбора проектных документов;
- построения RAG-индекса;
- обработки встреч;
- транскрибации;
- генерации memo/protocol/decisions/tasks.

Asu June Bot использует эти данные как проектную память, но имеет собственный контур:

- правила project-only ответа;
- ProjectGuard v2;
- маршрутизацию вопросов;
- source policy;
- ответ с citations;
- eval-наборы;
- будущий API `/search`, `/chat` и UI.
