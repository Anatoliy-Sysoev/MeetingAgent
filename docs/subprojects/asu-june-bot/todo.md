# TODO Asu June Bot

Обновлено: 2026-05-15.

## Текущий статус

API Search MVP закрыт. CLI Chat MVP прошёл первый smoke на локальной LLM. API Chat MVP реализован в коде и ожидает локальную проверку.

Завершено:

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
```

Финальные/рабочие отчёты:

```text
docs/subprojects/asu-june-bot/smoke_report_project_guard_v2.md
docs/subprojects/asu-june-bot/smoke_report_search_service_commit1.md
docs/subprojects/asu-june-bot/smoke_report_api_search_mvp.md
docs/subprojects/asu-june-bot/smoke_report_chat_mvp.md
docs/subprojects/asu-june-bot/smoke_report_api_chat_mvp.md
```

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

## Реализовано для POST /chat

```text
src/asu_june_bot/api/routes_chat.py
src/asu_june_bot/api/dependencies.py
src/asu_june_bot/api/app.py
tests/asu_june_bot/api/test_chat_smoke.py
```

`POST /chat` является thin API adapter над `ChatService`.

Не дублирует:

```text
guard
retrieval
rerank
context building
prompt building
LLM call
answer validation
```

## Следующий локальный прогон

```powershell
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\chat\test_chat_service.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\api\test_health.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\api\test_search_smoke.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\api\test_chat_smoke.py -q
```

Ожидаемо:

```text
ChatService: 7 passed
API health: 1 passed
API search: 3 passed
API chat: 5 passed
```

Runtime smoke `/chat`:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_api.py --host 127.0.0.1 --port 8000
```

В другом PowerShell:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/chat" `
  -ContentType "application/json" `
  -Body '{"query":"СоИ AD как происходит авторизация пользователей?","mode":"hybrid","top_k":5,"model":"qwen2.5:7b-instruct","max_tokens":500,"timeout_sec":300}'
```

Ожидаемо:

```text
status = answered
sources != []
diagnostics.llm_called = true
```

Refused smoke:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/chat" `
  -ContentType "application/json" `
  -Body '{"query":"Какая погода завтра в Москве?","mode":"hybrid","top_k":5,"model":"qwen2.5:7b-instruct","max_tokens":500,"timeout_sec":300}'
```

Ожидаемо:

```text
status = refused
diagnostics.llm_called = false
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

## Следующий приоритет после проверки POST /chat

### Quality hardening

- [ ] Добавить source quality filter для слишком коротких chunks.
- [ ] Добавить parent expansion для heading/UML/caption chunks.
- [ ] Добавить `tests/asu_june_bot/chat_eval_cases.jsonl`.
- [ ] Добавить `scripts/asu_june_bot_chat_eval.py`.
- [ ] Добавить `chat_runs.jsonl` для накопления dataset.
- [ ] Добавить ручную разметку good/bad для ответов.
- [ ] Рассмотреть `NO_ANSWER` status.
- [ ] Рассмотреть DSPy Lab только как research/lab, не runtime MVP.

## Не делать сейчас

- Не пытаться заставить `/search` писать осмысленные ответы.
- Не отправлять raw hybrid top-k в LLM.
- Не вызывать LLM при `refused` или `clarify`.
- Не развивать `scripts/09_chat.py` как основной runtime.
- Не подключать UI до стабильного `POST /chat`.
- Не подключать NeMo Guardrails, LangGraph, Dify/RAGFlow как runtime MVP.
- Не возвращаться к раздуванию `OUT_OF_PROJECT_MARKERS`.
- Не внедрять JSON-mode, retry, NLI и LLM-judge до накопления eval dataset.
