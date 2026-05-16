# Asu June Bot v2 Runbook

Обновлено: 2026-05-15.

## Назначение

Инструкция запуска независимого pipeline Asu June Bot v2.1/v2.2:

```text
apply_config_v2_1 -> extract_text_v2 -> chunks_v2 -> audit_sources_v2 -> build_index_v2 -> health_v2 -> search_v2 -> SearchService -> FastAPI /search -> ChatService -> CLI chat
```

Pipeline v2 не использует старый `scripts/02_extract_text.py` и не меняет старые runtime-файлы MeetingAgent:

```text
data/chunks.jsonl
data/embeddings_cache.jsonl
data/numpy_index/
```

Все новые данные пишутся в:

```text
data/asu_june_bot/
```

## Текущий статус

Готово:

```text
Extraction/Chunking v2.1
Index/Search v2
Search Quality v2.2
ProjectGuard v2
SearchService
API Search MVP
CLI Chat MVP
```

Финальные smoke-отчёты:

```text
docs/subprojects/asu-june-bot/smoke_report_project_guard_v2.md
docs/subprojects/asu-june-bot/smoke_report_search_service_commit1.md
docs/subprojects/asu-june-bot/smoke_report_api_search_mvp.md
docs/subprojects/asu-june-bot/smoke_report_chat_mvp.md
```

Следующий этап:

```text
POST /chat
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

## 1. Обновить ветку

```powershell
cd C:\Users\Сотрудник\Desktop\AI\MeetingAgent
git checkout docs/asu-june-bot-subproject
git pull --ff-only origin docs/asu-june-bot-subproject
```

## 2. Health check v2 через CLI

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_health_v2.py
```

JSON-вывод:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_health_v2.py --json
```

Ключевые признаки готовности:

```text
bm25_ready = true
vector_ready = true
counts.manifest_count = 31285
counts.index_metadata = 31285
checks.ollama_available = true
checks.embedding_model_installed = true
```

Если `bm25_ready = true`, а `vector_ready = false`, BM25-поиск работает, но vector/hybrid требует запущенный Ollama и модель `bge-m3`.

## 3. Если Ollama недоступен

Проверка:

```powershell
ollama list
```

Если Ollama не запущен:

```powershell
ollama serve
```

Если embedding-модели нет:

```powershell
ollama pull bge-m3
```

Если chat-модели нет:

```powershell
ollama pull qwen2.5:7b-instruct
```

После этого повторить:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_health_v2.py
```

## 4. ProjectGuard v2 regression

Базовые тесты:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\test_project_guard_v2.py -q
```

Regression suite:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\test_project_guard_v2_cases.py -q
```

Eval runner:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_guard_v2_eval.py --print-failed --fail-on-error
```

Ожидаемый результат:

```text
base tests passed
45 regression cases passed
false_allow = 0
```

Критический критерий:

```text
false_allow = 0
```

Если `false_allow > 0`, нельзя переходить к API/Chat до исправления guard.

## 5. SearchService tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\search\test_search_service.py -q
```

Ожидаемо:

```text
4 passed
```

Проверяется:

```text
refused -> retrieval_called=false
clarify -> retrieval_called=false
allow -> retrieval_called=true
--no-guard -> retrieval_called=true
```

## 6. ChatService tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\chat\test_chat_service.py -q
```

Ожидаемо:

```text
7 passed
```

Проверяется:

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

## 7. API Search tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\api\test_health.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\api\test_search_smoke.py -q
```

Ожидаемо:

```text
test_health.py: 1 passed
test_search_smoke.py: 3 passed
```

Если FastAPI/uvicorn не установлены:

```powershell
.\.venv\Scripts\python.exe -m pip install fastapi uvicorn
```

## 8. Запуск API Search MVP

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_api.py --host 127.0.0.1 --port 8000
```

Ожидаемо:

```text
Application startup complete
Uvicorn running on http://127.0.0.1:8000
```

## 9. API smoke: /health

В другом PowerShell:

```powershell
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8000/health"
```

Ожидаемо:

```text
status = ok
service = asu_june_bot
bm25_ready = true
vector_ready = true
guard_v2_ready = true
```

## 10. API smoke: /search project query

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/search" `
  -ContentType "application/json" `
  -Body '{"query":"СоИ AD как происходит авторизация пользователей?","mode":"hybrid","top_k":8}'
```

Ожидаемо:

```text
status = ok
results != []
context.primary_sources/supporting_sources != []
diagnostics.search_service.retrieval_called = true
```

## 11. API smoke: /search out-of-project query

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/search" `
  -ContentType "application/json" `
  -Body '{"query":"Какая погода завтра в Москве?","mode":"hybrid","top_k":8}'
```

Ожидаемо:

```text
status = refused
results = []
diagnostics.search_service.retrieval_called = false
```

## 12. API smoke: /search project + unknown tail

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/search" `
  -ContentType "application/json" `
  -Body '{"query":"СоИ AD как происходит авторизация пользователей? И расскажи стих про проект","mode":"hybrid","top_k":8}'
```

Ожидаемо:

```text
status = refused
guard.reason = in_project_query_contains_unclassified_segment
results = []
diagnostics.search_service.retrieval_called = false
```

Правило: не расширять marker DB частными темами. `project + unknown tail` блокируется на уровне `GuardPolicy`.

## 13. CLI search smoke

Использовать `--output`, а не PowerShell `>` — иначе возможна порча UTF-8 в Windows PowerShell.

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Что входит в Паспорт ИС?" --mode hybrid --top-k 8 --json --output "data\asu_june_bot\smoke_passport_context.json"

