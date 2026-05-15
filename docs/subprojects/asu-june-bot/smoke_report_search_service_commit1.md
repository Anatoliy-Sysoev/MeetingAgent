# Smoke report — SearchService Commit 1

Дата: 2026-05-15.

## Назначение проверки

Проверить, что Commit 1 API Search MVP выполнен корректно:

```text
SearchService = единственная orchestration-точка
CLI search_v2 = thin wrapper
ProjectGuard v2 не сломан
refused/clarify не вызывают retrieval
project query вызывает retrieval
```

## Проверяемые компоненты

```text
src/asu_june_bot/search/__init__.py
src/asu_june_bot/search/models.py
src/asu_june_bot/search/service.py
scripts/asu_june_bot_search_v2.py
tests/asu_june_bot/search/test_search_service.py
tests/asu_june_bot/test_project_guard_v2.py
tests/asu_june_bot/test_project_guard_v2_cases.py
```

## Выполненные команды

### SearchService unit tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\search\test_search_service.py -q
```

Результат:

```text
4 passed
```

### ProjectGuard v2 base tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\test_project_guard_v2.py -q
```

Результат:

```text
8 passed
```

### ProjectGuard v2 regression cases

```powershell
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\test_project_guard_v2_cases.py -q
```

Результат:

```text
44 passed
```

### Refused smoke через CLI search_v2

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Какая погода завтра в Москве?" --mode hybrid --top-k 8 --json --output data\asu_june_bot\smoke_service_refused_weather.json
```

Проверка:

```powershell
Get-Content data\asu_june_bot\smoke_service_refused_weather.json -Encoding UTF8 | Select-String '"status"|"retrieval_called"|"results"'
```

Результат:

```text
"status": "refused"
"results": []
"retrieval_called": false
```

### Project smoke через CLI search_v2

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "СоИ AD как происходит авторизация пользователей?" --mode hybrid --top-k 8 --json --output data\asu_june_bot\smoke_service_project_ad.json
```

Проверка:

```powershell
Get-Content data\asu_june_bot\smoke_service_project_ad.json -Encoding UTF8 | Select-String '"status"|"retrieval_called"|"primary_sources"|"results"'
```

Результат:

```text
"status": "ok"
"primary_sources": [
"results": [
"retrieval_called": true
```

## Вывод

Commit 1 пройден.

Статус:

```text
PASSED
```

Подтверждено:

- `SearchService` создан и импортируется;
- CLI `scripts/asu_june_bot_search_v2.py` работает через `SearchService`;
- unit tests SearchService проходят;
- ProjectGuard v2 tests не сломаны;
- ProjectGuard v2 regression suite не сломан;
- внепроектный запрос получает `status=refused`;
- для refused-запроса `retrieval_called=false`;
- project-запрос получает `status=ok`;
- для project-запроса `retrieval_called=true`;
- `primary_sources` и `results` присутствуют для project-запроса.

## Решение

Можно переходить к Commit 2 API Search MVP:

```text
FastAPI skeleton
GET /health
POST /search
```

Следующие файлы:

```text
src/asu_june_bot/api/__init__.py
src/asu_june_bot/api/app.py
src/asu_june_bot/api/dependencies.py
src/asu_june_bot/api/errors.py
src/asu_june_bot/api/middleware.py
src/asu_june_bot/api/routes_health.py
src/asu_june_bot/api/routes_search.py
scripts/asu_june_bot_api.py
```
