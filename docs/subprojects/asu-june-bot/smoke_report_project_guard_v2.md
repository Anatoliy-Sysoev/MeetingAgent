# Smoke report — ProjectGuard v2

Дата: 2026-05-15.

## Назначение проверки

Проверить, что ProjectGuard v2 корректно блокирует внепроектные, mixed-scope, offensive/security и prompt-injection запросы до запуска retrieval.

Критический критерий:

```text
false_allow = 0
```

Для project-only бота это важнее общего количества ошибок: небезопасный или внепроектный запрос не должен уходить в retrieval/LLM.

## Проверяемые компоненты

```text
src/asu_june_bot/guardrails/models.py
src/asu_june_bot/guardrails/segmenter.py
src/asu_june_bot/guardrails/scope_classifier.py
src/asu_june_bot/guardrails/aggregator.py
src/asu_june_bot/guardrails/policy.py
src/asu_june_bot/guardrails/project_guard.py
scripts/asu_june_bot_guard_v2_eval.py
tests/asu_june_bot/test_project_guard_v2.py
tests/asu_june_bot/test_project_guard_v2_cases.py
tests/asu_june_bot/guard_v2_cases.jsonl
```

## Команды проверки

```powershell
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\test_project_guard_v2.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\test_project_guard_v2_cases.py -q
.\.venv\Scripts\python.exe scripts\asu_june_bot_guard_v2_eval.py --print-failed --fail-on-error
```

## Финальный результат

```json
{
  "total": 44,
  "passed": 44,
  "failed": 0,
  "false_allow": 0,
  "false_refuse": 0,
  "false_clarify": 0,
  "failed_ids": [],
  "false_allow_ids": [],
  "false_refuse_ids": [],
  "false_clarify_ids": []
}
```

## Вывод

ProjectGuard v2 regression suite пройден полностью.

Статус:

```text
PASSED
```

Решение:

```text
ProjectGuard v2 можно использовать как pre-retrieval guard для API Search MVP.
```

## Что подтверждено

- Pure project-запросы получают `allow`.
- Pure out-of-project запросы получают `refuse`.
- Mixed-scope запросы получают `refuse`.
- Offensive/security запросы получают `refuse`.
- Prompt-injection/jailbreak запросы получают `refuse`.
- Ambiguous запросы получают `clarify`.
- `false_allow = 0`.

## Следующий шаг

Переход к API Search MVP:

```text
src/asu_june_bot/api/app.py
src/asu_june_bot/api/routes_search.py
```

Минимальные endpoints:

```text
GET /health
POST /search
```

API `/search` должен использовать текущий pipeline:

```text
Query -> QueryIntent -> ProjectGuard v2 -> Retrieval -> PostReranker -> ContextBuilder -> JSON response
```

При `refuse` или `clarify` retrieval не должен вызываться.
