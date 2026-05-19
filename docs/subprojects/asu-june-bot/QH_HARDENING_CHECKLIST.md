# QH Hardening Checklist

Обновлено: 2026-05-18.

## 1. Назначение

Документ фиксирует дополнительные проверки после ревью Claude и ручного UI smoke.

Использовать вместе с:

```text
docs/subprojects/asu-june-bot/TOMORROW_EXECUTION_PROTOCOL.md
docs/subprojects/asu-june-bot/TOMORROW_START.md
docs/subprojects/asu-june-bot/QH_STATUS.md
docs/subprojects/asu-june-bot/FTT_STATUS.md
```

Этот файл не заменяет основной протокол. Он добавляет проверки новых фиксов:

```text
no_answer status
search_error status
закрытие публичного no_guard
safe include_source_types allowlist
sanitized internal API errors
короткие project queries: Паспорт ИС / Протокол ПСИ / сценарии ПМИ
```

## 2. Что было исправлено

### 2.1 UI f-string

Проблема:

```text
routes_ui.py содержал JavaScript '{}', который ломал Python f-string
```

Исправление:

```text
diagnostics.textContent = '{{}}';
```

### 2.2 no_answer вместо validation_failed

Проблема:

```text
LLM честно отвечала 'В переданных источниках данных недостаточно для ответа', но AnswerValidator переводил это в validation_failed
```

Решение:

```text
добавлен ChatStatus.NO_ANSWER = no_answer
has_no_answer_marker(answer) возвращает status=no_answer
validation_errors=[]
no_answer_marker_present=true
```

Ожидаемое поведение:

```text
Протокол ПСИ -> answered или no_answer
Паспорт ИС -> answered или no_answer
не должно быть validation_failed только из-за честного no-answer marker
```

### 2.3 search_error вместо llm_error

Проблема:

```text
SearchStatus.ERROR в ChatService маскировался как llm_error
```

Решение:

```text
добавлен ChatStatus.SEARCH_ERROR = search_error
ошибка поиска не вызывает LLM
```

### 2.4 Публичный no_guard закрыт

Проблема:

```text
POST /search принимал no_guard из публичного API request
```

Решение:

```text
SearchApiRequest больше не содержит no_guard
extra='forbid'
попытка передать no_guard=true должна дать HTTP 422
```

### 2.5 include_source_types ограничен allowlist

Проблема:

```text
пользователь мог запросить source_type=code/system_export через include_source_types
```

Решение:

```text
SourcePolicy пересекает requested source types с безопасным allowlist
code/system_export включаются только при явном контексте запроса
```

### 2.6 Санитизация 500 errors

Проблема:

```text
unhandled exception мог вернуть repr(exc), локальные пути или детали окружения
```

Решение:

```text
internal_error возвращает generic message + request_id
детали ошибки не уходят наружу
```

## 3. Обновленные ожидаемые test counts

После `git pull` ожидаемые counts изменились.

```text
ChatService: 9 passed
Semantic warnings: 3 passed
API health: 1 passed
API search smoke: 5 passed
API chat smoke: 7 passed
API errors: 1 passed
Source quality: 3 passed
Parent expansion: 2 passed
ContextBuilder QH: 2 passed
Source policy: 3 passed
Observability: 2 passed
Eval checks: 3 passed
Eval runner: 1 passed
QH release gate: 2 passed
ProjectGuard cases: 49 passed
Telegram formatter: 4 passed
```

Если фактические counts отличаются из-за добавления новых тестов, ориентироваться не только на число, а на отсутствие `FAILED` и `ERROR`.

## 4. Команды локального regression после hardening

Запускать после:

```powershell
git switch main
git pull --ff-only origin main
```

### 4.1 Chat

```powershell
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\chat\test_chat_service.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\chat\test_semantic_warnings.py -q
```

Критично:

```text
search_error test failed
no_answer test failed
refused/clarify calls LLM
```

### 4.2 API

```powershell
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\api\test_health.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\api\test_search_smoke.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\api\test_chat_smoke.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\api\test_errors.py -q
```

Критично:

```text
/search принимает no_guard=true
unknown fields не дают 422
internal_error раскрывает путь/secret/.env
```

