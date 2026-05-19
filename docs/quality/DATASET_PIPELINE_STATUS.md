# Dataset Pipeline Status

Обновлено: 2026-05-19.

## Назначение

Документ фиксирует фактически реализованный pipeline накопления и разметки запросов для общего локального RAG/Chat режима MeetingAgent.

Важно: это не обучение весов LLM и не fine-tuning. Реализованный pipeline предназначен для:

- накопления реальных запросов;
- поиска слабых мест retrieval;
- ручной разметки;
- подготовки regression/eval кейсов;
- контроля качества после изменения корпуса и retrieval.

## Граница Применения

В репозитории есть два разных контура:

| Контур | Основной runtime | Назначение |
| --- | --- | --- |
| Project Knowledge Bot v2.1/v2.2 | `src/asu_june_bot/`, `scripts/asu_june_bot_*.py`, `data/asu_june_bot/*` | Целевой bot runtime: `/search`, `/chat`, Web UI, Telegram, QH-1..QH-5 |
| MeetingAgent v1 / baseline RAG | `scripts/04_query.py`, `scripts/09_chat.py`, `data/query_log.jsonl` | Общий RAG/Chat prototype и dataset feedback pipeline |

`scripts/09_chat.py` не является основным runtime Project Knowledge Bot. Для подпроекта бота целевой runtime — `src/asu_june_bot/` и `scripts/asu_june_bot_*.py`.

## Что Реализовано

### 1. Runtime Логирование

Реализовано append-only логирование запросов общего RAG/Chat prototype:

- `scripts/rag_common.py::append_query_log`
- `scripts/04_query.py`
- `scripts/09_chat.py`

Лог:

```text
data/query_log.jsonl
```

В лог пишутся:

- вопрос;
- top sources;
- retrieval score;
- answer/status;
- runtime params;
- timestamp.

Sensitive-запросы (`.env`, токены, пароли, системные инструкции) не логируются.

### 2. Synthetic Seed Dataset

Реализован стартовый synthetic dataset:

```text
docs/quality/synthetic_seed_queries.jsonl
```

Содержит:

- project queries;
- ambiguous queries;
- out-of-scope queries;
- mixed-scope queries;
- aggregation queries;
- source-quality queries.

Используется как reproducible smoke/regression corpus для общего RAG/Chat prototype.

### 3. Review Pipeline

Подготовка review-среза:

```text
scripts/10_review_queries.py
```

Создаёт:

```text
data/query_log_review.jsonl
```

Поддерживаемые verdict:

- `ok`
- `missing_source`
- `garbage_source`
- `low_score`
- `hallucination`
- `out_of_scope`

Сборка eval candidates:

```text
scripts/13_build_eval_candidates.py
```

Создаёт:

```text
data/eval_candidates.jsonl
```

Важно:

- candidates != approved eval;
- approval только ручной;
- automatic promotion запрещён.

### 4. Synthetic Smoke Pipeline

Прогон synthetic seed:

```text
scripts/11_run_synthetic_seed.py
```

Создаёт:

```text
data/synthetic_seed_report.jsonl
```

Поддерживает:

- retrieval-only smoke (`--compact`);
- полный LLM smoke (`--full-llm`).

Анализ отчёта:

```text
scripts/12_analyze_seed_report.py
```

Создаёт:

```text
data/synthetic_seed_summary.md
```

Анализирует:

- failures;
- categories;
- missing sources;
- low retrieval scores;
- recurring sources.

### 5. Realistic 100 Query Dataset

Дополнительно подготовлен набор реалистичных вопросов:

```text
docs/quality/realistic_100_queries.jsonl
```

И runner:

```text
scripts/14_run_realistic_100_eval.py
```

Назначение:

- прогнать 100 разнородных вопросов;
- зафиксировать модель на каждый вопрос;
- замерить длительность каждого запроса;
- получить `data/realistic_100_eval_report.jsonl`;
- затем пройти полный lifecycle review → candidates → approved regression.

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

Realistic 100 smoke:

```text
realistic_100_queries.jsonl
        ↓
14_run_realistic_100_eval.py
        ↓
realistic_100_eval_report.jsonl
        ↓
manual review / candidate generation
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

Для общего RAG/Chat dataset pipeline:

1. прогнать realistic 100 questions;
2. собрать `data/query_log.jsonl` и `data/realistic_100_eval_report.jsonl`;
3. выполнить ручную разметку;
4. собрать первые approved regression cases;
5. улучшить retrieval для ПМИ/aggregation;
6. стабилизировать source filtering.

Для Project Knowledge Bot:

1. завершить Telegram smoke;
2. выполнить final QH gate;
3. после QH-5 passed перейти к Docker stage.
