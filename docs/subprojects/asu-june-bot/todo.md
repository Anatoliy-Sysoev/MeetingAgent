# TODO Asu June Bot

Обновлено: 2026-05-15.

## Текущий статус

API Search MVP закрыт. CLI Chat MVP технически прошёл первый smoke на локальной LLM.

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
```

Финальные отчёты:

```text
docs/subprojects/asu-june-bot/smoke_report_project_guard_v2.md
docs/subprojects/asu-june-bot/smoke_report_search_service_commit1.md
docs/subprojects/asu-june-bot/smoke_report_api_search_mvp.md
docs/subprojects/asu-june-bot/smoke_report_chat_mvp.md
```

## Подтверждено

### ChatService tests

```text
7 passed
```

Проверено:

```text
refused -> LLM не вызывается
clarify -> LLM не вызывается
ok -> LLM вызывается
LLM получает context, не excluded_sources
пустой ответ LLM != answered
ответ без [Sx] != answered
unknown source reference != answered
context budget diagnostics работают
```

### Project smoke / qwen2.5

Команда:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_chat.py "СоИ AD как происходит авторизация пользователей?" --mode hybrid --top-k 5 --model qwen2.5:7b-instruct --max-tokens 500 --timeout-sec 300 --json --output data\asu_june_bot\smoke_chat_ad_qwen25_7b.json
```

Результат:

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

Вывод:

```text
qwen2.5:7b-instruct — рекомендуемая chat-модель для текущего MVP.
```

### Project smoke / qwen3

Команда:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_chat.py "СоИ AD как происходит авторизация пользователей?" --mode hybrid --top-k 5 --model qwen3:4b --max-tokens 500 --timeout-sec 300 --json --output data\asu_june_bot\smoke_chat_ad_qwen3_4b_nothink.json
```

Результат:

```text
status = llm_empty_response
llm_called = true
llm_model = qwen3:4b
llm_finish_reason = length
```

Вывод:

```text
qwen3:4b даже с /no_think нестабилен для Chat MVP на текущем prompt/max_tokens.
qwen3:8b ранее давал timeout/обрыв на локальном CPU runtime.
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

Для smoke-вопроса по AD модель дала валидный структурно ответ, но часть формулировок по коротким UML-фрагментам `[S2]`, `[S3]` требует ручного ревью. Это фиксируется как quality debt, а не runtime blocker.

## Текущая архитектура Chat MVP

```text
User question
  -> ChatService
  -> SearchService.search()
  -> if refused/clarify/error: return without LLM
  -> if ok: PromptBuilder(context.primary_sources + context.supporting_sources)
  -> context budget / truncation
  -> LLMClient.generate()
  -> AnswerValidator
  -> ChatResponse
```

Ключевое правило сохраняется:

```text
/search возвращает evidence/context
/chat возвращает осмысленный ответ по context
```

## Следующий приоритет

### Commit 8. POST /chat

- [ ] Добавить API route `POST /chat`.
- [ ] Использовать существующий `ChatService`, без дублирования логики.
- [ ] Добавить API tests:
  - [ ] project query -> `answered` на mock LLM;
  - [ ] refused query -> LLM не вызывается;
  - [ ] clarify query -> LLM не вызывается;
  - [ ] empty LLM -> `llm_empty_response`.
- [ ] Добавить PowerShell smoke для `/chat`.
- [ ] Обновить `RUNBOOK_V2.md`.

### Quality hardening после POST /chat

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
