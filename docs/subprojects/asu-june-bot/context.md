# Контекст Project Knowledge Bot

Обновлено: 2026-05-16.

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
- иметь baseline evaluation перед улучшениями retrieval/context.

Публичная документация подпроекта должна быть пригодна для выделения в отдельный репозиторий и не должна зависеть от конкретного заказчика или названия исходного внедрения.

## 2. Текущий статус

Подпроект доведён до уровня:

```text
API Search MVP — PASSED
CLI Chat MVP — PASSED_WITH_NOTES
API Chat MVP / POST /chat — PASSED_WITH_NOTES
QH-1 Observability + Eval Baseline — реализован в коде, ожидает локальный baseline-прогон
```

Завершены этапы:

```text
Extraction/Chunking v2.1
Index/Search v2
Search Quality v2.2
ProjectGuard v2
SearchService
FastAPI GET /health
FastAPI POST /search
ChatService
CLI chat
FastAPI POST /chat
ChatRunsLogger
Eval baseline skeleton
```

## 3. Текущий pipeline

```text
User question
  -> CLI / FastAPI
  -> SearchService
      -> QueryIntent
      -> ProjectGuard v2
      -> BM25 / Vector / Hybrid retrieval
      -> PostReranker
      -> ContextBuilder
  -> ChatService
      -> PromptBuilder
      -> LLMClient
      -> AnswerValidator
      -> ResponseFormatter
      -> ChatRunsLogger
  -> Response
```

Ключевое правило:

```text
/search возвращает evidence/context
/chat возвращает осмысленный answer with citations
```

## 4. Реализованные API endpoints

```text
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

## 5. Runtime-компоненты

### Extraction / Chunking / Index

```text
scripts/asu_june_bot_apply_config_v2_1.py
scripts/asu_june_bot_extract_text_v2.py
scripts/asu_june_bot_build_chunks_v2.py
scripts/asu_june_bot_audit_sources_v2.py
scripts/asu_june_bot_build_index_v2.py
scripts/asu_june_bot_health_v2.py
```

### Search / Guard / API

```text
src/asu_june_bot/search/
src/asu_june_bot/retrieval/
src/asu_june_bot/guardrails/
src/asu_june_bot/health/
src/asu_june_bot/api/
scripts/asu_june_bot_search_v2.py
scripts/asu_june_bot_guard_v2_eval.py
scripts/asu_june_bot_api.py
```

### Chat / LLM

```text
src/asu_june_bot/chat/
src/asu_june_bot/llm/
scripts/asu_june_bot_chat.py
```

### Observability / Eval

```text
src/asu_june_bot/observability/
src/asu_june_bot/eval/
scripts/asu_june_bot_chat_eval.py
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

Chat smoke:

```text
qwen2.5:7b-instruct -> answered / finish_reason=stop / validation_errors=[]
qwen3:4b -> llm_empty_response / finish_reason=length
qwen3:8b -> timeout/обрыв на CPU runtime
```

Рекомендуемая chat-модель MVP:

```text
qwen2.5:7b-instruct
```

## 7. Ограничение текущей версии

`AnswerValidator` выполняет structural validation:

```text
пустой ответ
наличие sources
наличие ссылок [Sx]
unknown citations
external knowledge markers
answer length
citation density / coverage
```

Не выполняет semantic/factual validation:

```text
поддерживается ли каждое утверждение конкретным source text;
не сделала ли модель спорный вывод из короткого UML/heading/caption chunk;
нет ли semantic hallucination при формально корректных [Sx].
```

Это quality debt. QH-1 не исправляет его напрямую, а создаёт измеримый baseline.

## 8. QH-1 Observability + Eval Baseline

Реализовано:

```text
ChatRunsLogger
chat_runs.jsonl
EvalCase/EvalRunner/EvalReport
scripts/asu_june_bot_chat_eval.py
eval/cases/base.jsonl
eval/golden_answers/*.md
```

Локально нужно проверить:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\observability\test_chat_runs.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\eval\test_checks.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\eval\test_runner.py -q
.\.venv\Scripts\python.exe scripts\asu_june_bot_chat_eval.py --cases eval\cases\base.jsonl --label baseline --model qwen2.5:7b-instruct --top-k 5
```

## 9. Исключения из основного корпуса

В основном project-only corpus не должны попадать технические runtime/system exports:

```text
**/Система/**
**/asu_docs_export/**
**/asu_admin_export/**
**/docs_html/**
**/docs_text/**
**/pages_html/**
**/pages_text/**
**/site_review_runs/**
**/playwright/**
**/exports/**
**/screenshots/**
**/*.har
```

Если такие данные понадобятся, нужен отдельный `system_export_corpus`.

## 10. Активная документация

Главные документы:

```text
README.md
architecture.md
mvp.md
roadmap.md
decisions.md
RUNBOOK_V2.md
todo.md
eval_questions.md
ideas.md
product/
smoke_report_*.md
```

Устаревшие документы и case-conflict материалы не должны оставаться в активной зоне подпроекта.

## 11. Следующие шаги

После локальной проверки QH-1:

```text
1. Проанализировать baseline report.
2. Уточнить eval cases, если они слишком жёсткие или некорректные.
3. Реализовать QH-2 Source Quality Filter.
4. Сравнить eval baseline vs with_source_filter.
5. Реализовать QH-3 Parent Expansion только при необходимости.
6. Подготовить подпроект к выделению в отдельный репозиторий.
```

## 12. Не делать сейчас

```text
не строить UI до baseline eval
не внедрять source filter без baseline
не внедрять parent expansion без анализа QH-2
не подключать DSPy в runtime
не делать LLM-as-judge/NLI до накопления dataset
не делать fine-tuning
не развивать scripts/09_chat.py как основной runtime
не смешивать старый RAG v1 и новый bot v2.1
```
