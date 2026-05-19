# FTT status Project Knowledge Bot

Обновлено: 2026-05-18.

## 1. Назначение

Документ фиксирует актуальный статус функционально-технических требований Project Knowledge Bot.

Этот файл является оперативной картой готовности именно бота. Он дополняет:

```text
docs/subprojects/asu-june-bot/mvp.md
docs/subprojects/asu-june-bot/QH_STATUS.md
docs/subprojects/asu-june-bot/roadmap.md
docs/subprojects/asu-june-bot/todo.md
```

Важно: требования ниже относятся к подпроекту бота, а не к исходным ФТТ внешней информационной системы.

## 2. Сводный вывод

Текущий статус:

```text
Bot MVP core: IMPLEMENTED
Search API: PASSED
Chat API: PASSED_WITH_NOTES
Local Web UI: IMPLEMENTED_CODE_READY
Telegram adapter: IMPLEMENTED_CODE_READY
QH-1: IMPLEMENTED
QH-2: IMPLEMENTED_CODE_READY
QH-3: IMPLEMENTED_CODE_READY
QH-4: IMPLEMENTED_CODE_READY
QH-5: PENDING_LOCAL_VALIDATION
Docker: NOT_STARTED_AFTER_QH5
```

Осталось реализовать до закрытия FTT текущего MVP:

```text
1. Локально проверить Telegram adapter smoke.
2. Выполнить final QH gate с --local-validation-done --baseline-compared.
3. Закрыть QH-5 как PASSED, если final gate зелёный.
```

Уже подтверждено 2026-05-18:

```text
regression tests: 97 passed
health_v2: ok
API smoke: ok/refused сценарии пройдены
Web UI HTTP smoke: /ui отдаёт страницу с основными элементами
chat_runs.jsonl: пишется
after_qh eval: 7/13 против baseline 6/13
smoke_report_qh_release.md: создан с решением QH-5 PENDING_LOCAL_VALIDATION
```

Осталось реализовать после закрытия текущего MVP:

```text
1. Docker packaging.
2. README/runbook под docker deployment.
3. Подготовка к выделению в отдельный репозиторий.
4. UI hardening, если текущей HTML-страницы недостаточно.
5. Optional: OpenWebUI/другой внешний UI adapter.
6. Optional: advanced semantic/factual validation после накопления dataset.
```

## 3. Детальный статус AJB-FTT

### AJB-FTT-01. Project-only режим

Статус:

```text
PASSED
```

Закрыто:

```text
ProjectGuard v2
false_allow = 0
mixed-scope refused
out-of-project refused
ambiguous clarify
refused/clarify без retrieval и без LLM
```

Осталось:

```text
расширять guard только через eval cases, не через бесконечное раздувание маркеров
```

### AJB-FTT-02. Pre-retrieval guard

Статус:

```text
PASSED
```

Закрыто:

```text
SearchService вызывает guard до retrieval
/chat не вызывает LLM при refused/clarify
```

Осталось:

```text
только регрессионный контроль
```

### AJB-FTT-03. Извлечение текста

Статус:

```text
PASSED_FOR_CURRENT_CORPUS
```

Закрыто:

```text
extract_text_v2
blocks.jsonl
DOCX/XLSX/PDF/PPTX/HTML/text parsing
source audit
```

Осталось:

```text
новые edge cases документов фиксировать как отдельные defects
```

### AJB-FTT-04. Chunking v2

Статус:

```text
PASSED_FOR_CURRENT_CORPUS
```

Закрыто:

```text
chunks_v2.jsonl
parent/child chunks
table rows
metadata
```

Осталось:

```text
семантическую нарезку не делать до фактической проблемы в eval
```

### AJB-FTT-05. Индексация и embeddings cache

Статус:

```text
PASSED_FOR_CURRENT_CORPUS
```

Закрыто:

```text
bge-m3
embeddings_cache_v2
numpy_index_v2
health_v2
```

Осталось:

```text
не пересчитывать embeddings без необходимости
```

### AJB-FTT-06. Гибридный поиск

Статус:

```text
PASSED
```

Закрыто:

```text
BM25
Vector search
Hybrid merge
PostReranker
```

Осталось:

```text
качество проверять через eval, а не вручную по единичным вопросам
```

### AJB-FTT-07. ContextBuilder

Статус:

```text
PASSED_WITH_QH_ENHANCEMENTS_CODE_READY
```

Закрыто:

```text
primary_sources
supporting_sources
excluded_sources
source_quality diagnostics
parent_expansion diagnostics
```

Осталось:

```text
локально подтверждено 2026-05-18
```

### AJB-FTT-08. Search API

Статус:

```text
PASSED
```

Закрыто:

```text
GET /health
POST /search
SearchRequest validation
MAX_QUERY_CHARS = 2000
smoke_report_api_search_mvp.md
```

Осталось:

```text
регрессионный smoke завтра
```

### AJB-FTT-09. Chat Service

Статус:

```text
PASSED_WITH_NOTES
```

Закрыто:

```text
ChatService
PromptBuilder
LLMClient
OllamaOpenAIClient
AnswerValidator
ResponseFormatter
Chat CLI
```

Осталось:

```text
answered на qwen2.5:7b-instruct подтверждено 2026-05-18
actual smoke output зафиксирован в smoke_report_qh_release.md
```

