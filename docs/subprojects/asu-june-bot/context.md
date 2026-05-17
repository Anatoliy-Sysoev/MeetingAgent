# Контекст Project Knowledge Bot

Обновлено: 2026-05-16.

## 1. Назначение

Project Knowledge Bot — отдельный подпроект внутри MeetingAgent для разработки локального project-only RAG/Chat сервиса по проектной документации информационной системы.

Бот должен:

- искать факты в проектных источниках;
- давать структурированные ответы с citations;
- явно отделять подтвержденные факты от вывода;
- отказывать на вопросы вне корпуса;
- не запускать retrieval/LLM для refused/clarify;
- генерировать ответы только по `primary_sources` и `supporting_sources`;
- логировать chat-запуски для накопления dataset;
- иметь baseline evaluation перед улучшениями retrieval/context;
- предоставлять локальный Web UI и Telegram adapter поверх `/chat`.

Публичная документация подпроекта должна быть пригодна для выделения в отдельный репозиторий и не должна зависеть от конкретного заказчика или названия исходного внедрения.

## 2. Текущий статус

Подпроект доведён до уровня:

```text
API Search MVP — PASSED
CLI Chat MVP — PASSED_WITH_NOTES
API Chat MVP / POST /chat — PASSED_WITH_NOTES
Local Web UI / GET / and GET /ui — READY_FOR_LOCAL_SMOKE
Telegram adapter over local /chat — READY_FOR_LOCAL_SMOKE
QH-1 Observability + Eval Baseline — реализован, baseline требует анализа
```

Добавлено для завтрашней сдачи:

```text
единый лимит query = 2000 символов
локальная HTML-страница для /chat
Telegram long-polling adapter без новых зависимостей
завтрашний чек-лист запуска
Telegram runbook
unit tests для Telegram formatter
```

## 3. Текущий pipeline

```text
User question
  -> CLI / FastAPI / Web UI / Telegram adapter
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
/ui вызывает /chat
Telegram adapter вызывает локальный /chat
```

## 4. Реализованные API endpoints

```text
GET /
GET /ui
GET /health
POST /search
POST /chat
```

`POST /search` возвращает:

```text
query_intent
guard
context.primary_sources
context.supporting_sources
context.excluded_sources
results
warnings
diagnostics
```

`POST /chat` возвращает:

```text
status
query
answer
sources
search
warnings
diagnostics
```

## 5. Runtime-компоненты

### Общие ограничения

```text
src/asu_june_bot/core/limits.py
MAX_QUERY_CHARS = 2000
```

Лимит применяется в:

```text
ChatRequest
SearchRequest
POST /chat
POST /search
Web UI
Telegram adapter
```

### Extraction / Chunking / Index

```text
scripts/asu_june_bot_apply_config_v2_1.py
scripts/asu_june_bot_extract_text_v2.py
scripts/asu_june_bot_build_chunks_v2.py
scripts/asu_june_bot_audit_sources_v2.py
scripts/asu_june_bot_build_index_v2.py
scripts/asu_june_bot_health_v2.py
```

### Search / Guard / API / UI

```text
src/asu_june_bot/search/
src/asu_june_bot/retrieval/
src/asu_june_bot/guardrails/
src/asu_june_bot/health/
src/asu_june_bot/api/
src/asu_june_bot/api/routes_ui.py
scripts/asu_june_bot_search_v2.py
scripts/asu_june_bot_guard_v2_eval.py
scripts/asu_june_bot_api.py
```

### Chat / LLM / Telegram

```text
src/asu_june_bot/chat/
src/asu_june_bot/llm/
src/asu_june_bot/telegram_bot.py
scripts/asu_june_bot_chat.py
scripts/asu_june_bot_telegram.py
```

### Observability / Eval

```text
src/asu_june_bot/observability/
src/asu_june_bot/eval/
scripts/asu_june_bot_chat_eval.py
eval/cases/base.jsonl
eval/golden_answers/*.md
```

## 6. Текущий локальный результат

Corpus/index:

