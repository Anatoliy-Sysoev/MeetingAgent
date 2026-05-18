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
TOMORROW_START.md                 завтрашний чек-лист запуска
QH_STATUS.md                      статус QH-этапов
FTT_STATUS.md                     оперативный статус FTT бота
context.md                        текущий контекст
architecture.md                   техническая архитектура
mvp.md                            ФТТ/MVP scope и статусы
roadmap.md                        план-график
decisions.md                      ADR
todo.md                           текущие задачи
RUNBOOK_V2.md                     запуск, проверка, troubleshooting
telegram.md                       Telegram adapter
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
Local Web UI / GET / and GET /ui: реализован, ожидает локальный smoke
Telegram adapter: реализован, ожидает локальный smoke
QH-1 Observability + Eval Baseline: реализован
QH-2 Source Quality Filter: реализован в коде, ожидает локальный прогон
QH-3 Parent Expansion: реализован в коде, ожидает локальный прогон
QH-4 Semantic Warnings / Manual Labels: реализован в коде, ожидает локальный прогон
QH-5 Release Stabilization: PENDING_LOCAL_VALIDATION
Docker: после фактического QH-5 passed
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
Local Web UI
Telegram adapter
ChatRunsLogger
Eval baseline runner
Source Quality Filter
Parent Expansion
Semantic Warnings
QH release gate
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
User / CLI / API / Web UI / Telegram adapter
  -> SearchService
      -> QueryIntent
      -> ProjectGuard v2
      -> BM25 / Vector / Hybrid retrieval
      -> PostReranker
      -> ContextBuilder
          -> QH-2 Source Quality Filter
          -> QH-3 Parent Expansion
  -> ChatService
      -> PromptBuilder
      -> LLMClient
      -> AnswerValidator
      -> QH-4 SemanticWarningAnalyzer
      -> ResponseFormatter
      -> ChatRunsLogger
  -> Response
```

Ключевое правило:

```text
/search возвращает evidence/context
/chat возвращает осмысленный answer with citations
/ui вызывает /chat
Telegram adapter вызывает локальный /chat
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

Технические инструкции остаются в `RUNBOOK_V2.md`, `architecture.md`, `mvp.md`, `todo.md`, `QH_STATUS.md`, `FTT_STATUS.md`.

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

QH-4 добавляет warning-only слой:

```text
weak_sources_present
weak_primary_fallback
parent_expansion_applied
low_source_count
low_citation_coverage
structural_validation_errors
```

Не выполняет semantic/factual validation как hard-fail:

```text
поддерживается ли каждое утверждение конкретным source text
не сделала ли модель спорный вывод из короткого UML/heading/caption chunk
нет ли semantic hallucination при формально корректных [Sx]
```

Это quality debt, а не blocker текущего runtime.

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
QH-4 warnings не являются hard-fail
Docker не начинается до фактического QH-5 passed
```

## Локальная проверка Project Knowledge Bot 2026-05-18

По `docs/subprojects/asu-june-bot/TOMORROW_EXECUTION_PROTOCOL.md` выполнена основная часть QH-5 проверки:

```text
health_v2: status=ok
regression tests: 97 passed
API smoke: /health ok, /search ok/refused, /chat answered/refused
Web UI HTTP smoke: /ui status_code=200
chat_runs.jsonl: пишется
after_qh eval: 7/13, 53.8%
baseline comparison: 6/13 -> 7/13
```

Отчёт:

```text
docs/subprojects/asu-june-bot/smoke_report_qh_release.md
```

QH-5 пока остаётся `PENDING_LOCAL_VALIDATION`: Telegram smoke не выполнен, потому что в окружении нет `ASU_JUNE_BOT_TELEGRAM_TOKEN` и `ASU_JUNE_BOT_ALLOWED_CHAT_IDS`. Финальный QH gate с `--local-validation-done --baseline-compared` не запускался намеренно.

## Ближайшие действия

```text
1. Запустить Telegram smoke с локальным token/chat id.
2. После Telegram smoke выполнить final QH gate.
3. Если gate passed — обновить QH_STATUS.md и FTT_STATUS.md до QH-5 PASSED.
4. После QH-5 перейти к Docker stage.
```