Ограничение:

```text
semantic/factual validation не является hard-fail
```

### AJB-FTT-10. Chat API

Статус:

```text
PASSED_WITH_NOTES
```

Закрыто:

```text
POST /chat
API validation
API tests
runtime smoke ранее пройден
```

Осталось:

```text
регрессионный smoke подтвержден 2026-05-18
```

### AJB-FTT-11. Structural Answer Validation

Статус:

```text
PASSED
```

Закрыто:

```text
empty answer
missing sources
missing citations
unknown citations
external knowledge markers
answer length
citation density / coverage
```

Осталось:

```text
не путать structural validation с factual validation
```

### AJB-FTT-12. Observability

Статус:

```text
IMPLEMENTED_CODE_READY
```

Закрыто:

```text
ChatRunsLogger
chat_runs.jsonl
latency_ms
status/model/sources/diagnostics
manual_label/manual_issue placeholders
semantic_warnings logging
```

Осталось:

```text
локально подтверждено 2026-05-18
```

### AJB-FTT-13. Eval Baseline

Статус:

```text
IMPLEMENTED
```

Закрыто:

```text
eval/cases/base.jsonl
scripts/asu_june_bot_chat_eval.py
JSON/Markdown reports
baseline report
```

Осталось:

```text
eval quality debt: 6 failed cases остаются в backlog
```

### AJB-FTT-14. Local Web UI

Статус:

```text
IMPLEMENTED_CODE_READY
```

Закрыто:

```text
GET /
GET /ui
HTML page over /chat
MAX_QUERY_CHARS counter
```

Осталось:

```text
ручной browser click smoke
HTTP smoke /ui подтвержден 2026-05-18
```

### AJB-FTT-15. Telegram adapter

Статус:

```text
IMPLEMENTED_CODE_READY
```

Закрыто:

```text
src/asu_june_bot/telegram_bot.py
scripts/asu_june_bot_telegram.py
/start
/help
/health
allowed chat ids
formatting answer + sources
```

Осталось:

```text
создать/вставить token локально
запустить adapter
отправить тестовый вопрос
проверить refused/answered сценарии
не коммитить token
```

### AJB-FTT-16. Input limits

Статус:

```text
PASSED
```

Закрыто:

```text
MAX_QUERY_CHARS = 2000
SearchRequest
ChatRequest
POST /search
POST /chat
Web UI
Telegram adapter
```

Осталось:

```text
регрессионный тест после pull
```

### AJB-FTT-17. QH-2 Source Quality Filter

Статус:

```text
IMPLEMENTED_CODE_READY
```

Закрыто:

```text
source_quality.py
ContextBuilder integration
weak_source diagnostics
primary eligibility
weak primary demotion
```

Осталось:

```text
локально прогнать tests/retrieval
проверить after_qh eval на реальных вопросах
```

### AJB-FTT-18. QH-3 Parent Expansion

Статус:

```text
IMPLEMENTED_CODE_READY
```

Закрыто:

```text
parent_expansion.py
bounded expansion
max_parent_chars
neighbor/parent context only from candidate pool
ContextBuilder diagnostics
```

Осталось:

```text
локально прогнать tests/retrieval
проверить, что expansion не ухудшил ответы
```

### AJB-FTT-19. QH-4 Semantic Warnings / Manual Labels

Статус:

```text
IMPLEMENTED_CODE_READY
```

Закрыто:

```text
semantic_warnings.py
warnings.semantic in /chat
semantic_warnings diagnostics
chat_runs semantic_warnings
manual labels placeholders
```

Осталось:

```text
локально проверить warnings в /chat output
не превращать warnings в hard-fail
```

### AJB-FTT-20. QH-5 Release Gate

Статус:

```text
PENDING_LOCAL_VALIDATION
```

Закрыто:

```text
release_gate.py
scripts/asu_june_bot_qh_gate.py
QH-5A/QH-5B pending до локального smoke/eval
Docker explicitly postponed
```

Осталось:

```text
local-validation-done
baseline-compared
Telegram smoke
QH_STATUS.md -> QH-5 PASSED
smoke_report_qh_release.md
```

## 4. Остаток реализации по FTT до сдачи

Минимальный остаток:

```text
QH-5A. Telegram smoke на рабочем ПК
QH-5B. final QH gate после Telegram smoke
QH-5C. финальное обновление QH_STATUS.md после факта
```

Это не новая функциональность, а подтверждение готовности.

## 5. Остаток реализации после сдачи MVP

После QH-5:

```text
Dockerfile
.dockerignore
docker-compose.yml
.env.example for Docker
docs/deployment/docker.md
healthcheck внутри compose
volume strategy для data/asu_june_bot
подготовка отдельного репозитория
```

Позже, не в текущий MVP:

```text
RBAC по источникам
multi-user mode
job queue для reindex/eval
production UI
OpenWebUI adapter
NLI/LLM-as-judge factual validation
DSPy optimization experiments
GPU inference path
```

## 6. Что не реализовывать сейчас

```text
не делать Docker до QH-5 passed
не подключать DSPy в runtime
не делать fine-tuning
не делать LLM-as-judge без dataset
не превращать semantic warnings в отказ
не расширять OUT_OF_PROJECT_MARKERS бесконечно
не переписывать в монолит
не смешивать old scripts/09_chat.py и bot runtime
```
