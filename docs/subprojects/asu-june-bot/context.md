# Контекст Project Knowledge Bot

Обновлено: 2026-05-27.

## 1. Назначение

Project Knowledge Bot — отдельный подпроект внутри MeetingAgent для разработки локального project-only RAG/Chat сервиса по проектной документации информационной системы.

Бот должен:

- искать факты в проектных источниках;
- давать структурированные ответы с citations;
- явно отделять подтвержденные факты от вывода;
- отказывать на вопросы вне корпуса;
- не запускать retrieval/LLM для refused/clarify;
- генерировать ответы только по `primary_sources` и `supporting_sources`;
- логировать chat-запуски для накопления dataset;
- иметь baseline evaluation и release gate;
- предоставлять локальный Web UI и Telegram adapter поверх `/chat`.

Публичная документация подпроекта должна быть пригодна для выделения в отдельный репозиторий и не должна зависеть от конкретного заказчика или названия исходного внедрения.

Главные архитектурные документы:

```text
docs/subprojects/asu-june-bot/architecture.md
docs/subprojects/asu-june-bot/TECHNICAL_DIAGRAMS.md
docs/subprojects/asu-june-bot/RUNBOOK_V2.md
docs/subprojects/asu-june-bot/NTK_YANDEX_CORPUS.md
```

## 2. Текущий статус

Подпроект доведён до уровня локального MVP:

```text
API Search MVP — PASSED
CLI Chat MVP — PASSED_WITH_NOTES
API Chat MVP / POST /chat — PASSED_WITH_NOTES
Local Web UI / GET / and GET /ui — smoke подтвержден вручную
Telegram adapter over local /chat — READY_FOR_LOCAL_SMOKE
QH-1 Observability + Eval Baseline — реализован
QH-2 Source Quality Filter — реализован
QH-3 Parent Expansion — реализован
QH-4 Semantic Warnings / Manual Labels — реализован
QH-5 Release Gate — реализован, PASSED
```

После ручного UI smoke подтверждено:

```text
GET / или /ui открывает страницу Project Knowledge Bot
POST /chat вызывается из UI
status=answered отображается
answer отображается
sources отображаются
diagnostics отображается
semantic_warnings отображаются
```

Выявлены и исправлены дефекты:

```text
routes_ui.py f-string экранирование '{}' -> '{{}}'
честный ответ 'недостаточно данных' больше не уходит в validation_failed, добавлен status=no_answer
короткие проектные запросы 'Протокол ПСИ', 'Паспорт ИС', 'сценарии ПМИ' добавлены в guard regression
публичный no_guard удалён из /search API
include_source_types ограничен безопасным allowlist через SourcePolicy
unhandled API errors санитизированы: наружу отдается request_id без repr(exc)
SearchStatus.ERROR в ChatService мапится в status=search_error, а не llm_error
```

## 3. Текущий pipeline

```text
User question
  -> CLI / FastAPI / Web UI / Telegram adapter
  -> SearchService
      -> QueryIntent
      -> ProjectGuard v2
      -> BM25 / Vector / Hybrid retrieval
      -> PostReranker
      -> ContextBuilder
          -> QH-2 Source Quality Filter
          -> QH-3 Parent Expansion
  -> ChatService
      -> PromptBuilder
      -> LLMClient
      -> AnswerValidator
      -> QH-4 SemanticWarningAnalyzer
      -> ResponseFormatter
      -> ChatRunsLogger
  -> Response
```

Ключевое правило:

```text
/search возвращает evidence/context
/chat возвращает осмысленный answer with citations
/ui вызывает /chat
Telegram adapter вызывает локальный /chat
```

## 4. Реализованные API endpoints

```text
GET /
GET /ui
GET /health
POST /search
POST /chat
```

`POST /search` возвращает:

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

`POST /chat` возвращает:

```text
status
query
answer
sources
search
warnings
diagnostics
```

Актуальные chat statuses:

```text
answered
refused
clarify
no_sources
no_answer
search_error
llm_error
llm_empty_response
validation_failed
```

## 5. Runtime-компоненты

### Общие ограничения

```text
src/asu_june_bot/core/limits.py
MAX_QUERY_CHARS = 2000
```

### NTK Yandex Corpus

2026-05-25 начата отдельная ветка `codex/ntk-yandex-corpus` для корпуса:

