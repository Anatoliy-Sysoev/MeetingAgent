# Roadmap Project Knowledge Bot

Обновлено: 2026-05-16.

## 1. Принцип roadmap

Развитие идёт от качества project-only контура, а не от UI и не от выбора модели:

```text
источники -> extraction -> chunks -> index -> guarded search -> context -> chat -> eval -> quality hardening -> docker packaging -> UI -> deployment
```

Любое изменение retrieval/context/LLM должно иметь проверку на baseline cases.

Docker-упаковка начинается только после QH-5, когда качество `/chat`, документация и smoke/regression-контур стабилизированы.

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
Этап 10. QH-4 Semantic Warnings / Manual Labels      После QH-2/QH-3
Этап 11. QH-5 Release Stabilization                  Перед Docker
Этап 12. Docker Packaging                            После QH-5
Этап 13. UI / OpenWebUI adapter                      После Docker или параллельно после quality baseline
Этап 14. GPU migration path                          Позже
Этап 15. Enterprise-hardening                        Позже
Этап 16. Выделение в отдельный репозиторий           После Docker и стабилизации документации
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

## 13. Этап 10. QH-4 Semantic Warnings / Manual Labels

Статус:

```text
Позже, после анализа QH-2/QH-3
```

Цель: добавить предупреждения по качеству ответа без hard-fail semantic validation.

Состав:

```text
manual_label / manual_issue в chat_runs.jsonl
offline review flow
semantic_warnings в diagnostics
low-overlap / weak-source warnings как warning, не validation_failed
```

Не делать в QH-4:

```text
LLM-as-judge как runtime dependency
NLI hard-fail
fine-tuning
```

## 14. Этап 11. QH-5 Release Stabilization

Статус:

```text
Перед Docker
```

Цель: заморозить минимально стабильный контур продукта перед упаковкой.

Критерии готовности QH-5:

```text
QH-1 baseline report создан
QH-2 результат сравнен с baseline
QH-3 выполнен или явно отменён как ненужный
QH-4 warnings/manual labels либо реализованы, либо перенесены в backlog
regression tests проходят
API /health /search /chat проходят smoke
README / architecture / mvp / roadmap / runbook синхронизированы
runtime paths и config приведены к относительным/portable defaults
секреты и локальные пути не попадают в Git
```

## 15. Этап 12. Docker Packaging

Статус:

```text
Запланирован после QH-5
```

Цель: упаковать Project Knowledge Bot для воспроизводимого запуска одной командой.

Минимальный состав:

```text
Dockerfile
.dockerignore
docker-compose.yml
.env.example
config.docker.example.yaml
docs/deployment/docker.md
scripts/docker_smoke.ps1 или docs smoke-команды
```

Первый docker-compose должен поднимать:

```text
bot-api
```

Ollama на первом шаге допускается запускать вне Docker на хосте Windows:

```text
Ollama host runtime -> bot-api container через host.docker.internal
```

Вторым шагом можно добавить optional profile:

```text
ollama service в docker-compose
```

Volume policy:

```text
./data:/app/data
./eval:/app/eval
./config.yaml:/app/config.yaml:ro
```

Критерии готовности Docker stage:

```text
docker compose up --build запускает bot-api
GET /health работает из хоста
POST /search работает
POST /chat работает при доступной Ollama
chat_runs.jsonl пишется в host volume
runtime data не пишется внутрь ephemeral container layer
```

## 16. Этап 13. UI / OpenWebUI adapter

Статус:

```text
Позже
```

Условие старта:

```text
/search и /chat стабильны
baseline eval понятен
качество источников улучшено
Docker или локальный API запуск воспроизводим
```

Варианты:

```text
OpenWebUI как оболочка
минимальный web client
CLI-first продолжение
```

## 17. Этап 14. GPU migration path

Статус:

```text
Позже
```

Цель: заменить локальный CPU/Ollama inference на GPU backend без переписывания бота.

Требование:

```text
LLMClient остаётся OpenAI-compatible adapter
```

## 18. Этап 15. Enterprise-hardening

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

## 19. Этап 16. Выделение в отдельный репозиторий

Статус:

```text
Планируется после Docker
```

Условия:

```text
активная документация синхронизирована
устаревшие материалы перенесены в archive
README готов как корневой README нового repo
Docker запуск воспроизводим
runtime paths независимы от MeetingAgent
package name и product name согласованы
```

## 20. Не делать сейчас

```text
не строить UI до baseline eval
не внедрять source filter без baseline
не внедрять parent expansion без source filter comparison
не подключать DSPy в runtime
не делать LLM-as-judge/NLI до накопления dataset
не делать fine-tuning
не развивать scripts/09_chat.py как основной runtime
не смешивать старый MeetingAgent RAG v1 и bot v2.1
не делать Docker до QH-5 release stabilization
```
