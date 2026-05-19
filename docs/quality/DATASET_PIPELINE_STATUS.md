# Dataset Pipeline Status

Обновлено: 2026-05-19.

## Назначение

Документ фиксирует фактически реализованный pipeline накопления и
разметки запросов для локального RAG/Chat режима MeetingAgent.

Важно: это не обучение весов LLM и не fine-tuning. Реализованный
pipeline предназначен для:

- накопления реальных запросов;
- поиска слабых мест retrieval;
- ручной разметки;
- подготовки regression/eval кейсов;
- контроля качества после изменения корпуса и retrieval.

## Что Реализовано

### 1. Runtime Логирование

Реализовано append-only логирование запросов:

- `scripts/rag_common.py::append_query_log`
- `scripts/04_query.py`
- `scripts/09_chat.py`

Лог:

```text
`data/query_log.jsonl`
```

В лог пишутся:

- вопрос;
- top sources;
- retrieval score;
- answer/status;
- runtime params;
- timestamp.

Sensitive-запросы (`.env`, токены, пароли, системные инструкции)
не логируются.

## 2. Synthetic Seed Dataset

Реализован стартовый synthetic dataset:

```text
`docs/quality/synthetic_seed_queries.jsonl`
```

Содержит:

- project queries;
- ambiguous queries;
- out-of-scope queries;
- mixed-scope queries;
- aggregation queries;
- source-quality queries.

Используется как reproducible smoke/regression corpus.

## 3. Review Pipeline

### Подготовка review-среза

```text
`scripts/10_review_queries.py`
```

Создаёт:

```text
`data/query_log_review.jsonl`
```

Поддерживаемые verdict:

- `ok`
- `missing_source`
- `garbage_source`
- `low_score`
- `hallucination`
- `out_of_scope`

### Сборка eval candidates

```text
`scripts/13_build_eval_candidates.py`
```

Создаёт:

```text
`data/eval_candidates.jsonl`
```

Важно:

- candidates != approved eval;
- approval только ручной;
- automatic promotion запрещён.

## 4. Synthetic Smoke Pipeline

### Прогон synthetic seed

```text
`scripts/11_run_synthetic_seed.py`
```

Создаёт:

```text
`data/synthetic_seed_report.jsonl`
```

Поддерживает:

- retrieval-only smoke (`--compact`);
- полный LLM smoke (`--full-llm`).

### Анализ отчёта

```text
`scripts/12_analyze_seed_report.py`
```

Создаёт:

```text
`data/synthetic_seed_summary.md`
```

Анализирует:

- failures;
- categories;
- missing sources;
- low retrieval scores;
- recurring sources.

## Текущий Pipeline

```text
04_query.py / 09_chat.py
        ↓
data/query_log.jsonl
        ↓
10_review_queries.py
        ↓
data/query_log_review.jsonl
        ↓
13_build_eval_candidates.py
        ↓
data/eval_candidates.jsonl
        ↓
manual approval
        ↓
approved regression/eval corpus
```

Synthetic smoke:

```text
synthetic_seed_queries.jsonl
        ↓
11_run_synthetic_seed.py
        ↓
synthetic_seed_report.jsonl
        ↓
12_analyze_seed_report.py
        ↓
synthetic_seed_summary.md
```

## Что НЕ Реализовано

Осознанно не реализованы:

- fine-tuning LLM;
- DSPy;
- LangGraph;
- auto-feedback API;
- automatic eval promotion;
- LLM-as-judge;
- runtime feedback buttons;
- Docker packaging;
- полноценный evaluation framework.

## Что Считается Следующим Этапом

Следующие реалистичные шаги:

1. накопить первые реальные ~100 запросов;
2. выполнить ручную разметку;
3. собрать первые approved regression cases;
4. улучшить retrieval для ПМИ/aggregation;
5. стабилизировать source filtering.

Только после этого:

- local API;
- UI;
- Docker;
- расширенный eval.
