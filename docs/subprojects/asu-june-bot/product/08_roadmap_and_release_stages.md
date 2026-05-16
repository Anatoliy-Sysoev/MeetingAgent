# 08. Дорожная карта и этапы релизов

Обновлено: 2026-05-16.

## Принцип roadmap

Roadmap строится не вокруг добавления AI-фич, а вокруг последовательного усиления продукта:

1. надежный корпус;
2. надежный retrieval;
3. project-only guard;
4. Search API;
5. Chat API;
6. observability и eval baseline;
7. улучшение качества sources/context;
8. UI;
9. аналитические сценарии;
10. эксплуатационное усиление.

## Этапы продукта

### P0. Product Foundation

Цель:

```text
отделить Project Knowledge Bot как самостоятельный продуктовый контур
описать vision, scope, roadmap, MVP и требования
```

Статус:

```text
Закрыт, документация актуализируется
```

Артефакты:

```text
README
product package
decisions
technical architecture
MVP/FTT
runbook
```

### P1. Reliable Search Product Core

Цель:

```text
собрать очищенный project-only corpus
построить retrieval core
зафиксировать search quality
поставить guard перед retrieval
```

Состав:

```text
extraction/chunking v2.1
embeddings/index v2
search quality v2.2
ProjectGuard v2
```

Статус:

```text
Закрыт
```

### P2. Search API MVP

Цель:

```text
сделать reusable API-слой поверх готового retrieval core
```

Состав:

```text
SearchService
GET /health
POST /search
API smoke report
```

Критерии:

```text
project query -> status ok + context
refused/clarify -> retrieval не вызывается
response format стабилен для будущего UI и chat
```

Статус:

```text
Закрыт
```

### P3. Chat API MVP

Цель:

```text
добавить project-only chat поверх подготовленного context
```

Состав:

```text
ChatService
PromptBuilder
LLMClient
AnswerValidator
ResponseFormatter
CLI chat
POST /chat
API smoke report
```

Правило:

```text
не отправлять raw top-k напрямую в LLM
чат опирается только на curated context
refused/clarify не вызывают LLM
```

Статус:

```text
Закрыт с ограничениями
```

Ограничение:

```text
semantic/factual validation не входит в MVP как hard-fail
```

### P4. Quality Hardening 1 — Observability + Eval Baseline

Цель:

```text
накопить измеримый baseline качества до изменения retrieval/context
```

Состав:

```text
ChatRunsLogger
chat_runs.jsonl
EvalRunner
eval/cases/base.jsonl
golden answer placeholders
JSON/Markdown reports
```

Статус:

```text
Реализован, ожидает локальный baseline-прогон
```

### P5. Quality Hardening 2 — Source Quality Filter

Цель:

```text
снизить риск, что короткие UML/heading/caption chunks становятся primary evidence
```

Статус:

```text
Открыт после baseline
```

Принцип:

```text
не удалять chunks из индекса
помечать weak_source
понижать primary eligibility
фиксировать reason в diagnostics
сравнивать eval до/после
```

### P6. Quality Hardening 3 — Parent Expansion

Цель:

```text
добавлять контекст родительского section/parent chunk для коротких, но потенциально полезных chunks
```

Статус:

```text
Открыт после QH-2 при необходимости
```

Ограничения:

```text
strict max chars
dedup parent context
не расширять все подряд
не превышать PromptBuilder budget
```

### P7. Team Adoption Surface

Цель:

```text
дать удобную точку входа для повседневного использования
```

Состав:

```text
web panel или OpenWebUI adapter
понятный search/chat UX
стандартизированный ответ с sources/citations
готовые сценарии для команды
```

Статус:

```text
Не начат
```

Условие старта:

```text
baseline eval выполнен
качество sources/context стабилизировано
```

### P8. Cross-Document Analyst Mode

Цель:

```text
перейти от "найди ответ" к "сопоставь артефакты и объясни расхождения"
```

Состав:

```text
traceability между требованиями, архитектурой, проектными решениями, интеграциями и испытаниями
document comparison
analyst flows
richer diagnostics
```

Статус:

```text
Позже
```

### P9. Meeting Memory Integration

Цель:

```text
связать память документов с памятью встреч
```

Состав:

```text
подключение meeting artifacts
поиск по решениям, задачам, рискам
связка discussion -> formal docs
```

Статус:

```text
Позже
```

### P10. Enterprise Readiness

Цель:

```text
подготовить продукт к более широкой эксплуатации
```

Состав:

```text
RBAC по источникам
audit logs
job queue для reindex
GPU/vLLM runtime profiles
monitoring dashboards
multi-user mode
```

Статус:

```text
Позже
```

### P11. Separate Repository

Цель:

```text
выделить Project Knowledge Bot в отдельный проект с собственной документацией
```

Условия:

```text
активная документация синхронизирована
устаревшие документы архивированы
README готов как root README
runtime paths независимы от MeetingAgent
package/product naming согласованы
```

Статус:

```text
Планируется
```

## Релизы

### Release 0.1

```text
Reliable local search core
```

Статус: закрыт.

### Release 0.2

```text
API Search MVP
```

Статус: закрыт.

### Release 0.3

```text
Project-only Chat MVP
```

Статус: закрыт с ограничениями.

### Release 0.4

```text
Observability + Eval Baseline
```

Статус: реализован, ожидает локальный baseline-прогон.

### Release 0.5

```text
Source Quality Filter + measured improvement
```

Статус: следующий.

### Release 0.6

```text
Parent Expansion / context quality hardening
```

Статус: условный.

### Release 0.7

```text
Рабочая UI-оболочка
```

Статус: позже.

## Что не должно сломать roadmap

- ранний уход в UI раньше стабильного quality baseline;
- ранняя замена ядра на тяжелую внешнюю платформу;
- попытка добавить все и сразу;
- смешивание старого RAG/runtime и нового bot runtime;
- подмена продуктовой пользы красивой демонстрацией модели;
- внедрение source filter или parent expansion без сравнения с baseline.

## Как понимать приоритеты

Приоритет выше у того, что:

1. повышает надежность;
2. повышает проверяемость;
3. сокращает рабочее время пользователя;
4. делает следующий слой продукта возможным;
5. измеримо улучшает baseline.

Поэтому порядок:

```text
Search -> API -> Chat -> Eval -> Source Quality -> UI -> Traceability -> Meeting Integration
```

является архитектурно и продуктово обоснованным.
