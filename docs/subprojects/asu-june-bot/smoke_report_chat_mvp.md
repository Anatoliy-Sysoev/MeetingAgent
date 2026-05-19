# Smoke report — Chat MVP

Дата: 2026-05-15.

## Назначение проверки

Проверить первый CLI Chat MVP поверх готового `SearchService`:

```text
User question
  -> ChatService
  -> SearchService.search()
  -> PromptBuilder
  -> LLMClient
  -> AnswerValidator
  -> ChatResponse
```

Проверить, что:

- ChatService использует `SearchService`;
- `refused/clarify` не вызывают LLM;
- проектный вопрос вызывает LLM;
- ответ проходит structural validation;
- источники возвращаются в `sources`;
- выбранная локальная модель пригодна для MVP.

## Проверяемые компоненты

```text
src/asu_june_bot/chat/models.py
src/asu_june_bot/chat/service.py
src/asu_june_bot/chat/prompt_builder.py
src/asu_june_bot/chat/answer_validator.py
src/asu_june_bot/chat/response_formatter.py
src/asu_june_bot/llm/client.py
src/asu_june_bot/llm/ollama_openai.py
scripts/asu_june_bot_chat.py
tests/asu_june_bot/chat/test_chat_service.py
```

## Unit tests

Команда:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\chat\test_chat_service.py -q
```

Результат:

```text
7 passed
```

Подтверждено:

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

## Smoke 1. Project question / qwen2.5:7b-instruct

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
qwen2.5:7b-instruct пригодна как базовая chat-модель MVP.
```

Важно: structural validation пройдена, но semantic groundedness пока не гарантируется. В ответе модель использовала источники `[S1]..[S4]`, однако часть формулировок требует ручного ревью на смысловую точность, особенно выводы по коротким UML-фрагментам `[S2]`, `[S3]`.

## Smoke 2. Project question / qwen3:4b + /no_think

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
prompt_sources = 5
selected_sources = 5
used_context_chars = 1162
```

Вывод:

```text
qwen3:4b даже с /no_think нестабилен для Chat MVP на текущем prompt/timeout/max_tokens.
```

Не считать это ошибкой retrieval: поиск и prompt context отработали корректно. Проблема находится в visible answer generation модели.

## Model decision

Для Chat MVP зафиксировать рекомендуемую модель:

```text
qwen2.5:7b-instruct
```

Не использовать как default для MVP:

```text
qwen3:4b
qwen3:8b
```

Причины:

```text
qwen3:4b -> llm_empty_response / finish_reason=length
qwen3:8b -> timeout/обрыв на локальном CPU runtime
```

## Качество источников

Для вопроса по СоИ AD SearchService вернул:

```text
primary_sources = 4
supporting_sources = 1
excluded_sources = 8
```

Primary context включает:

```text
[S1] Паспорт ИС, раздел 5.2 — централизованная аутентификация через Active Directory и Blitz IDP, группы безопасности AD для авторизации.
[S2] ЦТА, UML fragment — AD --> CCPM: Авторизация успешная.
[S3] ЦТА, UML fragment — CCPM -> AD: Авторизация (логин, пароль ...).
[S4] ЦТА — ежедневное обновление перечня пользователей с присвоенными/отозванными группами AD, сохранение учетных данных в БД, блокировка УЗ без групп AD.
[S5] ЦТА — заголовочный/поддерживающий фрагмент "Загрузка информации о пользователях AD".
```

Замечание:

```text
Короткие UML/heading chunks могут попадать в primary/supporting и усиливать риск спорных выводов модели.
```

Это не блокирует Chat MVP, но должно попасть в следующий этап hardening:

```text
source quality filter
parent expansion для коротких chunks
semantic answer review / eval dataset
```

## Статус Chat MVP

Технический статус:

```text
PASSED_WITH_NOTES
```

Подтверждено:

- unit tests ChatService проходят;
- проектный вопрос даёт `answered` на `qwen2.5:7b-instruct`;
- ответ содержит citations `[Sx]`;
- structural validator проходит;
- qwen3 нестабилен для текущего Chat MVP;
- retrieval/context работают, проблема qwen3 находится в LLM generation.

## Ограничения результата

Structural validation не равна factual validation.

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

Но пока не проверяет:

```text
поддерживается ли каждое утверждение конкретным source text;
не сделала ли модель спорный вывод из короткого UML-фрагмента;
нет ли semantic hallucination при формально правильных ссылках.
```

## Следующие действия

### Ближайший технический шаг

Добавить API endpoint:

```text
POST /chat
```

Использовать тот же `ChatService`, без дублирования логики.

### Ближайший quality шаг

Добавить chat eval dataset и smoke cases:

```text
tests/asu_june_bot/chat_eval_cases.jsonl
scripts/asu_june_bot_chat_eval.py
```

Минимальный набор:

```text
СоИ AD как происходит авторизация пользователей?
Какие интеграции заявлены в проекте?
Что входит в Паспорт ИС?
ФТТ 4.2.5 НОВАДОК ЭЦП
Какие требования ИБ описаны?
Какая погода завтра в Москве? -> refused
Расскажи подробнее -> clarify
```

### Quality hardening later

- source quality filter для слишком коротких chunks;
- parent expansion для заголовков/диаграмм;
- ручная разметка ответов good/bad;
- no_answer status;
- optional JSON-mode lab;
- optional DSPy lab;
- groundedness/NLI только после накопления eval dataset.
