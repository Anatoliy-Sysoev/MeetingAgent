# Chat MVP Design

Обновлено: 2026-05-15.

## Назначение

Chat MVP добавляет осмысленный project-only ответ поверх уже готового API/Search MVP.

`/search` возвращает evidence/context. `/chat` и CLI chat должны возвращать связный текстовый ответ с источниками.

## Главный принцип

```text
ChatService не дублирует guard/retrieval/rerank/context.
ChatService использует SearchService.
```

Запрещено отправлять в LLM сырой hybrid top-k.

В LLM передается только подготовленный `ContextBuilder` context:

```text
context.primary_sources
context.supporting_sources
```

## Pipeline

```text
User question
  -> ChatService
  -> SearchService.search()
  -> if refused/clarify: return without LLM
  -> if ok: build prompt from context
  -> LLMClient.generate()
  -> AnswerValidator
  -> ResponseFormatter
  -> ChatResponse
```

## Статусы ChatResponse

```text
answered
refused
clarify
no_sources
llm_error
llm_empty_response
validation_failed
```

## Правила вызова LLM

LLM не вызывается, если SearchService вернул:

```text
refused
clarify
error
```

LLM не вызывается, если отсутствуют:

```text
context.primary_sources
context.supporting_sources
```

## Prompt contract

PromptBuilder должен передать модели:

- роль: проектный ассистент системного аналитика ЦП УПКС;
- запрет использовать знания вне контекста;
- запрет выдумывать факты;
- требование отвечать на русском языке;
- требование ссылаться на источники из context;
- требование явно писать, если данных недостаточно;
- список источников с `source_ref`;
- пользовательский вопрос.

## Citation contract

Каждый источник в prompt получает стабильный `source_ref`:

```text
[S1]
[S2]
[S3]
```

В ответе модель должна использовать ссылки вида:

```text
[S1]
[S2]
```

В `ChatResponse.sources` возвращается соответствие `source_ref -> metadata`.

## Формат ответа

Рекомендуемый формат ответа:

```text
Краткий ответ
<ответ по существу>

Обоснование
<2-5 пунктов с источниками>

Источники
[S1] <документ / раздел / chunk_id>
[S2] <документ / раздел / chunk_id>
```

## AnswerValidator MVP

MVP-валидация должна проверять:

- ответ не пустой;
- при `answered` есть sources;
- при `answered` в тексте есть хотя бы одна ссылка `[S1]` или аналогичная;
- нельзя возвращать `answered`, если SearchService status не `ok`;
- нельзя возвращать `answered`, если LLM вернул пустой ответ.

Если валидация не пройдена:

```text
status = validation_failed
```

## LLM provider MVP

Для локального запуска используется Ollama OpenAI-compatible endpoint:

```text
base_url = http://127.0.0.1:11434/v1
model = qwen3:8b или другая локальная модель
```

Если локальная модель медленная, можно тестировать на меньшей модели, но качество smoke фиксировать отдельно.

## CLI MVP

Команда:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_chat.py "СоИ AD как происходит авторизация пользователей?" --mode hybrid --top-k 8
```

JSON:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_chat.py "СоИ AD как происходит авторизация пользователей?" --mode hybrid --top-k 8 --json --output data\asu_june_bot\smoke_chat_ad.json
```

## API /chat

`POST /chat` не входит в первый кодовый commit Chat MVP.

Сначала реализуется CLI Chat MVP. После smoke добавляется API endpoint.

## Definition of Done

- `ChatService` создан.
- `ChatService` использует `SearchService`.
- Для `refused/clarify` LLM не вызывается.
- Для `ok` LLM получает только context, не raw top-k.
- CLI chat работает.
- Ответ содержит текст и источники.
- Ответ без sources не получает статус `answered`.
- Пустой ответ LLM не получает статус `answered`.
- Создан smoke report Chat MVP.