```text
documents = 213
blocks = 31076
chunks_v2 = 31302
indexed_chunks = 31285
skipped_code_chunks = 17
embedding_model = bge-m3
embedding_dim = 1024
```

Health:

```text
status = ok
vector_ready = true
bm25_ready = true
ollama_available = true
embedding_model_installed = true
```

ProjectGuard:

```text
false_allow = 0
```

Chat smoke:

```text
qwen2.5:7b-instruct -> answered / finish_reason=stop / validation_errors=[]
qwen3:4b -> llm_empty_response / finish_reason=length
qwen3:8b -> timeout/обрыв на CPU runtime
```

Рекомендуемая chat-модель MVP:

```text
qwen2.5:7b-instruct
```

## 7. QH-1 baseline

Первый baseline:

```text
total = 13
passed = 6
failed = 7
pass_rate = 46.2%
```

Не трактовать как провал `/chat`.

Категории проблем:

```text
ложные eval failures: source_titles, clarify must_include
project guard gap: логирование как проектный вопрос
real retrieval/context gaps: ФТТ 4.2.5, short UML/source traps, no-context/SLA
```

Уже исправлено:

```text
source_titles ищет не только в title, но и path/section/preview
clarify cases проверяют фактическую формулировку "Сформулируйте"
ProjectGuard получил project markers для логирования/Grafana Loki/журналирования
```

Следующее действие по качеству — повторить baseline после локального pull и тестов.

## 8. Завтрашний запуск

Главный документ:

```text
docs/subprojects/asu-june-bot/TOMORROW_START.md
```

Порядок:

```text
git pull
health
tests
API
Web UI
Telegram adapter
manual smoke
```

Ключевые команды:

```powershell
cd C:\Users\Сотрудник\Desktop\AI\MeetingAgent
(Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned) ; (& .\.venv\Scripts\Activate.ps1)
git checkout docs/asu-june-bot-subproject
git pull --ff-only origin docs/asu-june-bot-subproject
.\.venv\Scripts\python.exe scripts\asu_june_bot_api.py --host 127.0.0.1 --port 8000
```

Открыть UI:

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/ui
```

Telegram:

```powershell
$env:ASU_JUNE_BOT_TELEGRAM_TOKEN='PASTE_TOKEN_HERE'
$env:ASU_JUNE_BOT_CHAT_API_URL='http://127.0.0.1:8000/chat'
.\.venv\Scripts\python.exe scripts\asu_june_bot_telegram.py
```

## 9. Активная документация

Главные документы:

```text
README.md
TOMORROW_START.md
architecture.md
mvp.md
roadmap.md
decisions.md
RUNBOOK_V2.md
telegram.md
todo.md
eval_questions.md
ideas.md
product/
smoke_report_*.md
```

Устаревшие документы и case-conflict материалы не должны оставаться в активной зоне подпроекта.

## 10. Следующие шаги

Перед QH-2 завтра нужно:

```text
1. Выполнить TOMORROW_START.md.
2. Проверить UI и Telegram adapter вручную.
3. Зафиксировать демонстрационный smoke.
4. Повторить QH-1 baseline после последних eval/guard fixes.
5. После демонстрации перейти к QH-2 Source Quality Filter.
```

После повторного baseline:

```text
1. Проанализировать failures.
2. Реализовать QH-2 Source Quality Filter.
3. Сравнить eval baseline vs with_source_filter.
4. Реализовать QH-3 Parent Expansion только при необходимости.
5. Docker — только после QH-5 Release Stabilization.
```

## 11. Не делать сейчас

```text
не запускать --reset без причины
не удалять data/asu_june_bot
не пересчитывать embeddings, если индекс уже готов
не менять модель embeddings bge-m3
не коммитить Telegram token
не пытаться заставить /search писать осмысленные ответы
не внедрять source filter без повторного baseline
не внедрять parent expansion без замера эффекта source quality filter
не подключать DSPy в runtime
не делать LLM-as-judge/NLI до накопления dataset
не делать Docker до QH-5
не развивать scripts/09_chat.py как основной runtime
не смешивать старый RAG v1 и новый bot v2.1
```
