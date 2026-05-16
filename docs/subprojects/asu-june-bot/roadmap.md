# Roadmap Project Knowledge Bot

Обновлено: 2026-05-16.

## 1. Принцип roadmap

Развитие идёт от качества project-only контура, а не от UI и не от выбора модели:

```text
источники -> extraction -> chunks -> index -> guarded search -> context -> chat -> eval -> quality hardening -> UI -> deployment
```

Любое изменение retrieval/context/LLM должно иметь проверку на baseline cases.

## 2. Сводный статус этапов

```text
Этап 0. Архитектурное отделение подпроекта          Закрыт
Этап 1. Corpus v2.1                                  Закрыт
Этап 2. Index/Search v2                              Закрыт
Этап 3. Search Quality v2.2                          Закрыт
Этап 4. ProjectGuard v2                              Закрыт
Этап 5. SearchService + API Search MVP               Закрыт
Этап 6. ChatService + CLI/API Chat MVP               Закрыт с ограничениями
Этап 7. QH-1 Observability + Eval Baseline           Реализован, ожидает локальный baseline-прогон
Этап 8. QH-2 Source Quality Filter                   Следующий после baseline
Этап 9. QH-3 Parent Expansion                        После QH-2 при необходимости
Этап 10. UI / OpenWebUI adapter                      После quality baseline
Этап 11. GPU migration path                          Позже
Этап 12. Enterprise-hardening                        Позже
Этап 13. Выделение в отдельный репозиторий           После стабилизации документации и MVP
```

## 3. Этап 0. Архитектурное отделение подпроекта

Статус:

```text
Закрыт
```

Цель: отделить проектного AI-бота от общего MeetingAgent и остановить разрастание старого `scripts/09_chat.py`.

Артефакты:

```text
README.md
context.md
decisions.md
architecture.md
mvp.md
roadmap.md
todo.md
eval_questions.md
ideas.md
RUNBOOK_V2.md
product/
```

Решение: `scripts/09_chat.py` считается legacy/prototype. Целевой runtime находится в `src/asu_june_bot/` и `scripts/asu_june_bot_*.py`.

## 4. Этап 1. Corpus v2.1

Статус:

```text
Закрыт
```

Результаты:

```text
extract_text_v2
blocks.jsonl
DOCX/XLSX/PDF/PPTX/HTML/text parsing
exclude rules для system exports/temp files
source audit
```

Критерий готовности:

```text
документы извлекаются без mojibake
технические выгрузки исключены
blocks_v2 сформирован
```

## 5. Этап 2. Index/Search v2

Статус:

```text
Закрыт
```

Результаты:

```text
chunks_v2 = 31302
indexed_chunks = 31285
embedding_model = bge-m3
numpy_index_v2
BM25
hybrid search
health_v2
```

Критерий готовности:

```text
health_v2 status = ok
vector_ready = true
bm25_ready = true
```

## 6. Этап 3. Search Quality v2.2

Статус:

```text
Закрыт
```

Результаты:

```text
QueryIntent
PostReranker
ContextBuilder
primary_sources
supporting_sources
excluded_sources
```

Критерий готовности:

```text
/search возвращает не raw top-k, а подготовленный context
```

## 7. Этап 4. ProjectGuard v2

Статус:

```text
Закрыт
```

Результаты:

```text
pre-retrieval guard
segmenter
scope classifier
aggregator
policy
regression cases
```

Критерии:

```text
false_allow = 0
refused -> retrieval_called=false
clarify -> retrieval_called=false
mixed-scope -> refused
project + unknown tail -> refused
```

## 8. Этап 5. SearchService + API Search MVP

Статус:

```text
Закрыт
```

Результаты:

```text
SearchService
GET /health
POST /search
API Search smoke report
```

Критерии:

```text
GET /health -> ok
project /search -> ok + context
out-of-project /search -> refused without retrieval
```

## 9. Этап 6. ChatService + CLI/API Chat MVP

Статус:

```text
Закрыт с ограничениями
```

Результаты:

```text
ChatService
PromptBuilder
LLMClient
OllamaOpenAIClient
AnswerValidator
ResponseFormatter
scripts/asu_june_bot_chat.py
POST /chat
API Chat smoke report
```

Рабочая модель:

```text
qwen2.5:7b-instruct
```

Ограничение:

```text
structural validation есть
semantic/factual validation отсутствует
```

## 10. Этап 7. QH-1 Observability + Eval Baseline

Статус:

```text
Реализован в коде, ожидает локальный baseline-прогон
```

Результаты:

```text
ChatRunsLogger
chat_runs.jsonl
eval/cases/base.jsonl
scripts/asu_june_bot_chat_eval.py
eval report JSON/Markdown
golden answer placeholders
```

Критерии:

```text
chat_runs.jsonl пишется
baseline eval запускается
reports создаются
deterministic checks работают без LLM-as-judge
```

## 11. Этап 8. QH-2 Source Quality Filter

Статус:

```text
Открыт
```

Условие старта:

```text
после анализа baseline report
```

Цель: снизить риск, что короткие UML/heading/caption chunks становятся primary evidence для широкого вывода.

Принцип:

```text
не удалять chunks из индекса
помечать weak_source
понижать primary eligibility на этапе context building
фиксировать reason в diagnostics
сравнивать eval до/после
```

Артефакты:

```text
src/asu_june_bot/retrieval/source_quality.py
tests/asu_june_bot/retrieval/test_source_quality.py
smoke/eval report with_source_filter
```

## 12. Этап 9. QH-3 Parent Expansion

Статус:

```text
Открыт после QH-2 при необходимости
```

Цель: расширять контекст для слабых коротких chunks до родительского section/parent chunk.

Ограничения:

```text
strict max chars
dedup parent context
не расширять все подряд
не превышать PromptBuilder budget
```

## 13. Этап 10. UI / OpenWebUI adapter

Статус:

```text
Позже
```

Условие старта:

```text
/search и /chat стабильны
baseline eval понятен
качество источников улучшено
```

Варианты:

```text
OpenWebUI как оболочка
минимальный web client
CLI-first продолжение
```

## 14. Этап 11. GPU migration path

Статус:

```text
Позже
```

Цель: заменить локальный CPU/Ollama inference на GPU backend без переписывания бота.

Требование:

```text
LLMClient остаётся OpenAI-compatible adapter
```

## 15. Этап 12. Enterprise-hardening

Статус:

```text
Позже
```

Состав:

```text
RBAC по источникам
audit logs
source-level access control
secrets detection
SIEM/export logs
job queue для reindex
monitoring dashboards
multi-user mode
```

## 16. Этап 13. Выделение в отдельный репозиторий

Статус:

```text
Планируется
```

Условия:

```text
активная документация синхронизирована
устаревшие материалы перенесены в archive
README готов как корневой README нового repo
runtime paths независимы от MeetingAgent
package name и product name согласованы
```

## 17. Не делать сейчас

```text
не строить UI до baseline eval
не внедрять source filter без baseline
не внедрять parent expansion без source filter comparison
не подключать DSPy в runtime
не делать LLM-as-judge/NLI до накопления dataset
не делать fine-tuning
не развивать scripts/09_chat.py как основной runtime
не смешивать старый MeetingAgent RAG v1 и Asu Bot v2.1
```
