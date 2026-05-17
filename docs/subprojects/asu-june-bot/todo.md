# TODO Project Knowledge Bot

Обновлено: 2026-05-16.

## Текущий статус

API Search MVP закрыт. CLI Chat MVP и API Chat MVP прошли smoke. Добавлены локальный Web UI, Telegram adapter и единый лимит длины запроса.

QH-этапы доведены до состояния:

```text
QH-1 Observability + Eval Baseline        IMPLEMENTED
QH-2 Source Quality Filter                IMPLEMENTED_CODE_READY
QH-3 Parent Expansion                     IMPLEMENTED_CODE_READY
QH-4 Semantic Warnings / Manual Labels    IMPLEMENTED_CODE_READY
QH-5 Release Stabilization                PENDING_LOCAL_VALIDATION
```

Главный документ статуса QH:

```text
docs/subprojects/asu-june-bot/QH_STATUS.md
```

Важно: QH-2/QH-3/QH-4 реализованы через GitHub и покрыты тестами, но фактический статус `PASSED` должен быть подтвержден завтра на рабочем ПК локальным прогоном тестов, API smoke, UI/Telegram smoke и eval after_qh.

Принято решение: Docker-упаковка выполняется **после фактического QH-5 passed**, а не сейчас.

## Для завтрашнего восстановления

Главный чек-лист:

```text
docs/subprojects/asu-june-bot/TOMORROW_START.md
```

Порядок:

```text
git pull
health
tests
QH gate
API
Web UI
Telegram adapter
manual smoke
eval after_qh
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
```

## Закрыто сегодня через GitHub

```text
MAX_QUERY_CHARS = 2000
ChatRequest query length validation
SearchRequest query length validation
POST /chat max_length validation
POST /search max_length validation
Local Web UI: GET / and GET /ui
Telegram adapter: src/asu_june_bot/telegram_bot.py
Telegram script: scripts/asu_june_bot_telegram.py
QH-2 Source Quality Filter: src/asu_june_bot/retrieval/source_quality.py
QH-3 Parent Expansion: src/asu_june_bot/retrieval/parent_expansion.py
QH-4 Semantic Warnings: src/asu_june_bot/chat/semantic_warnings.py
QH-4 logging semantic_warnings в chat_runs.jsonl
QH-5 release gate: src/asu_june_bot/qh/release_gate.py
QH-5 CLI: scripts/asu_june_bot_qh_gate.py
TOMORROW_START.md
QH_STATUS.md
telegram.md
README.md обновлен
RUNBOOK_V2.md обновлен
```

## Ожидаемые тесты завтра

```powershell
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\chat\test_chat_service.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\chat\test_semantic_warnings.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\api\test_health.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\api\test_search_smoke.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\api\test_chat_smoke.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\retrieval\test_source_quality.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\retrieval\test_parent_expansion.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\retrieval\test_context_builder_qh.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\observability\test_chat_runs.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\eval\test_checks.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\eval\test_runner.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\qh\test_release_gate.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\test_project_guard_v2_cases.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\test_telegram_bot.py -q
```

Ожидаемо после последних изменений:

```text
ChatService: 7 passed
Semantic warnings: 3 passed
API health: 1 passed
API search: 4 passed
API chat: 7 passed
Source quality: 3 passed
Parent expansion: 2 passed
ContextBuilder QH: 2 passed
observability: 2 passed
eval checks: 3 passed
eval runner: 1 passed
QH release gate: 2 passed
ProjectGuard cases: 46 passed
Telegram formatter: 4 passed
```

Фактический результат надо подтвердить завтра локальным прогоном.

## Завтрашний smoke для сдачи

### QH gate

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_qh_gate.py --json
```

До локального smoke/eval ожидаемо:

```text
status = pending_local_validation
pending = [QH-5A, QH-5B]
```

После локального regression/smoke и сравнения eval:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_qh_gate.py --local-validation-done --baseline-compared --json
```

### API + UI

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_api.py --host 127.0.0.1 --port 8000
```

Открыть:

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/ui
```

### Telegram

```powershell
$env:ASU_JUNE_BOT_TELEGRAM_TOKEN='PASTE_TOKEN_HERE'
$env:ASU_JUNE_BOT_CHAT_API_URL='http://127.0.0.1:8000/chat'
.\.venv\Scripts\python.exe scripts\asu_june_bot_telegram.py
```

Рекомендуется ограничить доступ:

```powershell
$env:ASU_JUNE_BOT_ALLOWED_CHAT_IDS='123456789'
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

Уже исправлено:

```text
source_titles ищет не только в title, но и path/section/preview
clarify cases проверяют фактическую формулировку "Сформулируйте"
ProjectGuard получил project markers для логирования/Grafana Loki/журналирования
```

Повторный eval после QH:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_chat_eval.py --cases eval\cases\base.jsonl --label after_qh --model qwen2.5:7b-instruct --top-k 5
```

Сравнить:

```text
eval/reports/*__baseline.md
eval/reports/*__after_qh.md
```

## Что дальше после локального QH-5 passed

Если завтра тесты, API smoke, UI smoke, Telegram smoke и after_qh eval прошли приемлемо:

```text
1. Зафиксировать smoke_report_qh_release.md.
2. Обновить QH_STATUS.md: QH-5 -> PASSED.
3. После этого можно начинать Docker stage.
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
