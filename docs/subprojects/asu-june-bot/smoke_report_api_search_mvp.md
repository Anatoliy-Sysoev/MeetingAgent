# Smoke report — API Search MVP

Дата: 2026-05-15.

## Назначение проверки

Проверить Commit 2 FastAPI skeleton и базовую работоспособность API Search MVP:

```text
GET /health
POST /search
```

Проверить, что API использует `SearchService`, а guard-отказы не запускают retrieval.

## Проверяемые компоненты

```text
src/asu_june_bot/health/service.py
src/asu_june_bot/api/app.py
src/asu_june_bot/api/dependencies.py
src/asu_june_bot/api/errors.py
src/asu_june_bot/api/middleware.py
src/asu_june_bot/api/routes_health.py
src/asu_june_bot/api/routes_search.py
scripts/asu_june_bot_api.py
tests/asu_june_bot/api/test_health.py
tests/asu_june_bot/api/test_search_smoke.py
src/asu_june_bot/guardrails/policy.py
src/asu_june_bot/guardrails/scope_classifier.py
tests/asu_june_bot/guard_v2_cases.jsonl
```

## Важное архитектурное уточнение

Во время API smoke был обнаружен пограничный запрос:

```text
СоИ AD как происходит авторизация пользователей? И расскажи стих про проект
```

Первичная быстрая правка через добавление creative/chitchat markers в `OUT_OF_PROJECT_MARKERS` была признана неправильной, так как возвращала проект к бесконечному расширению словаря тем.

Итоговое решение:

```text
не расширять marker DB частными темами;
перенести обработку project + unknown tail на уровень GuardPolicy.
```

Текущее policy-level правило:

```text
pure ambiguous -> clarify
pure project -> allow
project + explicit out-of-project -> refused / mixed
project + unknown extra segment -> refused / in_project_query_contains_unclassified_segment
```

Это защищает retrieval без раздувания базы маркеров.

## Выполненные команды

### API tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\api\test_health.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\api\test_search_smoke.py -q
```

Результат:

```text
test_health.py: 1 passed
test_search_smoke.py: 3 passed
```

### Guard regression

```powershell
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\test_project_guard_v2_cases.py -q
```

Результат:

```text
45 passed
```

### Запуск API

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_api.py --host 127.0.0.1 --port 8000
```

Результат:

```text
Application startup complete
Uvicorn running on http://127.0.0.1:8000
```

## Smoke: in-project + unknown tail

Команда:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/search" `
  -ContentType "application/json" `
  -Body '{"query":"СоИ AD как происходит авторизация пользователей? И расскажи стих про проект","mode":"hybrid","top_k":8}'
```

Результат:

```text
status = refused
guard.reason = in_project_query_contains_unclassified_segment
results = []
context.primary_sources = []
context.supporting_sources = []
context.excluded_sources = []
```

Сообщение отказа:

```text
Запрос содержит проектную часть и дополнительную часть, которую нельзя надежно отнести к документации ЦП УПКС. Я не запускаю поиск по смешанному или неоднозначному запросу. Оставьте только вопрос по документу, модулю, требованию, интеграции или разделу проекта.
```

## Smoke: expected API semantics

Ожидаемая семантика API Search MVP подтверждена:

```text
project query -> status=ok, retrieval_called=true
out-of-project query -> status=refused, retrieval_called=false
project + unknown tail -> status=refused, retrieval_called=false
ambiguous query -> status=clarify, retrieval_called=false
```

## Вывод

Commit 2 FastAPI skeleton пройден.

Статус:

```text
PASSED
```

Подтверждено:

- FastAPI app запускается;
- `GET /health` реализован;
- `POST /search` реализован;
- API вызывает `SearchService`, а не дублирует search-логику;
- request id middleware работает;
- validation/error handlers подключены;
- API tests проходят;
- guard regression проходит;
- policy-level защита для `project + unknown tail` работает без расширения topic marker DB.

## Следующее решение

Можно закрывать API Search MVP как базово работающий и переходить к следующему этапу после обновления runbook/docs:

```text
Commit 3. API smoke + docs
```

После Commit 3 следующий крупный этап:

```text
Chat MVP
```
