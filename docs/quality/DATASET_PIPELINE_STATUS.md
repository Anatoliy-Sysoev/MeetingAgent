# Dataset Pipeline Status

Обновлено: 2026-05-19.

## Назначение

Документ фиксирует фактически реализованный pipeline накопления и
разметки запросов для локального RAG/Chat режима MeetingAgent.

Это отдельный quality/evaluation контур. Он не заменяет целевой runtime
Project Knowledge Bot (`src/asu_june_bot/`) и не должен трактовать
`scripts/09_chat.py` как основную архитектуру бота.

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

`scripts/09_chat.py` здесь используется как legacy/prototype-источник
логов для старого project-only baseline. Для целевого Project Knowledge
Bot основной runtime находится в `src/asu_june_bot/` и
`scripts/asu_june_bot_*.py`.

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

## 3. Realistic 100 Dataset

Реализован набор из 100 реалистичных вопросов:

```text
`docs/quality/realistic_100_queries.jsonl`
```

Распределение:

```text
70 project queries
20 boundary / mixed / ambiguous queries
10 out_of_scope queries
```

Модель задаётся в каждой строке dataset:

```text
qwen2.5:7b-instruct  для основной проектной части
qwen3:4b              для boundary-среза
qwen3:8b              для out_of_scope-среза
```

Runner:

```text
`scripts/14_run_realistic_100_eval.py`
```

После PR #8 runner по умолчанию использует quality wrapper:

```text
`scripts/09_chat_quality.py`
```

Это включает `hybrid_vector_lexical` rerank и retrieval diagnostics из
`scripts/rag_retrieval_quality.py`. Для исторического baseline можно передать
`--chat-script scripts/09_chat.py`.

Отчёт runtime:

```text
`data/realistic_100_eval_report.jsonl`
```

## 4. Review Pipeline

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

## 5. Synthetic Smoke Pipeline

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

Realistic 100:

```text
realistic_100_queries.jsonl
        ↓
14_run_realistic_100_eval.py
        ↓
realistic_100_eval_report.jsonl
        ↓
manual review
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