```text
C:\Users\Сотрудник\Desktop\Yandex.Disk\Документы НТК Сдача
```

Runtime:

```text
data/asu_june_bot_ntk/
```

Состояние:

```text
source links built
extraction complete
chunks built
embeddings/index built
BM25-only smoke: 8/20
hybrid smoke after project markers/routing: completed, 20/20
default corpus switch: not done
```

После chat-level проверки `NTK-SMOKE-007` зафиксировано:

```text
предыдущее `20/20` было false positive для RTO/RPO;
smoke проверял только doc_type=ЦТА и не проверял recovery anchors;
LLM не галлюцинировал: при слабом retrieval он честно отвечал, что источников недостаточно.
```

Исправление:

```text
добавлен отдельный intent `cta_recovery_rto_rpo`;
RTO/RPO вынесены в отдельный query-expansion bucket;
BM25/PostReranker получили boost recovery chunks и penalty logging/port-only chunks;
`scripts/asu_june_bot_ntk_smoke_eval.py` теперь умеет проверять `expected_terms_in_top5`.
```

Проверка после фикса:

```text
hybrid smoke: 19/20 ok
NTK-SMOKE-007: ok=true, terms_hit_in_top5=true
chat-level `asu_june_bot_chat.py "Что указано в ЦТА про RTO и RPO?"`:
  retrieval поднимает recovery chunks из ЦТА;
  answer опирается на RTO=4 часа и RPO=4 часа;
  NTK-SMOKE-017 после ручной проверки признан устаревшим expectation smoke, а не retrieval-багом
```

По `NTK-SMOKE-017` подтверждено:

```text
корректный expected_doc_type для вопроса про регламенты ведения объектов НСИ — `Методика/Регламент НСИ`;
retrieval и chat-level ответ уже идут в этот тип документов;
expectation smoke обновлен, и hybrid smoke снова дает `20/20 ok`;
остаточный технический риск — `weak_primary_fallback`: primary поднимается из короткого registry/note chunk, хотя в supporting уже есть полноценные регламентные документы.
```

Главная инструкция:

