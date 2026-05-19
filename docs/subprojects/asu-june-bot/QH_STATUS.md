# QH Status — Project Knowledge Bot

Обновлено: 2026-05-19.

## Итоговый статус

```text
QH-1 Observability + Eval Baseline        IMPLEMENTED
QH-2 Source Quality Filter                IMPLEMENTED_CODE_READY
QH-3 Parent Expansion                     IMPLEMENTED_CODE_READY
QH-4 Semantic Warnings / Manual Labels    IMPLEMENTED_CODE_READY
QH-5 Release Stabilization                PENDING_LOCAL_VALIDATION
```

Важно: QH-2/QH-3/QH-4 реализованы в коде и подтверждены локальным regression pack 2026-05-18. QH-5 пока нельзя закрывать как `PASSED`, потому что Telegram smoke ещё не выполнен. Для безопасного запуска добавлен `scripts/asu_june_bot_start_telegram.ps1`.

## Локальный прогон 2026-05-18

Выполнено:

```text
health_v2: status=ok, vector_ready=true, bm25_ready=true
regression tests: 97 passed
API smoke: /health ok, /search ok/refused, /chat answered/refused/mixed refused
Web UI HTTP smoke: /ui status_code=200, основные элементы есть
chat_runs.jsonl: пишется
after_qh eval: 7/13, 53.8%
baseline comparison: 6/13 -> 7/13
```

Не выполнено:

```text
Telegram smoke: ожидает локальный запуск через scripts/asu_june_bot_start_telegram.ps1
final QH gate: не запускался, чтобы не пометить QH-5 passed без Telegram smoke
```

Отчёт:

```text
docs/subprojects/asu-june-bot/smoke_report_qh_release.md
```

## QH-1. Observability + Eval Baseline

Статус:

```text
IMPLEMENTED
```

Реализовано:

```text
ChatRunsLogger
chat_runs.jsonl
EvalRunner
eval/cases/base.jsonl
golden answer placeholders
JSON/Markdown eval reports
```

Код:

```text
src/asu_june_bot/observability/chat_runs.py
src/asu_june_bot/eval/
scripts/asu_june_bot_chat_eval.py
```

Первый baseline:

```text
total = 13
passed = 6
failed = 7
pass_rate = 46.2%
```

Интерпретация:

```text
это не провал /chat
часть падений была из-за eval case defects
часть падений — реальные retrieval/context gaps
```

Исправлено после baseline:

```text
source_titles проверяет title/path/section/preview
clarify cases проверяют фактическую формулировку "Сформулируйте"
ProjectGuard получил project markers по логированию
```

## QH-2. Source Quality Filter

Статус:

```text
IMPLEMENTED_CODE_READY
```

Цель:

```text
снизить риск, что короткие UML/heading/caption chunks становятся primary evidence
```

Решение:

```text
не удалять chunks из индекса
не менять raw retrieval
оценивать качество источника в ContextBuilder
слабые источники демотировать из primary в supporting/excluded
оставлять reasons в diagnostics
```

Код:

```text
src/asu_june_bot/retrieval/source_quality.py
src/asu_june_bot/retrieval/context_builder.py
```

Диагностика в ответе:

```text
context.diagnostics.source_quality_filter.enabled
context.diagnostics.source_quality_filter.results.weak_count
context.diagnostics.source_quality_filter.results.weak_reasons
context.diagnostics.source_quality_filter.source_quality_excluded_primary
context.diagnostics.source_quality_filter.primary_fallback_weak
```

Тесты:

```text
tests/asu_june_bot/retrieval/test_source_quality.py
tests/asu_june_bot/retrieval/test_context_builder_qh.py
```

## QH-3. Parent Expansion

Статус:

```text
IMPLEMENTED_CODE_READY
```

Цель:

```text
расширять слабый, но потенциально полезный источник соседним/родительским контекстом
```

Ограничения:

