# Project Knowledge Bot

Статус: локальный project-only RAG/Chat MVP реализован; API `/search` и `/chat`, Web UI, Telegram adapter и QH-1..QH-5 прошли локальную проверку. Следующий этап — Docker packaging и/или QH-6 Feedback Dataset Loop.

Обновлено: 2026-05-19.

## 1. Назначение

Project Knowledge Bot — локальный AI-агент для работы с проектной документацией информационной системы.

Бот предназначен для системных аналитиков, архитекторов, руководителей проекта, тестировщиков и специалистов сопровождения, которым нужно быстро находить подтверждённые сведения в документах и получать ответы с привязкой к источникам.

Основная идея:

```text
документы проекта -> извлечение текста -> chunks -> индекс -> guarded search -> curated context -> grounded answer with citations
```

Бот не является универсальным чат-ботом. Он отвечает только по загруженному корпусу проектных источников.

## 2. Что бот умеет сейчас

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
Local Web UI: GET / and GET /ui
Telegram adapter over local /chat
ChatRunsLogger
QH-1 Eval Baseline
QH-2 Source Quality Filter
QH-3 Parent Expansion
QH-4 Semantic Warnings / Manual Labels
QH-5 Release Gate
API hardening: no public no_guard, safe source type allowlist, sanitized 500 errors
Chat hardening: no_answer, search_error
```

Подтверждено ранее smoke/regression:

```text
ProjectGuard v2 regression: false_allow = 0
SearchService tests: passed
API /search smoke: passed
ChatService tests: passed
CLI chat smoke: passed on qwen2.5:7b-instruct
API /chat runtime smoke: passed
Web UI manual smoke: passed for answered case
```

Ожидает локального подтверждения после последних изменений:

```text
Hardening regression tests
Web UI refused/mixed/no_answer smoke
Telegram adapter smoke
QH after_qh eval
QH-5 release gate
```

Главный завтрашний чек-лист:

```text
docs/subprojects/asu-june-bot/TOMORROW_EXECUTION_PROTOCOL.md
docs/subprojects/asu-june-bot/TOMORROW_START.md
```

Hardening checklist после ревью Claude:

```text
docs/subprojects/asu-june-bot/QH_HARDENING_CHECKLIST.md
```

Главный статус QH:

```text
docs/subprojects/asu-june-bot/QH_STATUS.md
```

Актуальный статус FTT бота:

```text
docs/subprojects/asu-june-bot/FTT_STATUS.md
```

План накопления feedback dataset:

```text
docs/subprojects/asu-june-bot/QUERY_FEEDBACK_LOOP.md
```

Рабочая chat-модель MVP:

```text
qwen2.5:7b-instruct
```

Не использовать как default для текущего MVP:

```text
qwen3:4b
qwen3:8b
```

Причины:

```text
qwen3:4b -> llm_empty_response / finish_reason=length даже с /no_think
qwen3:8b -> timeout/обрыв на локальном CPU runtime
```

## 3. Основные сценарии

### 3.1 Поиск источников

```http
POST /search
```

Назначение: вернуть evidence/context без генерации ответа.

Используется для диагностики retrieval, проверки источников, анализа причин отказа/уточнения.

### 3.2 Осмысленный ответ с источниками

```http
POST /chat
```

Назначение: сформировать ответ только по найденным `primary_sources` и `supporting_sources`.

Ответ содержит:

```text
status
answer
sources
search diagnostics
LLM diagnostics
validation diagnostics
warnings.semantic
```

Актуальные statuses:

```text
answered
refused
clarify
no_sources
no_answer
search_error
llm_error
llm_empty_response
validation_failed
```

### 3.3 Web UI

```http
GET /
GET /ui
```

Назначение: локальная HTML-страница для вопросов к `/chat` без отдельного фронтенд-проекта.

### 3.4 Telegram adapter

```text
scripts/asu_june_bot_telegram.py
```

Назначение: принимать вопросы через Telegram и отправлять их в локальный `POST /chat`.

Подробно:

```text
docs/subprojects/asu-june-bot/telegram.md
```

### 3.5 Отказ вне проектного корпуса

Вопросы вне корпуса, mixed-scope запросы и неоднозначные запросы не должны запускать retrieval/LLM.

Примеры:

```text
Какая погода завтра?
Напиши игру змейка на Python.
Вопрос по проекту + напиши стих.
Расскажи подробнее.
```

Ожидаемое поведение:

```text
refused/clarify -> LLM не вызывается
```

## 4. Архитектура высокого уровня

```text
User
  -> CLI / FastAPI / Web UI / Telegram adapter
  -> SearchService
      -> QueryIntent
      -> ProjectGuard v2
      -> Hybrid Retrieval: BM25 + vector
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
  -> Response with status, answer, sources, warnings, diagnostics