```text
docs/subprojects/asu-june-bot/NTK_YANDEX_CORPUS.md
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

### Extraction / Chunking / Index

```text
scripts/asu_june_bot_apply_config_v2_1.py
scripts/asu_june_bot_extract_text_v2.py
scripts/asu_june_bot_build_chunks_v2.py
scripts/asu_june_bot_audit_sources_v2.py
scripts/asu_june_bot_build_index_v2.py
scripts/asu_june_bot_health_v2.py
```

### Search / Guard / API / UI

```text
src/asu_june_bot/search/
src/asu_june_bot/retrieval/
src/asu_june_bot/guardrails/
src/asu_june_bot/health/
src/asu_june_bot/api/
src/asu_june_bot/api/routes_ui.py
scripts/asu_june_bot_search_v2.py
scripts/asu_june_bot_guard_v2_eval.py
scripts/asu_june_bot_api.py
```

### Chat / LLM / Telegram

```text
src/asu_june_bot/chat/
src/asu_june_bot/llm/
src/asu_june_bot/telegram_bot.py
scripts/asu_june_bot_chat.py
scripts/asu_june_bot_telegram.py
```

### Observability / Eval / QH

```text
src/asu_june_bot/observability/
src/asu_june_bot/eval/
src/asu_june_bot/qh/
scripts/asu_june_bot_chat_eval.py
scripts/asu_june_bot_qh_gate.py
eval/cases/base.jsonl
eval/golden_answers/*.md
```

## 6. Текущий локальный результат

Corpus/index:

```text
documents = 213
blocks = 31076
chunks_v2 = 31302
indexed_chunks = 31285
skipped_code_chunks = 17
embedding_model = bge-m3
embedding_dim = 1024
```

Health:

```text
status = ok
vector_ready = true
bm25_ready = true
ollama_available = true
embedding_model_installed = true
```

ProjectGuard:

```text
false_allow = 0
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

Причины:

```text
qwen3:4b -> llm_empty_response / finish_reason=length
qwen3:8b -> timeout/обрыв на CPU runtime
```

## 7. QH status

```text
QH-1 Observability + Eval Baseline — implemented
QH-2 Source Quality Filter — implemented
QH-3 Parent Expansion — implemented
QH-4 Semantic Warnings / Manual Labels — implemented
QH-5 Release Gate — implemented, passed
```

QH-5 закрыт 2026-05-19 после:

```text
local regression tests
API smoke
Web UI smoke
Telegram smoke
final QH gate
after_qh eval
baseline comparison
qh gate with --local-validation-done --baseline-compared
smoke_report_qh_release.md
```

## 8. Завтрашний запуск

Главный детальный документ:

```text
docs/subprojects/asu-june-bot/TOMORROW_EXECUTION_PROTOCOL.md
```

Короткий чек-лист:

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
after_qh eval
QH gate
smoke report
```

Ключевые команды:

```powershell
cd C:\Users\Сотрудник\Desktop\AI\MeetingAgent
(Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned) ; (& .\.venv\Scripts\Activate.ps1)
git switch main
git pull --ff-only origin main
.\.venv\Scripts\python.exe scripts\asu_june_bot_api.py --host 127.0.0.1 --port 8000
```

Открыть UI:

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/ui
```

Telegram:

```powershell
.\scripts\asu_june_bot_start_telegram.ps1 -AllowedChatIds "YOUR_CHAT_ID"
```

## 9. Активная документация

Главные документы:

```text
README.md
TOMORROW_EXECUTION_PROTOCOL.md
TOMORROW_START.md
QH_STATUS.md
FTT_STATUS.md
architecture.md
mvp.md
roadmap.md
decisions.md
RUNBOOK_V2.md
telegram.md
todo.md
eval_questions.md
ideas.md
product/
smoke_report_*.md
```

## 10. Локальная проверка 2026-05-18 / 2026-05-19

Выполнено:

```text
health_v2: ok
ollama: bge-m3 и qwen2.5:7b-instruct доступны
regression tests: 97 passed
QH gate до smoke: pending_local_validation
API smoke: /health, /search, /chat проверены
Web UI HTTP smoke: /ui отдаёт страницу с нужными элементами
chat_runs.jsonl: пишется
after_qh eval: 7/13, 53.8%
baseline comparison: baseline 6/13, 46.2% -> after_qh 7/13, 53.8%
2026-05-19: FastAPI /health перепроверен, добавлен safe launcher scripts/asu_june_bot_start_telegram.ps1
```

Создан отчёт:

```text
docs/subprojects/asu-june-bot/smoke_report_qh_release.md
```

QH-5 закрыт как `PASSED`: Telegram smoke закрыт локально, final gate выполнен с `--local-validation-done --baseline-compared`.

## 11. Следующие шаги

Сейчас:

```text
1. Ручной просмотр smoke_eval_hybrid_after_markers_v3 завершен: 18/20 strict pass, 2 partial, 0 fail.
2. Feature flag корпуса реализован через configs/asu_june_bot/corpus.yaml и ASU_JUNE_BOT_ACTIVE_CORPUS=default|ntk.
3. Health-check с ASU_JUNE_BOT_ACTIVE_CORPUS=ntk подтверждает переключение на data/asu_june_bot_ntk.
4. Для NTK-SMOKE-012 внесен targeted retrieval-fix: в top-2 появляется chunk с таблицей "Роли / группы AD" и app_ccpm_ul_cc_01/02/03.
5. Для NTK-SMOKE-017 внесен targeted retrieval-fix: top-1..top-5 уходят в Методика/Регламент НСИ вместо одного Реестра НСИ.
6. До глобального переключения нужен повторный ручной review именно кейсов 012 и 017.
7. После этого проектировать incremental update для Yandex-папки.
```

После QH-5 passed:

```text
1. Зафиксировать QH_STATUS.md и FTT_STATUS.md.
2. Перейти к Docker stage.
3. Не менять retrieval/guard без eval baseline.
```

## 12. Не делать сейчас

```text
не запускать --reset без причины
не удалять data/asu_june_bot
не пересчитывать embeddings, если индекс уже готов
не менять модель embeddings bge-m3
не коммитить Telegram token
не пытаться заставить /search писать осмысленные ответы
не подключать DSPy в runtime
не делать LLM-as-judge/NLI до накопления dataset
не делать Docker до QH-5 passed
не развивать scripts/09_chat.py как основной runtime
не смешивать старый RAG v1 и новый bot v2.1
```