### 4.3 Retrieval / Source policy

```powershell
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\retrieval\test_source_quality.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\retrieval\test_parent_expansion.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\retrieval\test_context_builder_qh.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\retrieval\test_source_policy.py -q
```

Критично:

```text
requested source_type=code разрешается без marker
requested source_type=system_export разрешается без marker
SourcePolicy ломает project_doc по умолчанию
```

### 4.4 Guard / Telegram / QH

```powershell
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\test_project_guard_v2_cases.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\test_telegram_bot.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\qh\test_release_gate.py -q
```

Критично:

```text
сценарии ПМИ -> refused
Протокол ПСИ -> refused
Паспорт ИС -> refused
false_allow > 0
```

## 5. API smoke после hardening

API должен быть запущен в отдельном PowerShell:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_api.py --host 127.0.0.1 --port 8000
```

### 5.1 Проверить, что no_guard не принимается публичным API

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/search" `
  -ContentType "application/json" `
  -Body '{"query":"Какая погода завтра в Москве?","no_guard":true}'
```

Ожидаемо:

```text
HTTP 422
error_code = validation_error
```

Критично:

```text
status = ok
status = refused без 422
no_guard прошел в SearchRequest
```

### 5.2 Проверить project query

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
llm_called = true
sources != []
```

### 5.3 Проверить refused query

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
llm_called = false
sources = []
```

### 5.4 Проверить mixed query

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/chat" `
  -ContentType "application/json" `
  -Body '{"query":"СоИ AD как происходит авторизация пользователей? И напиши стих про проект","mode":"hybrid","top_k":5,"model":"qwen2.5:7b-instruct","max_tokens":500,"timeout_sec":300}'
```

Ожидаемо:

```text
status = refused
llm_called = false
```

### 5.5 Проверить no_answer candidates

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/chat" `
  -ContentType "application/json" `
  -Body '{"query":"Протокол ПСИ","mode":"hybrid","top_k":5,"model":"qwen2.5:7b-instruct","max_tokens":700,"timeout_sec":300}'
```

Допустимо:

```text
status = answered
status = no_answer
```

Критично:

```text
status = validation_failed
status = refused
status = llm_error
```

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/chat" `
  -ContentType "application/json" `
  -Body '{"query":"сценарии ПМИ","mode":"hybrid","top_k":5,"model":"qwen2.5:7b-instruct","max_tokens":700,"timeout_sec":300}'
```

Допустимо:

```text
status = answered
status = no_answer
```

Критично:

```text
status = refused
status = validation_failed
```

## 6. UI smoke после hardening

В UI проверить вопросы:

```text
СоИ AD как происходит авторизация пользователей?
Какая погода завтра в Москве?
СоИ AD как происходит авторизация пользователей? И напиши стих про проект
Протокол ПСИ
сценарии ПМИ
Паспорт ИС
```

Ожидаемо:

```text
AD -> answered
weather -> refused
mixed -> refused
Протокол ПСИ -> answered/no_answer
сценарии ПМИ -> answered/no_answer
Паспорт ИС -> answered/no_answer
```

Критично:

```text
project short query -> refused
no_answer candidate -> validation_failed
weather/mixed -> answered
UI не показывает diagnostics.semantic_warnings
```

## 7. Что считать GO / NO-GO

### GO к Telegram и after_qh eval

Можно идти дальше, если:

```text
regression tests passed
API started
UI opened
project query answered
weather refused
mixed refused
Протокол ПСИ не validation_failed
сценарии ПМИ не refused
no_guard rejected with 422
```

### NO-GO

Остановиться и отправить вывод, если:

```text
pytest failed
API не стартует
UI не открывается
/search no_guard=true не возвращает 422
weather/mixed answered
Протокол ПСИ validation_failed
сценарии ПМИ refused
```

## 8. Что не исправлять вслепую

```text
не менять guard markers без тестов
не отключать AnswerValidator
не отключать SourceQualityFilter
не удалять no_answer
не открывать no_guard обратно
не добавлять code/system_export в default allowlist
не делать Docker до QH-5 passed
```