```text
только для weak source
только если соседний/родительский фрагмент уже есть среди кандидатов rerank/excluded
строгий max_parent_chars
без обращения к индексу и без пересборки corpus
```

Код:

```text
src/asu_june_bot/retrieval/parent_expansion.py
src/asu_june_bot/retrieval/context_builder.py
```

Диагностика:

```text
context.diagnostics.parent_expansion.enabled
context.diagnostics.parent_expansion.primary.expanded_count
context.diagnostics.parent_expansion.supporting.expanded_count
source.diagnostics.parent_expansion
```

Тесты:

```text
tests/asu_june_bot/retrieval/test_parent_expansion.py
tests/asu_june_bot/retrieval/test_context_builder_qh.py
```

## QH-4. Semantic Warnings / Manual Labels

Статус:

```text
IMPLEMENTED_CODE_READY
```

Цель:

```text
дать warning-only слой качества без hard-fail semantic validation
```

Решение:

```text
не блокировать answered
добавлять warnings.semantic
dублировать semantic_warnings в diagnostics
логировать semantic_warnings в chat_runs.jsonl
сохранять manual_label/manual_issue для ручной разметки
```

Код:

```text
src/asu_june_bot/chat/semantic_warnings.py
src/asu_june_bot/chat/service.py
src/asu_june_bot/observability/chat_runs.py
```

Warning codes:

```text
weak_sources_present
weak_primary_fallback
parent_expansion_applied
low_source_count
low_citation_coverage
structural_validation_errors
```

Тесты:

```text
tests/asu_june_bot/chat/test_semantic_warnings.py
```

Важно: QH-4 не является factual validator. Он только помечает риск, чтобы не создавать ложное ощущение доказанной семантической корректности.

## QH-5. Release Stabilization

Статус:

```text
PENDING_LOCAL_VALIDATION
```

Почему не PASSED:

```text
локальные тесты, API smoke, Web UI HTTP smoke и after_qh eval выполнены
Telegram smoke не выполнен без локального token/chat id
final gate не запускался без Telegram smoke
```

Код gate:

```text
src/asu_june_bot/qh/release_gate.py
scripts/asu_june_bot_qh_gate.py
```

Проверка статуса:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_qh_gate.py --json
```

Ожидаемо до локальной проверки:

```text
status = pending_local_validation
pending = [QH-5A, QH-5B]
```

После локальных тестов, smoke и сравнения eval:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_qh_gate.py --local-validation-done --baseline-compared --json
```

Ожидаемо:

```text
status = passed
```

## Завтрашний обязательный QH test pack

```powershell
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\chat\test_semantic_warnings.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\retrieval\test_source_quality.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\retrieval\test_parent_expansion.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\retrieval\test_context_builder_qh.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\qh\test_release_gate.py -q
```

## Завтрашний eval после QH

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_chat_eval.py --cases eval\cases\base.jsonl --label after_qh --model qwen2.5:7b-instruct --top-k 5
```

Сравнить:

```text
eval/reports/*__baseline.md
eval/reports/*__after_qh.md
```

Смотреть особенно:

```text
SHORTSRC-AD-001
PROJECT-FTT-425-001
NO-CONTEXT-001
PROJECT-LOGGING-001
```

## Что считать успехом QH перед сдачей

Минимально:

```text
regression tests проходят
API запускается
UI открывается
Telegram отвечает
/chat возвращает answer + sources + warnings.semantic
QH gate показывает pending только по локальному validation/baseline comparison до фактического прогона
```

После фактического прогона:

```text
QH gate может быть отмечен как passed только если local-validation-done и baseline-compared подтверждены
```

## Что не делать

```text
не считать QH-5 passed без локального smoke/eval
не начинать Docker до фактического QH-5 passed
не удалять weak chunks из индекса
не делать parent expansion без лимита
не превращать semantic warnings в hard-fail
не подключать LLM-as-judge/NLI до накопления dataset
```
