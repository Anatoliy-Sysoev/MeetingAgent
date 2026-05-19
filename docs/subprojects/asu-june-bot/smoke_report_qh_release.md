# QH-5 local validation report

Дата: 2026-05-18.

Ветка на момент прогона: `docs/asu-june-bot-subproject`. После merge PR #7 каноническая ветка для повторного запуска — `main`.

Commit: `bb0b0856628052643fad8125151bbd679dcb6689`.

## Итог

```text
Итоговый статус после addendum 2026-05-19: QH-5 PASSED.
```

Исторический срез 2026-05-18: локальные regression tests, API smoke, Web UI HTTP-smoke, chat logging и `after_qh` eval были выполнены, но Telegram smoke ещё не был закрыт.

Addendum 2026-05-19: Telegram smoke закрыт локально без сохранения token в Git/docs, final QH gate выполнен с `--local-validation-done --baseline-compared` и вернул `status=passed`, `pending=[]`.

## Environment

Ollama models:

```text
bge-m3:latest
qwen2.5:7b-instruct
mistral:7b-instruct-q4_0
qwen3:4b
qwen3:8b
```

Health v2:

```text
status = ok
vector_ready = true
bm25_ready = true
ollama_available = true
embedding_model_installed = true
chunks_v2 = 31302
index_count = 31285
embedding_model = bge-m3
```

## Regression tests

```text
tests/asu_june_bot/chat/test_chat_service.py: 9 passed
tests/asu_june_bot/chat/test_semantic_warnings.py: 3 passed
tests/asu_june_bot/api/test_health.py + test_search_smoke.py + test_chat_smoke.py: 13 passed
tests/asu_june_bot/retrieval/test_source_quality.py + test_parent_expansion.py + test_context_builder_qh.py: 7 passed
tests/asu_june_bot/observability/test_chat_runs.py + eval/test_checks.py + eval/test_runner.py + qh/test_release_gate.py: 8 passed
tests/asu_june_bot/test_project_guard_v2_cases.py + test_telegram_bot.py: 53 passed
tests/asu_june_bot/api/test_errors.py + retrieval/test_source_policy.py: 4 passed
```

Итог: `97 passed`, без `FAILED` и `ERROR`.

## QH gate before smoke

```text
status = pending_local_validation
passed = QH-1, QH-2, QH-3, QH-4, QH-5C, QH-5D
pending = QH-5A, QH-5B
failed = []
```

## API smoke

API запускался локально:

```text
http://127.0.0.1:8000
```

Проверки:

```text
GET /health -> status=ok, service=asu_june_bot
POST /search project query -> status=ok, results_count=8, primary_count=2, supporting_count=5
POST /search weather query -> status=refused, results_count=0
POST /chat project query -> status=answered, sources_count=5, llm_called=true, semantic warnings=2
POST /chat weather query -> status=refused, sources_count=0, llm_called=false
POST /chat mixed query -> status=refused, sources_count=0, llm_called=false
```

Проектный `/chat` вопрос:

```text
СоИ AD как происходит авторизация пользователей?
```

Краткий результат:

```text
answer_len = 725
sources_count = 5
status = answered
```

## Web UI smoke

HTTP-проверка `/ui`:

```text
status_code = 200
Project Knowledge Bot title = true
input = true
model = true
top_k = true
Ответ = true
Источники = true
Диагностика = true
2000 counter = true
```

Ручной браузерный клик в UI в этом прогоне не выполнялся. Поведение `/chat`, на который завязан UI, проверено через API smoke.

## Chat runs

`data/asu_june_bot/chat_runs.jsonl` пишет JSONL-записи.

Последняя проверенная запись:

```text
status = refused
llm_called = false
latency_ms = 49
semantic_warnings.count = 0
```

## Telegram smoke

Закрыто локально 2026-05-19.

Ограничения фиксации:

```text
Telegram token не сохраняется в Git, docs, .env или runtime-отчеты
для безопасного запуска используется scripts/asu_june_bot_start_telegram.ps1
```

Проверяемые сценарии smoke:

```text
1. /health
2. проектный вопрос
3. отказ на внепроектный вопрос
```

## Eval after QH

Команда:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_chat_eval.py --cases eval\cases\base.jsonl --label after_qh --model qwen2.5:7b-instruct --top-k 5
```

Результат:

```text
total = 13
passed = 7
failed = 6
pass_rate = 53.8%
report = eval/reports/2026-05-18T152255+0000__after_qh.md
```

Сравнение с последним baseline:

```text
baseline 2026-05-17: 6/13, 46.2%
after_qh 2026-05-18: 7/13, 53.8%
delta: +1 passed, +7.6 percentage points
```

Провалы after_qh:

```text
PROJECT-FTT-425-001
PROJECT-IB-001
SHORTSRC-AD-001
CLARIFY-001
CLARIFY-002
NO-CONTEXT-001
```

Интерпретация:

```text
after_qh не ухудшил общий baseline, но eval всё ещё показывает реальные retrieval/context gaps и дефекты критериев clarify.
```

## Решение

```text
QH-5 = PASSED
```

Финальный gate:

```text
.\.venv\Scripts\python.exe scripts\asu_june_bot_qh_gate.py --local-validation-done --baseline-compared --json
status = passed
pending = []
failed = []
```