.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "ФТТ 4.2.5 НОВАДОК ЭЦП" --mode hybrid --top-k 8 --json --output "data\asu_june_bot\smoke_ftt_425_context.json"

.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Какие интеграции заявлены в проекте?" --mode hybrid --top-k 8 --json --output "data\asu_june_bot\smoke_integrations_context.json"
```

Ожидаемо:

```text
Паспорт ИС:
  status = ok
  primary_sources = 1

ФТТ 4.2.5:
  status = ok
  primary source = ФТТ / Таблица 8 / строка 44 / № 4.2.5

Интеграции:
  status = ok
  primary/supporting содержит ЦТА, Паспорт ИС, ФТТ, СоИ
```

## 14. CLI Chat MVP smoke

Project question:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_chat.py "СоИ AD как происходит авторизация пользователей?" --mode hybrid --top-k 5 --model qwen2.5:7b-instruct --max-tokens 500 --timeout-sec 300 --json --output data\asu_june_bot\smoke_chat_ad_qwen25_7b.json
```

Ожидаемо:

```text
status = answered
llm_called = true
llm_model = qwen2.5:7b-instruct
llm_finish_reason = stop
validation_errors = []
prompt_sources = 5
selected_sources = 5
used_context_chars <= max_context_chars
```

Out-of-project question:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_chat.py "Какая погода завтра в Москве?" --mode hybrid --top-k 5 --model qwen2.5:7b-instruct --max-tokens 500 --timeout-sec 300 --json --output data\asu_june_bot\smoke_chat_weather_refused.json
```

Ожидаемо:

```text
status = refused
llm_called = false
```

Не использовать для smoke default-модель qwen3:

```text
qwen3:4b -> llm_empty_response / finish_reason=length
qwen3:8b -> timeout/обрыв на локальном CPU runtime
```

## 15. Почему /search не даёт осмысленный ответ

`/search` — это не чат и не генератор ответа. Он возвращает evidence/context:

```text
query_intent
guard
context.primary_sources
context.supporting_sources
context.excluded_sources
results
warnings
diagnostics
```

Осмысленный текстовый ответ даёт ChatService:

```text
Question
  -> SearchService.search()
  -> ContextBuilder context
  -> PromptBuilder
  -> LLMClient
  -> AnswerValidator
  -> ResponseFormatter
  -> answer with citations
```

Не надо заставлять `/search` писать ответ. Это создаст смешение responsibilities и снова приведёт к монолиту.

## 16. Ограничение Chat MVP

Текущий `AnswerValidator` выполняет structural validation, но не semantic/factual validation.

Проверяется:

```text
пустой ответ
наличие sources
наличие ссылок [Sx]
unknown citations
external knowledge markers
answer length
citation density / coverage
```

Не проверяется:

```text
поддерживается ли каждое утверждение конкретным source text;
не сделала ли модель спорный вывод из короткого UML/heading/caption chunk;
нет ли semantic hallucination при формально корректных [Sx].
```

Это quality debt, а не blocker для `POST /chat`.

## 17. Полная пересборка v2.1 при изменении корпуса

Если меняются фильтры, список файлов или правила extraction/chunking, пересобрать с нуля:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_extract_text_v2.py --reset
.\.venv\Scripts\python.exe scripts\asu_june_bot_build_chunks_v2.py
.\.venv\Scripts\python.exe scripts\asu_june_bot_audit_sources_v2.py
.\.venv\Scripts\python.exe scripts\asu_june_bot_build_index_v2.py --embed-only
.\.venv\Scripts\python.exe scripts\asu_june_bot_build_index_v2.py --index-only
.\.venv\Scripts\python.exe scripts\asu_june_bot_health_v2.py
```

## 18. Проверка extraction/chunking

Для Windows PowerShell 5.1 всегда указывать `-Encoding UTF8` при чтении отчетов.

```powershell
Get-Content .\data\asu_june_bot\extracted_v2\extraction_v2_report.json -Encoding UTF8
Get-Content .\data\asu_june_bot\chunking_v2_report.json -Encoding UTF8
Get-Content .\data\asu_june_bot\source_audit_v2_report.json -Encoding UTF8
Get-Content .\data\asu_june_bot\index_v2_report.json -Encoding UTF8
Get-Content .\data\asu_june_bot\numpy_index_v2\manifest.json -Encoding UTF8
```

## 19. Watchdog для долгого embeddings cache

```powershell
.\register_asu_june_bot_index_v2_watchdog.ps1 -IntervalMinutes 30
```

Лог:

```powershell
Get-Content .\logs\asu_june_bot_index_v2_watchdog.log -Encoding UTF8 -Tail 80
```

Отключить вручную:

```powershell
Unregister-ScheduledTask -TaskName AsuJuneBotIndexV2Watchdog -Confirm:$false
```

## 20. Следующий этап: POST /chat

Реализовать:

```text
src/asu_june_bot/api/routes_chat.py
```

`POST /chat` должен использовать `ChatService`, а не дублировать guard/retrieval/context/generation.

## 21. Не делать

- Не пытаться заставить `/search` писать осмысленные ответы.
- Не удалять `data/asu_june_bot/`, если нужно продолжить после прерывания.
- Не запускать `--reset`, если нужна resume-сборка.
- Не менять старый `run_full_rag.ps1`.
- Не перезаписывать `data/chunks.jsonl`.
- Не индексировать `Система` в основной project-only корпус.
- Не отправлять в LLM сырой hybrid top-k.
- Не развивать старый `scripts/09_chat.py` как основной runtime.
- Не внедрять JSON-mode, retry, NLI и LLM-judge до накопления eval dataset.