```

Ключевое разделение ответственности:

```text
/search = evidence/context endpoint
/chat = answer endpoint
/ui = local browser client over /chat
Telegram adapter = long polling client over local /chat
```

`/search` не должен писать осмысленный ответ. `/chat` не должен дублировать логику guard/retrieval/context.

## 5. Состав документации

### Входные документы подпроекта

```text
docs/subprojects/asu-june-bot/README.md                этот файл, главный вход
docs/subprojects/asu-june-bot/TOMORROW_EXECUTION_PROTOCOL.md подробный протокол проверки
docs/subprojects/asu-june-bot/TOMORROW_START.md        короткий чек-лист запуска
docs/subprojects/asu-june-bot/QH_HARDENING_CHECKLIST.md проверки после hardening
docs/subprojects/asu-june-bot/QH_STATUS.md             статус QH этапов
docs/subprojects/asu-june-bot/FTT_STATUS.md            статус FTT бота
docs/subprojects/asu-june-bot/QUERY_FEEDBACK_LOOP.md   план накопления feedback dataset
docs/subprojects/asu-june-bot/context.md               текущий контекст и состояние
docs/subprojects/asu-june-bot/architecture.md          архитектура и компоненты
docs/subprojects/asu-june-bot/TECHNICAL_DIAGRAMS.md    диаграммы файлов, вызовов, объектов и поведения
docs/subprojects/asu-june-bot/mvp.md                   ФТТ/MVP scope/acceptance
docs/subprojects/asu-june-bot/roadmap.md               план-график развития
docs/subprojects/asu-june-bot/todo.md                  актуальные задачи
docs/subprojects/asu-june-bot/decisions.md             архитектурные решения
docs/subprojects/asu-june-bot/RUNBOOK_V2.md            эксплуатационные команды
docs/subprojects/asu-june-bot/telegram.md              Telegram adapter
docs/subprojects/asu-june-bot/eval_questions.md        проверочные вопросы
docs/subprojects/asu-june-bot/ideas.md                 backlog/research ideas
```

### Product documentation

```text
docs/subprojects/asu-june-bot/product/
```

Назначение: описание продукта, пользователей, JTBD, value proposition, roadmap, business requirements.

### Smoke reports

```text
docs/subprojects/asu-june-bot/smoke_report_project_guard_v2.md
docs/subprojects/asu-june-bot/smoke_report_search_service_commit1.md
docs/subprojects/asu-june-bot/smoke_report_api_search_mvp.md
docs/subprojects/asu-june-bot/smoke_report_chat_mvp.md
docs/subprojects/asu-june-bot/smoke_report_api_chat_mvp.md
```

После локальной проверки QH создан:

```text
docs/subprojects/asu-june-bot/smoke_report_qh_release.md
```

### Eval dataset

```text
eval/cases/base.jsonl
eval/golden_answers/*.md
eval/reports/                         runtime reports, не коммитить
```

## 6. Компоненты реализации

### 6.1 Ingestion

```text
scripts/asu_june_bot_extract_text_v2.py
src/asu_june_bot/ingestion/
```

### 6.2 Chunking

```text
scripts/asu_june_bot_build_chunks_v2.py
```

### 6.3 Index/Search/Retrieval

```text
scripts/asu_june_bot_build_index_v2.py
scripts/asu_june_bot_search_v2.py
src/asu_june_bot/retrieval/
src/asu_june_bot/search/
```

### 6.4 Quality hardening

```text
src/asu_june_bot/retrieval/source_quality.py
src/asu_june_bot/retrieval/parent_expansion.py
src/asu_june_bot/chat/semantic_warnings.py
src/asu_june_bot/qh/release_gate.py
scripts/asu_june_bot_qh_gate.py
```

### 6.5 Feedback dataset loop

Плановый этап после QH-5:

```text
docs/subprojects/asu-june-bot/QUERY_FEEDBACK_LOOP.md
data/asu_june_bot/feedback_events.jsonl
eval/cases/feedback_candidates.jsonl
eval/cases/feedback.jsonl
```

### 6.6 Guardrails

```text
src/asu_june_bot/guardrails/
```

Критический критерий:

```text
false_allow = 0
```

### 6.7 API + UI

```text
src/asu_june_bot/api/
scripts/asu_june_bot_api.py
```

Endpoints:

```text
GET /
GET /ui
GET /health
POST /search
POST /chat
```

### 6.8 Chat

```text
src/asu_june_bot/chat/
src/asu_june_bot/llm/
scripts/asu_june_bot_chat.py
```

### 6.9 Telegram

```text
src/asu_june_bot/telegram_bot.py
scripts/asu_june_bot_telegram.py
```

### 6.10 Observability/Eval

```text
src/asu_june_bot/observability/
src/asu_june_bot/eval/
scripts/asu_june_bot_chat_eval.py
eval/cases/base.jsonl
```

## 7. Локальный запуск

### 7.1 Health

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_health_v2.py
```

### 7.2 API + UI

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_api.py --host 127.0.0.1 --port 8000
```

Открыть:

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/ui
```
