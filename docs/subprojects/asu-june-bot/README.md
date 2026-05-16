# Project Knowledge Bot

Статус: локальный project-only RAG/Chat MVP реализован, API `/search` и `/chat` работают, начат слой оценки качества QH-1.

Обновлено: 2026-05-16.

## 1. Назначение

Project Knowledge Bot — локальный AI-агент для работы с проектной документацией информационной системы.

Бот предназначен для системных аналитиков, архитекторов, руководителей проекта, тестировщиков и специалистов сопровождения, которым нужно быстро находить подтверждённые сведения в документах и получать ответы с привязкой к источникам.

Основная идея:

```text
документы проекта -> извлечение текста -> chunks -> индекс -> guarded search -> context -> grounded answer with citations
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
ChatRunsLogger
QH-1 Eval Baseline skeleton
```

Подтверждено smoke/regression:

```text
ProjectGuard v2 regression: false_allow = 0
SearchService tests: passed
API /search smoke: passed
ChatService tests: passed
CLI chat smoke: passed on qwen2.5:7b-instruct
API /chat runtime smoke: passed
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
```

### 3.3 Отказ вне проектного корпуса

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
User / CLI / API client
  -> FastAPI / CLI
  -> SearchService
      -> QueryIntent
      -> ProjectGuard v2
      -> Hybrid Retrieval: BM25 + vector
      -> PostReranker
      -> ContextBuilder
  -> ChatService
      -> PromptBuilder
      -> LLMClient
      -> AnswerValidator
      -> ResponseFormatter
      -> ChatRunsLogger
  -> Response with status, answer, sources, diagnostics
```

Ключевое разделение ответственности:

```text
/search = evidence/context endpoint
/chat = answer endpoint
```

`/search` не должен писать осмысленный ответ. `/chat` не должен дублировать логику guard/retrieval/context.

## 5. Состав документации

### Входные документы подпроекта

```text
docs/subprojects/asu-june-bot/README.md                этот файл, главный вход
docs/subprojects/asu-june-bot/context.md               текущий контекст и состояние
docs/subprojects/asu-june-bot/architecture.md          архитектура и компоненты
docs/subprojects/asu-june-bot/mvp.md                   ФТТ/MVP scope/acceptance
docs/subprojects/asu-june-bot/roadmap.md               план-график развития
docs/subprojects/asu-june-bot/todo.md                  актуальные задачи
docs/subprojects/asu-june-bot/decisions.md             архитектурные решения
docs/subprojects/asu-june-bot/RUNBOOK_V2.md            эксплуатационные команды
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

Назначение:

- сканирование `project_root`;
- исключение мусорных путей и временных файлов;
- извлечение текста из DOCX/XLSX/PDF/PPTX/HTML/text;
- сохранение blocks v2.

### 6.2 Chunking

```text
scripts/asu_june_bot_build_chunks_v2.py
```

Назначение:

- формирование parent/child chunks;
- сохранение `chunks_v2.jsonl`;
- заполнение metadata: `document_type`, `source_type`, `sections`, `requirement_id`, `integration`, `protocol`.

### 6.3 Index/Search

```text
scripts/asu_june_bot_build_index_v2.py
scripts/asu_june_bot_search_v2.py
src/asu_june_bot/retrieval/
src/asu_june_bot/search/
```

Назначение:

- embeddings через `bge-m3`;
- numpy vector index;
- BM25 index;
- hybrid search;
- rerank;
- context building.

### 6.4 Guardrails

```text
src/asu_june_bot/guardrails/
```

Назначение:

- pre-retrieval фильтрация;
- отказ на внепроектные и смешанные запросы;
- уточнение для неоднозначных запросов;
- предотвращение ложного допуска.

Критический критерий:

```text
false_allow = 0
```

### 6.5 API

```text
src/asu_june_bot/api/
scripts/asu_june_bot_api.py
```

Endpoints:

```text
GET /health
POST /search
POST /chat
```

### 6.6 Chat

```text
src/asu_june_bot/chat/
src/asu_june_bot/llm/
scripts/asu_june_bot_chat.py
```

Назначение:

- построение prompt по context;
- вызов локальной LLM через Ollama OpenAI-compatible API;
- structural validation ответа;
- форматирование ответа.

### 6.7 Observability/Eval

```text
src/asu_june_bot/observability/
src/asu_june_bot/eval/
scripts/asu_june_bot_chat_eval.py
eval/cases/base.jsonl
```

Назначение:

- логирование запусков `/chat` в `chat_runs.jsonl`;
- baseline evaluation без LLM-as-judge;
- deterministic checks;
- отчёты JSON/Markdown.

## 7. Локальный запуск

### 7.1 Health

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_health_v2.py
```

### 7.2 API

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_api.py --host 127.0.0.1 --port 8000
```

### 7.3 Search smoke

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/search" `
  -ContentType "application/json" `
  -Body '{"query":"Какие интеграции описаны в проектных документах?","mode":"hybrid","top_k":8}'
```

### 7.4 Chat smoke

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/chat" `
  -ContentType "application/json" `
  -Body '{"query":"Как происходит авторизация пользователей?","mode":"hybrid","top_k":5,"model":"qwen2.5:7b-instruct","max_tokens":500,"timeout_sec":300}'
```

### 7.5 Eval baseline

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_chat_eval.py --cases eval\cases\base.jsonl --label baseline --model qwen2.5:7b-instruct --top-k 5
```

## 8. Критерии готовности текущего MVP

```text
GET /health -> ok
POST /search project query -> ok, retrieval_called=true
POST /search out-of-project -> refused, retrieval_called=false
POST /chat project query -> answered, llm_called=true
POST /chat out-of-project -> refused, llm_called=false
ChatService tests -> passed
API tests -> passed
Guard regression -> false_allow=0
chat_runs.jsonl пишется локально
chat_eval baseline формирует JSON/Markdown reports
```

## 9. Ограничения текущей версии

Текущий `AnswerValidator` выполняет structural validation, но не semantic/factual validation.

Проверяется:

```text
пустой ответ
наличие sources
наличие ссылок [Sx]
unknown citations
external knowledge markers
answer length
citation density / coverage
```

Не проверяется:

```text
поддерживается ли каждое утверждение конкретным source text;
не делает ли модель спорный вывод из короткого UML/heading/caption chunk;
нет ли semantic hallucination при формально корректных [Sx].
```

Следующий этап качества:

```text
QH-2 Source Quality Filter
QH-3 Parent Expansion
```

## 10. Что не входит в текущий MVP

```text
полноценный UI
многопользовательский режим
RBAC по источникам
автоматическая синхронизация прав доступа
fine-tuning
LLM-as-judge
NLI groundedness model
DSPy runtime
LangGraph agent runtime
Dify/RAGFlow как основной runtime
промышленная эксплуатация
```

## 11. Подготовка к выделению в отдельный репозиторий

Подпроект уже отделён логически:

```text
src/asu_june_bot/
scripts/asu_june_bot_*.py
docs/subprojects/asu-june-bot/
eval/
```

Перед выделением в отдельный проект нужно:

- переименовать пакет и продуктовое имя при необходимости;
- вынести независимый README в корень нового репозитория;
- перенести product/architecture/runbook/todo/eval docs;
- оставить MeetingAgent только как upstream/source-проект;
- удалить проектно-специфичные названия из публичной документации;
- сохранить архив legacy-документов отдельно.
