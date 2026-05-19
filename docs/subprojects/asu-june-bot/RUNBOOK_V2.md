# Asu June Bot v2 Runbook

Обновлено: 2026-05-16.

## Назначение

Инструкция запуска независимого pipeline Asu June Bot v2.1/v2.2:

```text
apply_config_v2_1 -> extract_text_v2 -> chunks_v2 -> audit_sources_v2 -> build_index_v2 -> health_v2 -> search_v2 -> SearchService -> FastAPI /search -> ChatService -> CLI chat -> API /chat -> Web UI -> Telegram adapter -> QH-1 eval baseline
```

Pipeline v2 не использует старый `scripts/02_extract_text.py` и не меняет старые runtime-файлы MeetingAgent:

```text
data/chunks.jsonl
data/embeddings_cache.jsonl
data/numpy_index/
```

Все новые runtime-данные пишутся в:

```text
data/asu_june_bot/
```

## Быстрый старт завтра

Для восстановления после выключения рабочего ПК сначала выполнить отдельный чек-лист:

```text
docs/subprojects/asu-june-bot/TOMORROW_START.md
```

Он содержит минимальную последовательность:

```text
git pull -> health -> tests -> API -> Web UI -> Telegram adapter
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
API Chat MVP / POST /chat
Local Web UI: GET / and GET /ui
Telegram adapter over local /chat
QH-1 Observability + Eval Baseline skeleton
```

Финальные smoke-отчёты:

```text
docs/subprojects/asu-june-bot/smoke_report_project_guard_v2.md
docs/subprojects/asu-june-bot/smoke_report_search_service_commit1.md
docs/subprojects/asu-june-bot/smoke_report_api_search_mvp.md
docs/subprojects/asu-june-bot/smoke_report_chat_mvp.md
docs/subprojects/asu-june-bot/smoke_report_api_chat_mvp.md
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

## Ограничения ввода

Единый лимит запроса:

```text
MAX_QUERY_CHARS = 2000
```

Лимит применяется в:

```text
ChatRequest
SearchRequest
POST /chat
POST /search
Web UI
Telegram adapter
```

Слишком длинный запрос должен возвращать validation error до запуска retrieval/LLM.

## 1. Обновить ветку

```powershell
cd C:\Users\Сотрудник\Desktop\AI\MeetingAgent
git switch main
git pull --ff-only origin main
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

## 6. ChatService tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\chat\test_chat_service.py -q
```

Ожидаемо:

```text
7 passed
```

## 7. API/UI tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\api\test_health.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\api\test_search_smoke.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\api\test_chat_smoke.py -q
```

Ожидаемо после UI/limit изменений:

```text
test_health.py: 1 passed
test_search_smoke.py: 4 passed
test_chat_smoke.py: 7 passed
```

Если FastAPI/uvicorn не установлены:

```powershell
.\.venv\Scripts\python.exe -m pip install fastapi uvicorn
```

## 8. QH-1 observability/eval tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\observability\test_chat_runs.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\eval\test_checks.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\eval\test_runner.py -q
```

Ожидаемо после последних eval fixes:

```text
observability: 2 passed
eval checks: 3 passed
eval runner: 1 passed
```

## 9. Запуск API и Web UI

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_api.py --host 127.0.0.1 --port 8000
```

Ожидаемо:

```text
Application startup complete
Uvicorn running on http://127.0.0.1:8000
```

Открыть в браузере:

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/ui
```

## 10. API smoke: /health

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

## 11. API smoke: /search project query

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

## 12. API smoke: /chat project query

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
answer != null
sources != []
diagnostics.llm_called = true
diagnostics.llm_model = qwen2.5:7b-instruct
diagnostics.llm_finish_reason = stop
```

## 13. API smoke: /chat out-of-project query

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
sources = []
diagnostics.llm_called = false
```

## 14. Telegram adapter

Подробная инструкция:

```text
docs/subprojects/asu-june-bot/telegram.md
```

Минимальный запуск:

```powershell
$env:ASU_JUNE_BOT_TELEGRAM_TOKEN='PASTE_TOKEN_HERE'
$env:ASU_JUNE_BOT_CHAT_API_URL='http://127.0.0.1:8000/chat'
.\.venv\Scripts\python.exe scripts\asu_june_bot_telegram.py
```

Рекомендуется ограничить chat id:

```powershell
$env:ASU_JUNE_BOT_ALLOWED_CHAT_IDS='123456789'
```

Команды в Telegram:

```text
/start
/help
/health
```

Обычное текстовое сообщение считается вопросом к `/chat`.

## 15. CLI search smoke

Использовать `--output`, а не PowerShell `>` — иначе возможна порча UTF-8 в Windows PowerShell.

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Что входит в Паспорт ИС?" --mode hybrid --top-k 8 --json --output "data\asu_june_bot\smoke_passport_context.json"

.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "ФТТ 4.2.5 НОВАДОК ЭЦП" --mode hybrid --top-k 8 --json --output "data\asu_june_bot\smoke_ftt_425_context.json"

.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Какие интеграции заявлены в проекте?" --mode hybrid --top-k 8 --json --output "data\asu_june_bot\smoke_integrations_context.json"
```

