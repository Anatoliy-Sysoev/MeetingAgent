# TODO Project Knowledge Bot

Обновлено: 2026-05-18.

## Текущий статус

API Search MVP закрыт. CLI Chat MVP и API Chat MVP прошли smoke. Добавлены локальный Web UI, Telegram adapter и единый лимит длины запроса.

QH-этапы доведены до состояния:

```text
QH-1 Observability + Eval Baseline        IMPLEMENTED
QH-2 Source Quality Filter                IMPLEMENTED
QH-3 Parent Expansion                     IMPLEMENTED
QH-4 Semantic Warnings / Manual Labels    IMPLEMENTED
QH-5 Release Stabilization                PENDING_LOCAL_VALIDATION
```

Локальная проверка 2026-05-18:

```text
regression tests: 97 passed
health_v2: ok
API smoke: ok
Web UI HTTP smoke: ok
after_qh eval: 7/13, 53.8%
baseline comparison: 6/13 -> 7/13
smoke_report_qh_release.md создан
Telegram smoke: не выполнен, нет локального token/chat id
final QH gate: не запускался
```

После ручного UI smoke и ревью Claude добавлен hardening:

```text
routes_ui.py f-string fix
ChatStatus.NO_ANSWER
ChatStatus.SEARCH_ERROR
public /search no_guard rejected
safe include_source_types allowlist
sanitized unhandled API errors
short project queries added to guard regression: Паспорт ИС / Протокол ПСИ / сценарии ПМИ
```

Главные документы:

```text
docs/subprojects/asu-june-bot/TOMORROW_EXECUTION_PROTOCOL.md
docs/subprojects/asu-june-bot/QH_HARDENING_CHECKLIST.md
docs/subprojects/asu-june-bot/QH_STATUS.md
docs/subprojects/asu-june-bot/FTT_STATUS.md
```

Важно: QH-5 можно закрывать только после локального regression, API smoke, UI smoke, Telegram smoke, after_qh eval и final QH gate.

Принято решение: Docker-упаковка выполняется **после фактического QH-5 passed**, а не сейчас.

## Следующий практический шаг

```text
Telegram smoke
final QH gate
QH_STATUS.md / FTT_STATUS.md -> QH-5 PASSED только после gate
```

## Закрыто ранее

```text
Extraction/Chunking v2.1
Index/Search v2
Search Quality v2.2
ProjectGuard v2
SearchService Commit 1
FastAPI /health и /search
API Search MVP smoke/docs
Chat MVP design
LLMClient + PromptBuilder
ChatService + CLI skeleton
Chat MVP hardening после внешнего ревью
Chat MVP smoke на qwen2.5:7b-instruct
POST /chat route implementation
API Chat MVP smoke tests implementation
POST /chat runtime smoke
QH-1 Observability + Eval Baseline code implementation
Product docs refresh
Docker-after-QH-5 decision
MAX_QUERY_CHARS = 2000
Local Web UI: GET / and GET /ui
Telegram adapter
QH-2 Source Quality Filter
QH-3 Parent Expansion
QH-4 Semantic Warnings
QH-5 release gate
```

## Закрыто после ревью Claude / ручного UI smoke

```text
UI answered-case smoke подтвержден вручную
routes_ui.py f-string bug исправлен
no_answer status добавлен
search_error status добавлен
AnswerValidator больше не превращает честное 'недостаточно данных' в validation_failed
/search больше не принимает публичный no_guard
SearchApiRequest extra='forbid'
SourcePolicy ограничивает requested source types безопасным allowlist
unhandled API errors санитизированы
QH_HARDENING_CHECKLIST.md добавлен
README/RUNBOOK/context обновлены
```

## Ожидаемые regression tests после pull

```powershell
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\chat\test_chat_service.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\chat\test_semantic_warnings.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\api\test_health.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\api\test_search_smoke.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\api\test_chat_smoke.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\api\test_errors.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\retrieval\test_source_quality.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\retrieval\test_parent_expansion.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\retrieval\test_context_builder_qh.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\retrieval\test_source_policy.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\observability\test_chat_runs.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\eval\test_checks.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\eval\test_runner.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\qh\test_release_gate.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\test_project_guard_v2_cases.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\test_telegram_bot.py -q
```

