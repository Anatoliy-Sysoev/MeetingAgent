# Контекст проекта

Обновлено: 2026-05-16.

## Текущее состояние

MeetingAgent — приватный GitHub-backed пет-проект и локальный продуктовый репозиторий.

Репозиторий:

```text
Локальный путь: %USERPROFILE%\Desktop\AI\MeetingAgent
Remote: https://github.com/Anatoliy-Sysoev/MeetingAgent
Видимость: private
Рабочая ветка подпроекта: docs/asu-june-bot-subproject
```

Продуктовое направление: local-first агент памяти проекта.

Основные сценарии MeetingAgent:

```text
RAG по проектной документации
транскрибация встреч
генерация memo и протоколов
project-only чат-бот по источникам
классификация по этапу/документу/задаче
генерация черновиков документов на основе цитируемых источников
```

## Подпроекты

### Project Knowledge Bot

`Project Knowledge Bot` — отдельный подпроект для локального AI-агента по проектной документации информационной системы.

Историческое рабочее имя в коде и путях:

```text
asu_june_bot
```

Назначение: отвечать только по загруженной проектной документации и артефактам проекта, возвращать sources/citations, отказывать на внепроектные и смешанные запросы, логировать запуски и поддерживать baseline-оценку качества.

Документация подпроекта находится в:

```text
docs/subprojects/asu-june-bot/
```

Ключевые документы:

```text
README.md                         обзор подпроекта / будущий root README отдельного repo
context.md                        текущий контекст
architecture.md                   техническая архитектура
mvp.md                            ФТТ/MVP scope и статусы
roadmap.md                        план-график
decisions.md                      ADR
todo.md                           текущие задачи
RUNBOOK_V2.md                     запуск, проверка, troubleshooting
eval_questions.md                 проверочные вопросы
ideas.md                          research backlog
product/                          продуктовый пакет
smoke_report_*.md                 отчеты smoke/regression
```

## Статус Project Knowledge Bot

Текущий статус:

```text
API Search MVP: закрыт
CLI Chat MVP: закрыт с ограничениями
API Chat MVP / POST /chat: закрыт с ограничениями
QH-1 Observability + Eval Baseline: реализован, ожидает локальный baseline-прогон
```

Реализовано:

```text
Extraction/Chunking v2.1
Index/Search v2
Search Quality v2.2
ProjectGuard v2
SearchService
FastAPI GET /health
FastAPI POST /search
ChatService
CLI chat
FastAPI POST /chat
ChatRunsLogger
Eval baseline skeleton
```

Корпус v2.1:

```text
documents = 213
blocks = 31076
chunks_v2 = 31302
indexed_chunks = 31285
skipped_code_chunks = 17
embedding_model = bge-m3
embedding_dim = 1024
```

Health v2:

```text
status = ok
vector_ready = true
bm25_ready = true
ollama_available = true
embedding_model_installed = true
```

ProjectGuard v2:

```text
false_allow = 0
```

Рекомендуемая chat-модель MVP:

```text
qwen2.5:7b-instruct
```

Не использовать как default:

```text
qwen3:4b
qwen3:8b
```

Причина:

```text
qwen3:4b -> llm_empty_response / finish_reason=length
qwen3:8b -> timeout/обрыв на локальном CPU runtime
```

## Runtime pipeline Project Knowledge Bot

```text
User / CLI / API client
  -> FastAPI / CLI
  -> SearchService
      -> QueryIntent
      -> ProjectGuard v2
      -> BM25 / Vector / Hybrid retrieval
      -> PostReranker
      -> ContextBuilder
  -> ChatService
      -> PromptBuilder
      -> LLMClient
      -> AnswerValidator
      -> ResponseFormatter
      -> ChatRunsLogger
  -> Response
```

Ключевое правило:

```text
/search возвращает evidence/context
/chat возвращает осмысленный answer with citations
```

`/search` не должен писать осмысленный ответ. Это диагностический endpoint retrieval/context.

## Runtime-данные

Старый RAG MeetingAgent остается v1/baseline и не должен смешиваться с bot v2.1:

```text
data/chunks.jsonl
data/embeddings_cache.jsonl
data/numpy_index/
```

Новый runtime bot v2.1:

```text
data/asu_june_bot/chunks_v2.jsonl
data/asu_june_bot/embeddings_cache_v2.jsonl
data/asu_june_bot/numpy_index_v2/
data/asu_june_bot/chat_runs.jsonl
```

Runtime-данные не коммитить.

## Product documentation

В `docs/subprojects/asu-june-bot/product/` хранится продуктовый пакет:

```text
README.md
01_problem_and_opportunity.md
02_product_vision_and_strategy.md
03_personas_and_jobs.md
04_value_proposition_and_goals.md
05_customer_discovery_and_interview_guide.md
06_babok_business_requirements.md
07_product_architecture_and_relationships.md
08_roadmap_and_release_stages.md
```

Пакет описывает продуктовую сторону: проблему, vision, пользователей, ценность, discovery, BABOK-требования, продуктовую архитектуру и релизы.

Технические инструкции остаются в `RUNBOOK_V2.md`, `architecture.md`, `mvp.md`, `todo.md`.

## Ограничение Chat MVP

Текущий `AnswerValidator` выполняет structural validation:

```text
пустой ответ
наличие sources
наличие ссылок [Sx]
unknown citations
external knowledge markers
answer length
citation density / coverage
```

Не выполняет semantic/factual validation:

```text
поддерживается ли каждое утверждение конкретным source text
не сделала ли модель спорный вывод из короткого UML/heading/caption chunk
нет ли semantic hallucination при формально корректных [Sx]
```

Это quality debt. Следующие этапы качества:

```text
QH-1 baseline eval
QH-2 source quality filter
QH-3 parent expansion при необходимости
```

## Исключения из основного корпуса

В основной project-only corpus не входят технические выгрузки:

```text
**/Система/**
**/asu_docs_export/**
**/asu_admin_export/**
**/docs_html/**
**/docs_text/**
**/pages_html/**
**/pages_text/**
**/site_review_runs/**
**/playwright/**
**/exports/**
**/screenshots/**
**/*.har
```

Если такие данные понадобятся, нужен отдельный `system_export_corpus`.

## Важные решения

```text
scripts/09_chat.py остается legacy/prototype
целевой runtime находится в src/asu_june_bot/ и scripts/asu_june_bot_*.py
qwen2.5:7b-instruct — default chat model MVP
LLM вызывается только после allow + sources/context
refused/clarify не вызывают retrieval/LLM
UI не делать до baseline eval и quality hardening
```

## Ближайшие действия

```text
1. Локально прогнать QH-1 regression tests.
2. Локально прогнать baseline eval.
3. Проанализировать failures.
4. Реализовать QH-2 Source Quality Filter.
5. Сравнить baseline vs with_source_filter.
6. Реализовать QH-3 Parent Expansion только при необходимости.
7. Подготовить выделение Project Knowledge Bot в отдельный репозиторий.
```
