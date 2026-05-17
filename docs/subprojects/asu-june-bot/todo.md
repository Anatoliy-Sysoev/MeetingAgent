# TODO Project Knowledge Bot

Обновлено: 2026-05-16.

## Текущий статус

API Search MVP закрыт. CLI Chat MVP и API Chat MVP прошли smoke. Добавлены локальный Web UI, Telegram adapter и единый лимит длины запроса.

Этап **QH-1 Observability + Eval Baseline** реализован в коде. Первый baseline показал, что есть смесь ложных eval failures, guard gap и реальных retrieval/context gaps. Часть ложных падений уже исправлена.

Принято решение: Docker-упаковка выполняется **после QH-5 Release Stabilization**, а не сейчас.

## Для завтрашнего восстановления

Главный чек-лист:

```text
docs/subprojects/asu-june-bot/TOMORROW_START.md
```

Порядок:

```text
git pull
health
tests
API
Web UI
Telegram adapter
manual smoke
```

## Закрыто ранее

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
POST /chat runtime smoke
QH-1 Observability + Eval Baseline code implementation
Product docs refresh
Docker-after-QH-5 decision
```

## Закрыто сегодня через GitHub

```text
MAX_QUERY_CHARS = 2000
ChatRequest query length validation
SearchRequest query length validation
POST /chat max_length validation
POST /search max_length validation
Local Web UI: GET / and GET /ui
Telegram adapter: src/asu_june_bot/telegram_bot.py
Telegram script: scripts/asu_june_bot_telegram.py
TOMORROW_START.md
telegram.md
README.md обновлен
RUNBOOK_V2.md обновлен
```

## Ожидаемые тесты завтра

```powershell
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\chat\test_chat_service.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\api\test_health.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\api\test_search_smoke.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\api\test_chat_smoke.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\observability\test_chat_runs.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\eval\test_checks.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\eval\test_runner.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\test_project_guard_v2_cases.py -q
```

Ожидаемо после последних изменений:

```text
ChatService: 7 passed
API health: 1 passed
API search: 4 passed
API chat: 7 passed
observability: 2 passed
eval checks: 3 passed
eval runner: 1 passed
ProjectGuard cases: 46 passed
```

Фактический результат надо подтвердить завтра локальным прогоном.

## Завтрашний smoke для сдачи

### API + UI

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_api.py --host 127.0.0.1 --port 8000
```

Открыть:

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/ui
```

### Telegram

```powershell
$env:ASU_JUNE_BOT_TELEGRAM_TOKEN='PASTE_TOKEN_HERE'
$env:ASU_JUNE_BOT_CHAT_API_URL='http://127.0.0.1:8000/chat'
.\.venv\Scripts\python.exe scripts\asu_june_bot_telegram.py
```

Рекомендуется ограничить доступ:

```powershell
$env:ASU_JUNE_BOT_ALLOWED_CHAT_IDS='123456789'
```

## Реализовано в QH-1

```text
src/asu_june_bot/observability/chat_runs.py
src/asu_june_bot/observability/__init__.py
src/asu_june_bot/eval/models.py
src/asu_june_bot/eval/checks.py
src/asu_june_bot/eval/runner.py
src/asu_june_bot/eval/report.py
src/asu_june_bot/eval/loader.py
src/asu_june_bot/eval/__init__.py
scripts/asu_june_bot_chat_eval.py
eval/cases/base.jsonl
eval/golden_answers/*.md
tests/asu_june_bot/observability/test_chat_runs.py
tests/asu_june_bot/eval/test_checks.py
tests/asu_june_bot/eval/test_runner.py
```

QH-1 принципиально не включает:

```text
source quality filter
parent expansion
LLM-as-judge
NLI / groundedness model
DSPy runtime
JSON-mode
retry policy
Docker
```

## QH-1 baseline: первичный вывод

Первый baseline:

```text
total = 13
passed = 6
failed = 7
pass_rate = 46.2%
```

Не трактовать как провал `/chat`.

Категории проблем:

```text
ложные eval failures: source_titles, clarify must_include
project guard gap: логирование как проектный вопрос
real retrieval/context gaps: ФТТ 4.2.5, short UML/source traps, no-context/SLA
```

Уже исправлено:

```text
source_titles ищет не только в title, но и path/section/preview
clarify cases проверяют фактическую формулировку "Сформулируйте"
ProjectGuard получил project markers для логирования/Grafana Loki/журналирования
```

Нужно подтвердить завтра локальными тестами и повторным baseline.

## Следующий приоритет после демонстрационного smoke

### QH-2. Source Quality Filter

Делать после повторного baseline.

План:

```text
src/asu_june_bot/retrieval/source_quality.py
unit tests для weak chunks
интеграция в ContextBuilder
повторный eval: label=with_source_filter
сравнение с baseline
```

Принцип:

```text
не удалять короткие chunks из индекса
не ломать retrieval
помечать / понижать weak chunks в context stage
фиксировать reason в diagnostics
```

### QH-3. Parent Expansion

Делать только если QH-2 не устранил проблему коротких chunks.

Принцип:

```text
строгий max chars
dedup parent context
никакого расширения без лимита
сравнение eval до/после
```

### QH-4. Semantic Warnings / Manual Labels

После QH-2/QH-3:

```text
manual_label / manual_issue в chat_runs.jsonl
semantic_warnings в diagnostics
low-overlap / weak-source warnings как warning, не hard-fail
```

### QH-5. Release Stabilization

Перед Docker:

```text
закрыть/зафиксировать QH-1..QH-4
прогнать regression и smoke
синхронизировать документацию
проверить portable paths/config
проверить отсутствие secrets/runtime data в Git
заморозить минимальный stable MVP contour
```

## Docker stage после QH-5

Docker не делать до закрытия QH-5.

Минимальный состав Docker stage:

```text
Dockerfile
.dockerignore
docker-compose.yml
.env.example
config.docker.example.yaml
docs/deployment/docker.md
bot-api service
host volumes для data/eval/config
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
поддерживается ли каждое утверждение конкретным source text
не делает ли модель спорный вывод из короткого UML/heading chunk
нет ли semantic hallucination при формально корректных [Sx]
```

Это фиксируется как quality debt, а не runtime blocker.

## Не делать сейчас

```text
не пытаться заставить /search писать осмысленные ответы
не отправлять raw hybrid top-k в LLM
не вызывать LLM при refused или clarify
не развивать scripts/09_chat.py как основной runtime
не подключать NeMo Guardrails, LangGraph, Dify/RAGFlow как runtime MVP
не возвращаться к раздуванию OUT_OF_PROJECT_MARKERS
не внедрять JSON-mode, retry, NLI и LLM-judge до накопления eval dataset
не внедрять source quality filter без baseline
не внедрять parent expansion без замера эффекта source quality filter
не делать Docker до QH-5 Release Stabilization
не коммитить Telegram token
```
