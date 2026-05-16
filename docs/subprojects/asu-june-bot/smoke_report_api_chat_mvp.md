# Smoke report — API Chat MVP

Дата: 2026-05-16.

## Назначение проверки

Проверить реализацию `POST /chat` как thin API adapter над существующим `ChatService`.

Цель: не дублировать guard/retrieval/context/generation logic в API-слое.

## Реализованные компоненты

```text
src/asu_june_bot/api/routes_chat.py
src/asu_june_bot/api/dependencies.py
src/asu_june_bot/api/app.py
tests/asu_june_bot/api/test_chat_smoke.py
```

## Архитектурное правило

```text
POST /chat
  -> ChatApiRequest
  -> get_chat_service()
  -> ChatService.chat()
  -> ChatResponse.to_dict()
```

API route не реализует самостоятельно:

```text
guard
retrieval
rerank
context building
prompt building
LLM call
answer validation
response formatting
```

Вся бизнес-логика остаётся в:

```text
src/asu_june_bot/chat/service.py
```

## AppState

`AppState` теперь содержит:

```text
config
search_service
health_service
chat_service
```

`ChatService` использует тот же `SearchService`, что и `/search`.

LLM client по умолчанию:

```text
OllamaOpenAIClient
base_url = http://127.0.0.1:11434/v1
model = qwen2.5:7b-instruct
```

Значения могут быть переопределены через `config.yaml` секцию:

```yaml
ollama:
  chat_base_url: "http://127.0.0.1:11434/v1"
  chat_model: "qwen2.5:7b-instruct"
```

## API contract

Endpoint:

```text
POST /chat
```

Request fields:

```text
query: string, required
mode: hybrid | vector | bm25, default hybrid
top_k: integer, 1..50, default 8
include_source_types: list[string] | null
model: string | null
temperature: float, 0.0..2.0, default 0.0
max_tokens: integer, 1..4096, default 900
timeout_sec: integer, 1..1800, default 300
include_diagnostics: bool, default true
```

Response shape is `ChatResponse.to_dict()`:

```text
status
query
answer
sources
search
warnings
diagnostics
```

`request_id` добавляется в:

```text
diagnostics.request_id
```

и возвращается в HTTP header:

```text
X-Request-Id
```

## Unit/API tests

Добавлен файл:

```text
tests/asu_june_bot/api/test_chat_smoke.py
```

Покрытие:

```text
project query -> answered на fake ChatService
refused query -> llm_called=false
clarify query -> llm_called=false
empty LLM -> llm_empty_response
unknown field -> HTTP 422 validation_error
```

Команда локальной проверки:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\api\test_chat_smoke.py -q
```

Ожидаемо:

```text
5 passed
```

## Full local regression

Рекомендуемый набор после pull:

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

## Runtime smoke через FastAPI

Запуск API:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_api.py --host 127.0.0.1 --port 8000
```

### Project chat request

Команда:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/chat" `
  -ContentType "application/json" `
  -Body '{"query":"СоИ AD как происходит авторизация пользователей?","mode":"hybrid","top_k":5,"model":"qwen2.5:7b-instruct","max_tokens":500,"timeout_sec":300}'
```

Фактический результат локального runtime smoke:

```text
status = answered
query = СоИ AD как происходит авторизация пользователей?
answer != null
sources != []
search.status = ok
diagnostics.llm_called = true
diagnostics.search_status = ok
diagnostics.prompt_sources = 5
diagnostics.llm_model = qwen2.5:7b-instruct
diagnostics.llm_finish_reason = stop
diagnostics.validation_errors = []
```

### Out-of-project chat request

Команда:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/chat" `
  -ContentType "application/json" `
  -Body '{"query":"Какая погода завтра в Москве?","mode":"hybrid","top_k":5,"model":"qwen2.5:7b-instruct","max_tokens":500,"timeout_sec":300}'
```

Фактический результат локального runtime smoke:

```text
status = refused
query = Какая погода завтра в Москве?
answer = Я отвечаю только по материалам проекта ЦП УПКС. Вопрос не относится к проектной базе знаний.
sources = []
search.status = refused
diagnostics.llm_called = false
diagnostics.search_status = refused
```

## Примечание по PowerShell

Первая попытка project chat smoke упала из-за склеенной команды:

```text
-Body '{...}'с(Set-ExecutionPolicy ...)
```

PowerShell воспринял лишний символ `с` и следующую команду как позиционный аргумент `Invoke-RestMethod`.

Это не ошибка API и не ошибка `/chat`.

## Статус

Кодовый и runtime статус:

```text
PASSED_WITH_NOTES
```

Подтверждено:

```text
POST /chat route работает
project query -> answered
out-of-project query -> refused
refused -> LLM не вызывается
request_id возвращается в diagnostics
qwen2.5:7b-instruct пригодна как chat-модель MVP
```

## Ограничения

`POST /chat`, как и CLI Chat MVP, использует structural validation. Semantic/factual validation пока не реализована.

Quality debt остаётся прежним:

```text
short UML/heading chunks могут приводить к спорным обобщениям;
нужны chat eval cases;
нужна ручная разметка good/bad;
нужен source quality filter / parent expansion.
```
