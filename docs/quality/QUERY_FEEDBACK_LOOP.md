# Query Feedback Loop

## Назначение

Документ описывает ручной feedback/eval pipeline для локального RAG/Chat контура MeetingAgent.

Pipeline предназначен для:

- анализа retrieval;
- поиска слабых запросов;
- накопления regression dataset;
- стабилизации качества ответов.

Pipeline не выполняет fine-tuning модели.

## Граница Контуров

В репозитории одновременно существуют:

1. Project Knowledge Bot v2 (`src/asu_june_bot/`)
2. baseline RAG/Chat prototype (`scripts/04_query.py`, `scripts/09_chat.py`)

Feedback loop относится ко второму контуру.

Для bot runtime (`src/asu_june_bot`) pipeline пока используется как вспомогательный источник evaluation-кейсов.

## Основные Артефакты

### Runtime Logs

```text
data/query_log.jsonl
```

Содержит:

- query;
- retrieval sources;
- scores;
- timestamps;
- runtime metadata.

### Review Dataset

```text
data/query_log_review.jsonl
```

Создаётся:

```text
scripts/10_review_queries.py
```

### Eval Candidates

```text
data/eval_candidates.jsonl
```

Создаётся:

```text
scripts/13_build_eval_candidates.py
```

### Synthetic Dataset

```text
docs/quality/synthetic_seed_queries.jsonl
```

Runner:

```text
scripts/11_run_synthetic_seed.py
```

Analyzer:

```text
scripts/12_analyze_seed_report.py
```

## Review Workflow

```text
runtime query
    ↓
query_log.jsonl
    ↓
manual review
    ↓
query_log_review.jsonl
    ↓
filtered candidates
    ↓
eval_candidates.jsonl
    ↓
manual approval
    ↓
regression corpus
```

## Review Категории

Поддерживаются verdict:

| Verdict | Смысл |
| --- | --- |
| ok | retrieval корректен |
| missing_source | нужный источник не найден |
| garbage_source | нерелевантный источник |
| low_score | retrieval слабый |
| hallucination | ответ не основан на источниках |
| out_of_scope | запрос вне домена |

## Ограничения

Не реализовано:

- RLHF;
- automatic ranking;
- online learning;
- fine-tuning;
- auto retraining;
- auto approval.

Все approval выполняются вручную.

## Текущий Статус

Pipeline находится в manual-active-learning режиме.

Основная цель:

- стабилизировать retrieval;
- накопить regression cases;
- подготовить reproducible evaluation.

Docker/staging/deployment не являются частью данного этапа.
