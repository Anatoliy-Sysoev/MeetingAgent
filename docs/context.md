# Контекст проекта

Обновлено: 2026-05-19.

## Текущее состояние

MeetingAgent — приватный GitHub-backed пет-проект и локальный продуктовый репозиторий.

Репозиторий:

```text
Локальный путь: %USERPROFILE%\Desktop\AI\MeetingAgent
Remote: https://github.com/Anatoliy-Sysoev/MeetingAgent
Видимость: private
Каноническая ветка: main
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
Local Web UI / GET / and GET /ui: реализован, HTTP smoke пройден
Telegram adapter: реализован, local smoke закрыт
QH-1 Observability + Eval Baseline: реализован
QH-2 Source Quality Filter: реализован и локально проверен
QH-3 Parent Expansion: реализован и локально проверен
QH-4 Semantic Warnings / Manual Labels: реализован и локально проверен
QH-5 Release Stabilization: PASSED
Docker: следующий этап после QH-5
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

## Архитектурная документация

После актуализации 2026-05-19 архитектура разложена по уровням:

```text
docs/architecture/ARCHITECTURE.md
docs/architecture/TECHNICAL_FILE_RELATIONSHIPS.md
docs/architecture/MEETING_ARTIFACTS_PIPELINE.md
docs/subprojects/asu-june-bot/architecture.md
docs/subprojects/asu-june-bot/TECHNICAL_DIAGRAMS.md
```

Смысловое разделение:

```text
MeetingAgent baseline RAG v1          scripts/01..05, 04_query.py
Meeting processing                    06_transcribe_meeting.py, 07/08, meeting.schema.json
Project Knowledge Bot runtime         src/asu_june_bot, scripts/asu_june_bot_*.py
Quality / dataset pipeline            docs/quality, scripts/10..14, data/query_log*.jsonl
```

`scripts/09_chat.py` остаётся legacy/prototype для старого project-only baseline и не считается основным runtime Project Knowledge Bot.

## Dataset / evaluation pipeline

В `main` есть отдельный контур качества retrieval/chat:

```text
docs/quality/QUERY_FEEDBACK_LOOP.md
docs/quality/DATASET_PIPELINE_STATUS.md
docs/quality/synthetic_seed_queries.jsonl
docs/quality/realistic_100_queries.jsonl
scripts/10_review_queries.py
scripts/11_run_synthetic_seed.py
scripts/12_analyze_seed_report.py
scripts/13_build_eval_candidates.py
scripts/14_run_realistic_100_eval.py
scripts/15_prepare_realistic_eval_review.py
scripts/run_realistic_100_eval_automation.ps1
scripts/realistic_100_eval_status.ps1
```

Этот контур является параллельным quality/eval слоем, а не заменой bot runtime. Цель: логировать реальные запросы, делать ручную разметку, формировать eval candidates и проверять retrieval improvements.

Автоматизация realistic 100:

```text
19:00 — scripts/run_realistic_100_eval_automation.ps1 запускает полный realistic 100 eval.
Каждый час — scripts/realistic_100_eval_status.ps1 -PrepareNextIfComplete снимает статус.
Если rows >= 100, review готовится автоматически в data/realistic_100_eval_review.jsonl.
10:00 следующего дня — финальная проверка: если rows < 100, сообщить текущий этап.
```

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

## Локальная проверка Project Knowledge Bot 2026-05-18 / 2026-05-19

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

Дополнительно 2026-05-19:

```text
FastAPI /health перепроверен локально: status=ok, vector_ready=true, bm25_ready=true, guard_v2_ready=true
добавлен scripts/asu_june_bot_start_telegram.ps1 для безопасного локального запуска Telegram adapter без передачи token в command line
scripts/14_run_realistic_100_eval.py пишет START/DONE по каждому вопросу с flush=True, чтобы фоновый smoke было видно в logs
realistic 100 smoke --limit 10: 10/10 answered, failures=0, parse_errors=0, avg_duration_sec=131.4
final QH gate: status=passed, pending=[]
```

Отчёт:

```text
docs/subprojects/asu-june-bot/smoke_report_qh_release.md
```

QH-5 закрыт как `PASSED`: финальный gate выполнен с `--local-validation-done --baseline-compared`, pending-пунктов нет. Telegram token не хранится в Git, docs или runtime-артефактах.

## Ближайшие действия

```text
1. Начать Docker stage Project Knowledge Bot.
2. Запустить полный realistic 100 eval и manual review dataset pipeline.
3. Решить порядок: QH-6 Feedback Dataset Loop до/после Docker hardening.
4. По общему MeetingAgent вернуться к incremental RAG update и meeting watcher.
```