## 16. CLI Chat MVP smoke + chat_runs.jsonl

Project question:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_chat.py "СоИ AD как происходит авторизация пользователей?" --mode hybrid --top-k 5 --model qwen2.5:7b-instruct --max-tokens 500 --timeout-sec 300 --json --output data\asu_june_bot\smoke_chat_ad_qwen25_7b.json
```

Проверить лог:

```powershell
Get-Content data\asu_june_bot\chat_runs.jsonl -Encoding UTF8 -Tail 1
```

Ожидаемо:

```text
chat_runs.jsonl содержит валидный JSONL
status = answered
llm_called = true
sources != []
latency_ms != null
```

Отключить логирование для разового запуска:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_chat.py "СоИ AD как происходит авторизация пользователей?" --no-log
```

## 17. QH-1 eval baseline

Запустить baseline без изменения retrieval/context:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_chat_eval.py --cases eval\cases\base.jsonl --label baseline --model qwen2.5:7b-instruct --top-k 5
```

Ожидаемо:

```text
Eval cases: 13
Passed: N
Failed: M
Pass rate: X.X%
JSON report: eval\reports\*__baseline.json
Markdown report: eval\reports\*__baseline.md
```

Важно:

```text
baseline может быть ниже 100%.
Это не ошибка.
Цель QH-1 — измерить текущее качество, а не подогнать кейсы.
```

Если нужно прогнать eval без записи в `chat_runs.jsonl`:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_chat_eval.py --cases eval\cases\base.jsonl --label baseline --model qwen2.5:7b-instruct --top-k 5 --no-log
```

## 18. Почему /search не даёт осмысленный ответ

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

## 19. Ограничение Chat MVP

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

Это quality debt. QH-1 не решает его напрямую, а создаёт измеримый baseline.

## 20. Полная пересборка v2.1 при изменении корпуса

Если меняются фильтры, список файлов или правила extraction/chunking, пересобрать с нуля:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_extract_text_v2.py --reset
.\.venv\Scripts\python.exe scripts\asu_june_bot_build_chunks_v2.py
.\.venv\Scripts\python.exe scripts\asu_june_bot_audit_sources_v2.py
.\.venv\Scripts\python.exe scripts\asu_june_bot_build_index_v2.py --embed-only
.\.venv\Scripts\python.exe scripts\asu_june_bot_build_index_v2.py --index-only
.\.venv\Scripts\python.exe scripts\asu_june_bot_health_v2.py
```

## 21. Проверка extraction/chunking

Для Windows PowerShell 5.1 всегда указывать `-Encoding UTF8` при чтении отчетов.

```powershell
Get-Content .\data\asu_june_bot\extracted_v2\extraction_v2_report.json -Encoding UTF8
Get-Content .\data\asu_june_bot\chunking_v2_report.json -Encoding UTF8
Get-Content .\data\asu_june_bot\source_audit_v2_report.json -Encoding UTF8
Get-Content .\data\asu_june_bot\index_v2_report.json -Encoding UTF8
Get-Content .\data\asu_june_bot\numpy_index_v2\manifest.json -Encoding UTF8
```

## 22. Следующие этапы после baseline

### QH-2. Source Quality Filter

Делать только после анализа baseline.

```text
src/asu_june_bot/retrieval/source_quality.py
unit tests для weak chunks
интеграция в ContextBuilder
повторный eval: label=with_source_filter
сравнение с baseline
```

### QH-3. Parent Expansion

Делать только если QH-2 не устранил проблему коротких chunks.

```text
strict max chars
dedup parent context
никакого expansion без лимита
сравнение eval до/после
```

## 23. Не делать

- Не пытаться заставить `/search` писать осмысленные ответы.
- Не удалять `data/asu_june_bot/`, если нужно продолжить после прерывания.
- Не запускать `--reset`, если нужна resume-сборка.
- Не менять старый `run_full_rag.ps1`.
- Не перезаписывать `data/chunks.jsonl`.
- Не индексировать `Система` в основной project-only корпус.
- Не отправлять в LLM сырой hybrid top-k.
- Не развивать старый `scripts/09_chat.py` как основной runtime.
- Не внедрять JSON-mode, retry, NLI и LLM-judge до накопления eval dataset.
- Не внедрять source quality filter без baseline.
- Не внедрять parent expansion без замера эффекта source quality filter.
- Не начинать Docker до QH-5 Release Stabilization.
