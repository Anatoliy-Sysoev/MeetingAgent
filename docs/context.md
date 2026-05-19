# Контекст Проекта

Обновлено: 2026-05-19.

## Текущее Состояние

MeetingAgent - приватный GitHub-backed пет-проект и локальный продуктовый репозиторий.

Репозиторий:

- Локальный путь: `%USERPROFILE%\\Desktop\\AI\\MeetingAgent`
- Remote: `https://github.com/Anatoliy-Sysoev/MeetingAgent`
- Видимость: private
- Основная ветка: `main`
- Активная рабочая ветка dataset/eval-подготовки: `claude/model-training-guide-CAfwU`

Продуктовое направление: local-first агент памяти проекта.

Основные сценарии:

- RAG по проектной документации;
- project-only чат с проверяемыми источниками;
- накопление runtime-запросов и regression/eval-кейсов;
- транскрибация встреч;
- генерация memo и протоколов;
- классификация материалов по этапу проекта, ФТТ, задаче и документу.

## Текущее Состояние RAG И Chat MVP

Основной RAG-corpus локально собран и использует стабильный numpy backend.
ChromaDB больше не считается критическим поисковым слоем.

Текущий Project-Only Chatbot MVP:

- `scripts/09_chat.py`;
- retrieval → source filtering → refusal/LLM;
- ответ только по источникам проекта;
- отказ без подтверждённых источников;
- sensitive-запросы блокируются.

Локально подтверждены:

- retrieval smoke;
- compact source output;
- project-only refusals;
- guardrail для mixed/out-of-scope запросов;
- базовый runtime logging.

## Dataset / Feedback Pipeline

На текущей ветке реализован минимальный pipeline накопления датасета и
подготовки regression/eval кейсов.

Документы:

- `docs/quality/QUERY_FEEDBACK_LOOP.md`
- `docs/quality/DATASET_PIPELINE_STATUS.md`

Реализованные компоненты:

| Компонент | Назначение |
| --- | --- |
| `scripts/rag_common.py::append_query_log` | append-only runtime logging |
| `scripts/10_review_queries.py` | подготовка review-срезов |
| `scripts/11_run_synthetic_seed.py` | synthetic retrieval smoke |
| `scripts/12_analyze_seed_report.py` | анализ retrieval smoke |
| `scripts/13_build_eval_candidates.py` | сборка eval candidates |
| `docs/quality/synthetic_seed_queries.jsonl` | synthetic seed dataset |

Pipeline:

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

Важно:

- это не fine-tuning;
- веса LLM не обучаются;
- pipeline используется только для контроля качества retrieval и chat;
- automatic promotion запрещён;
- review остаётся ручным.

## Важные Runtime-Факты

- `run_full_rag.ps1` запускает полную сборку.
- `scripts/03_build_index.py` создаёт chunks и embeddings cache.
- `scripts/05_build_numpy_index.py` собирает numpy-index.
- `scripts/04_query.py` выполняет retrieval.
- `scripts/09_chat.py` выполняет project-only chat.
- `data/numpy_index` используется как основной retrieval backend.
- `data/query_log.jsonl` используется для накопления runtime-запросов.
- Все runtime-данные в `data/` исключены из Git.

## Что Изменилось Недавно

- Реализован append-only runtime logging запросов.
- Реализован review pipeline поверх `query_log.jsonl`.
- Реализован synthetic seed retrieval smoke.
- Реализован markdown-анализ retrieval smoke.
- Реализована подготовка eval candidates из review-разметки.
- Добавлен документ `docs/quality/DATASET_PIPELINE_STATUS.md`.
- Обновлён `docs/quality/QUERY_FEEDBACK_LOOP.md` под фактический pipeline.
- Подтверждено, что dataset pipeline не использует fine-tuning.
- Подтверждено, что synthetic seed не считается golden dataset.
- Подтверждено, что approval regression/eval остаётся ручным.

## Что Осталось

- Накопить первые реальные ~100 запросов.
- Провести ручную разметку review-среза.
- Подготовить первые approved regression cases.
- Улучшить retrieval для ПМИ и aggregation-вопросов.
- Ввести `source_type` metadata.
- Стабилизировать `score_threshold`.
- Подготовить local API `/chat`.
- После стабилизации runtime — переходить к UI и Docker.

## Что Не Делать Сейчас

- Не делать fine-tuning LLM.
- Не подключать DSPy/LangGraph/Dify до стабилизации базового project-only RAG.
- Не считать synthetic seed production-eval.
- Не переносить автоматически плохие ответы в regression.
- Не делать Docker до завершения локального smoke и стабилизации runtime.

## Восстановление Контекста В Новом Треде

```text
Прочитай README.md, AGENTS.md, docs/context.md, docs/todo.md, docs/quality/QUERY_FEEDBACK_LOOP.md, docs/quality/DATASET_PIPELINE_STATUS.md и git log --oneline -10. Восстанови контекст проекта и предложи следующий практический шаг.
```
