# TODO Asu June Bot

Обновлено: 2026-05-16.

## Текущий статус

API Search MVP закрыт. CLI Chat MVP и API Chat MVP прошли smoke. Начат этап **QH-1 Observability + Eval Baseline** без изменения поведения `/chat`.

Завершено ранее:

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
```

Реализовано в QH-1:

```text
src/asu_june_bot/observability/chat_runs.py
src/asu_june_bot/observability/__init__.py
src/asu_june_bot/eval/models.py
src/asu_june_bot/eval/checks.py
src/asu_june_bot/eval/runner.py
src/asu_june_bot/eval/report.py
src/asu_june_bot/eval/loader.py
src/asu_june_bot/eval/__init__.py
scripts/asu_june_bot_chat_eval.py
eval/cases/base.jsonl
eval/golden_answers/*.md
tests/asu_june_bot/observability/test_chat_runs.py
tests/asu_june_bot/eval/test_checks.py
tests/asu_june_bot/eval/test_runner.py
```

QH-1 принципиально не включает:

```text
source quality filter
parent expansion
LLM-as-judge
NLI / groundedness model
DSPy runtime
JSON-mode
retry policy
```

Причина: сначала нужен baseline качества текущего `/chat`, затем изменения контекста должны измеряться относительно baseline.

## Подтверждено ранее

### ChatService tests

```text
7 passed
```

### Project smoke / qwen2.5

```text
status = answered
llm_called = true
llm_model = qwen2.5:7b-instruct
llm_finish_reason = stop
validation_errors = []
prompt_sources = 5
selected_sources = 5
used_context_chars = 1162
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

## Следующий локальный прогон

### Regression

```powershell
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\chat\test_chat_service.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\api\test_health.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\api\test_search_smoke.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\api\test_chat_smoke.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\observability\test_chat_runs.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\eval\test_checks.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\eval\test_runner.py -q
```

Ожидаемо:

```text
ChatService: 7 passed
API health: 1 passed
API search: 3 passed
API chat: 5 passed
observability: 2 passed
eval checks: 2 passed
eval runner: 1 passed
```

### CLI chat log smoke

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_chat.py "СоИ AD как происходит авторизация пользователей?" --mode hybrid --top-k 5 --model qwen2.5:7b-instruct --max-tokens 500 --timeout-sec 300 --json --output data\asu_june_bot\smoke_chat_log_ad.json

Get-Content data\asu_june_bot\chat_runs.jsonl -Encoding UTF8 -Tail 1
```

Ожидаемо:

```text
chat_runs.jsonl содержит валидный JSONL
status = answered
llm_called = true
latency_ms != null
sources != []
```

### Eval baseline

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_chat_eval.py --cases eval\cases\base.jsonl --label baseline --model qwen2.5:7b-instruct --top-k 5
```

Ожидаемо:

```text
создан eval/reports/*__baseline.json
создан eval/reports/*__baseline.md
выведены total/passed/failed/pass_rate
```

Важно: baseline может быть ниже 100%. Это нормально. Цель QH-1 — измерить текущее качество, а не подогнать кейсы под прохождение.

## Что смотреть после baseline

- Есть ли failures в `short_source_trap`.
- Есть ли false_allow в `out_of_scope` / `mixed_scope`.
- Есть ли false_refuse в `project_question`.
- Падает ли `NO-CONTEXT-001` из-за выдуманного SLA.
- Какие `expected_source_title_contains` слишком жёсткие или требуют корректировки по реальным названиям документов.

## Следующий приоритет после QH-1 baseline

### QH-2. Source Quality Filter

Делать только после анализа baseline.

План:

```text
src/asu_june_bot/retrieval/source_quality.py
unit tests для weak chunks
интеграция в ContextBuilder
повторный eval: label=with_source_filter
сравнение с baseline
```

Принцип:

```text
не удалять короткие chunks из индекса;
не ломать retrieval;
помечать / понижать weak chunks в context stage;
фиксировать reason в diagnostics.
```

### QH-3. Parent Expansion

Делать только если QH-2 не устранил проблему коротких chunks.

Принцип:

```text
строгий max chars;
dedup parent context;
никакого расширения без лимита;
сравнение eval до/после.
```

## Важное ограничение результата

Chat MVP smoke прошёл как structural validation, но не как полноценная semantic/factual validation.

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

Он не проверяет:

```text
поддерживается ли каждое утверждение конкретным source text;
не делает ли модель спорный вывод из короткого UML/heading chunk;
нет ли semantic hallucination при формально корректных [Sx].
```

Это фиксируется как quality debt, а не runtime blocker.

## Не делать сейчас

- Не пытаться заставить `/search` писать осмысленные ответы.
- Не отправлять raw hybrid top-k в LLM.
- Не вызывать LLM при `refused` или `clarify`.
- Не развивать `scripts/09_chat.py` как основной runtime.
- Не подключать UI до baseline eval.
- Не подключать NeMo Guardrails, LangGraph, Dify/RAGFlow как runtime MVP.
- Не возвращаться к раздуванию `OUT_OF_PROJECT_MARKERS`.
- Не внедрять JSON-mode, retry, NLI и LLM-judge до накопления eval dataset.
- Не внедрять source quality filter без baseline.
- Не внедрять parent expansion без замера эффекта source quality filter.