Ожидаемо:

```text
нет FAILED
нет ERROR
```

Ориентировочные counts:

```text
ChatService: 9 passed
Semantic warnings: 3 passed
API health: 1 passed
API search: 5 passed
API chat: 7 passed
API errors: 1 passed
Source quality: 3 passed
Parent expansion: 2 passed
ContextBuilder QH: 2 passed
Source policy: 3 passed
observability: 2 passed
eval checks: 3 passed
eval runner: 1 passed
QH release gate: 2 passed
ProjectGuard cases: 49 passed
Telegram formatter: 4 passed
```

Если counts немного отличаются из-за новых тестов, главным критерием остается отсутствие `FAILED` и `ERROR`.

## API/UI hardening smoke

После запуска API:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_api.py --host 127.0.0.1 --port 8000
```

Проверить:

```text
/search with no_guard=true -> HTTP 422
AD project query -> answered
weather query -> refused
mixed query -> refused
Протокол ПСИ -> answered/no_answer, но не validation_failed/refused
сценарии ПМИ -> answered/no_answer, но не refused/validation_failed
Паспорт ИС -> answered/no_answer, но не refused/validation_failed
```

Подробные команды:

```text
docs/subprojects/asu-june-bot/QH_HARDENING_CHECKLIST.md
```

## QH-1 baseline: первичный вывод

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

Повторный eval после hardening/QH:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_chat_eval.py --cases eval\cases\base.jsonl --label after_qh --model qwen2.5:7b-instruct --top-k 5
```

Сравнить:

```text
eval/reports/*__baseline.md
eval/reports/*__after_qh.md
```

## Что дальше после локального QH-5 passed

Если тесты, API smoke, UI smoke, Telegram smoke и after_qh eval прошли приемлемо:

```text
1. Зафиксировать smoke_report_qh_release.md.
2. Обновить QH_STATUS.md: QH-5 -> PASSED.
3. Обновить FTT_STATUS.md.
4. После этого можно начинать Docker stage.
```

Если есть падения:

```text
1. Не начинать Docker.
2. Исправить только блокирующие дефекты запуска/API/UI/Telegram.
3. Quality defects retrieval/context фиксировать отдельно, не ломая демо.
```

## Важное ограничение результата

Chat MVP smoke прошёл как structural validation, но не как полноценная semantic/factual validation.

QH-4 добавляет warning-only слой, но не доказывает фактическую истинность каждого утверждения.

Текущий `AnswerValidator` проверяет:

```text
пустой ответ
наличие источников
наличие ссылок [Sx]
unknown citations
external knowledge markers
answer length
citation density / coverage
```

QH-4 дополнительно предупреждает:

```text
weak_sources_present
weak_primary_fallback
parent_expansion_applied
low_source_count
low_citation_coverage
structural_validation_errors
```

Он не проверяет:

```text
поддерживается ли каждое утверждение конкретным source text
не делает ли модель спорный вывод из короткого UML/heading chunk
нет ли semantic hallucination при формально корректных [Sx]
```

Это фиксируется как quality debt, а не runtime blocker.

## Не делать сейчас

```text
не пытаться заставить /search писать осмысленные ответы
не отправлять raw hybrid top-k в LLM
не вызывать LLM при refused или clarify
не развивать scripts/09_chat.py как основной runtime
не подключать NeMo Guardrails, LangGraph, Dify/RAGFlow как runtime MVP
не возвращаться к раздуванию OUT_OF_PROJECT_MARKERS
не превращать QH-4 warnings в hard-fail
не внедрять JSON-mode, retry, NLI и LLM-judge до накопления eval dataset
не делать Docker до фактического QH-5 passed
не коммитить Telegram token
не открывать публичный no_guard
не добавлять code/system_export в default source allowlist
