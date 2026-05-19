# Цикл Логирования И Коррекции Запросов

## Назначение

Этот документ описывает процесс улучшения качества ответов на первых
реальных запросах: **логировать → просматривать → размечать →
корректировать**.

Важно: в MeetingAgent нет дообучения весов модели. Эмбеддинги считаются
готовой моделью `bge-m3` через Ollama. «Обучение» здесь — это подстройка
корпуса и параметров retrieval по результатам разметки реальных запросов.
Подробности по сборке индекса: `docs/operations/RAG_PIPELINE.md`.

## Принцип Первых 100 Запросов

Первые реальные запросы дают самую полезную обратную связь: они
показывают реальные формулировки пользователей, слабые типы документов
(ПМИ, агрегирующие вопросы) и пробелы корпуса.

Решение по объёму:

- логируется **каждый** запрос, без жёсткого лимита в коде;
- «первые 100» — это срез на этапе разметки, а не ограничение
  логирования;
- после разбора первой сотни цикл повторяется на следующих срезах.

Логирование реализовано в `scripts/04_query.py` и `scripts/09_chat.py`
через общий помощник `append_query_log` в `scripts/rag_common.py`.
Путь берётся из `paths.query_log` (`config.example.yaml`), по умолчанию
`data/query_log.jsonl`.

## Реализованный Минимальный Pipeline

На текущей ветке реализован минимальный контур накопления датасета и
ручной разметки:

| Артефакт | Назначение | Статус |
| --- | --- | --- |
| `scripts/rag_common.py::append_query_log` | append-only логирование запросов с sensitive-фильтром | готово |
| `scripts/04_query.py` | RAG-запросы и запись retrieval-логов | готово |
| `scripts/09_chat.py` | project-only чат и запись chat-логов | готово |
| `docs/quality/synthetic_seed_queries.jsonl` | стартовый synthetic seed вопросов | готово |
| `scripts/10_review_queries.py` | подготовка `data/query_log_review.jsonl` для ручной разметки | готово |
| `scripts/11_run_synthetic_seed.py` | прогон seed-вопросов через `04_query.py` | готово |
| `scripts/12_analyze_seed_report.py` | markdown-сводка по `synthetic_seed_report.jsonl` | готово |
| `scripts/13_build_eval_candidates.py` | сборка кандидатов eval-кейсов из review-разметки | готово |

Это не framework обучения и не fine-tuning. Это контролируемый контур
качества RAG: логирование, synthetic smoke, ручная разметка, кандидаты в
regression/eval.

## Рабочий Поток На Практике

### 1. Накопить лог реальных запросов

```powershell
.\.venv\Scripts\python.exe scripts\04_query.py "Что входит в Паспорт ИС?" --top-k 8 --compact
.\.venv\Scripts\python.exe scripts\09_chat.py "Что входит в Паспорт ИС?" --json
```

Результат автоматически дописывается в `data/query_log.jsonl`.

### 2. Подготовить первые 100 строк к ручному review

```powershell
.\.venv\Scripts\python.exe scripts\10_review_queries.py --limit 100
```

Результат: `data/query_log_review.jsonl`.

### 3. Разметить review-файл вручную

В поле `review_verdict` указать один из вердиктов:

- `ok`;
- `missing_source`;
- `garbage_source`;
- `low_score`;
- `hallucination`;
- `out_of_scope`.

В поле `review_comment` указать пояснение: какой источник ожидался, какой
мусор попал, где галлюцинация или почему вопрос вне проектного контекста.

### 4. Собрать кандидатов в eval

```powershell
.\.venv\Scripts\python.exe scripts\13_build_eval_candidates.py
```

Результат: `data/eval_candidates.jsonl`.

Кандидаты не считаются утверждённым eval. Их нужно просмотреть вручную и
только после этого переносить в постоянный regression-набор.

### 5. Прогнать synthetic seed

Дешёвый retrieval smoke без генерации LLM:

```powershell
.\.venv\Scripts\python.exe scripts\11_run_synthetic_seed.py --limit 20
```

Полный LLM smoke на малом срезе:

```powershell
.\.venv\Scripts\python.exe scripts\11_run_synthetic_seed.py --limit 10 --full-llm
```

Результат: `data/synthetic_seed_report.jsonl`.

### 6. Построить сводку synthetic seed

```powershell
.\.venv\Scripts\python.exe scripts\12_analyze_seed_report.py
```

Результат: `data/synthetic_seed_summary.md`.

Сводка показывает failures, категории, запросы без источников, низкие
score и часто возвращаемые источники. Это помогает найти мусорные
источники, слабые документы и regression после изменения фильтров.

## Шаг 1. Логирование

Каждый запрос дописывается в `data/query_log.jsonl` (локальный runtime,
исключён из Git, как и остальной `data/`).

Фактическая запись на одну строку (`09_chat.py`):

```json
{
  "ts": "2026-05-18T14:32:43+00:00",
  "source": "09_chat",
  "question": "Что входит в Паспорт ИС?",
  "status": "answered",
  "refusal_reason": null,
  "answer_mode": "llm",
  "confidence": 0.83,
  "top_sources": [
    {"relative_path": "...", "chunk_index": 3, "score": 0.71}
  ],
  "answer": "текст ответа или null при отказе",
  "params": {"top_k": 4, "score_threshold": 0.35, "model": null}
}
```

`04_query.py` пишет тот же формат с полем `mode` (`raw | compact |
llm`) вместо `status`.

Требования (обеспечены кодом в `rag_common.append_query_log`):

- append-only, по одной JSON-строке на запрос, `ts` проставляется
  автоматически;
- sensitive-запросы (`.env`, `config.yaml`, токены, пароли, системные
  инструкции) не логируются никогда — фильтр в `append_query_log` плюс
  отдельная проверка `REFUSAL_SENSITIVE` в `09_chat.py`;
- логирование локально (`data/query_log.jsonl`, исключён из Git) и не
  влияет на ответ пользователю.

## Шаг 2. Просмотр

После накопления первых ~100 строк:

```powershell
.\.venv\Scripts\python.exe scripts\04_query.py "<вопрос из лога>" --top-k 8 --compact
```

Для каждого запроса смотреть:

- релевантность ответа;
- релевантность top-источников;
- пропущенные источники;
- галлюцинации (ответ без опоры на источник);
- мусорные источники (архивы, черновики, backup).

Это те же критерии, что в `docs/quality/EVALUATION_PLAN.md`.

## Шаг 3. Разметка

На каждую запись лога проставляется вердикт:

| Вердикт | Значение |
| --- | --- |
| `ok` | ответ и источники релевантны |
| `missing_source` | релевантный документ есть в проекте, но не попал в выдачу |
| `garbage_source` | в выдаче мусорный/архивный источник |
| `low_score` | релевантный источник есть, но score ниже порога |
| `hallucination` | ответ не опирается на источники |
| `out_of_scope` | вопрос не про проектную документацию |

Разметку вести в `data/query_log_review.jsonl`, который создаётся
скриптом `scripts/10_review_queries.py`. Срез и сводка по вердиктам
фиксируются по образцу `docs/quality/rag_eval_report_template.md`.

## Шаг 4. Коррекция

Действие зависит от преобладающего вердикта:

- `garbage_source` → добавить точечный паттерн в `exclude_path_patterns`
  (процедура в `docs/operations/RAG_PIPELINE.md`, раздел «Процедура
  Настройки Exclude»);
- `missing_source` → проверить, попал ли документ в `data/chunks.jsonl`;
  при необходимости снять лишний exclude или добавить документ в
  проектную папку;
- `low_score` → подобрать `--score-threshold` и `--top-k` на срезе
  запросов, не ломая project-only отказы;
- `hallucination` → ужесточить порог и проверить source-grounding
  ответа;
- стабильные промахи по типу документа (ПМИ, агрегирующие вопросы) →
  завести задачу в `docs/todo.md` на улучшение retrieval, при росте
  корпуса рассмотреть hybrid retrieval (см. `docs/todo.md`).

После правок:

1. Пересобрать индекс: `run_full_rag.ps1`.
2. Прогнать проблемные запросы среза через `04_query.py --compact`.
3. Убедиться, что мусор ушёл, а релевантные источники не потерялись.
4. Значимые правила корпуса зафиксировать в `docs/decisions.md`.
5. Повторить цикл на следующем срезе запросов.

## Накопление Датасета

Датасет здесь — не обучающая выборка для весов LLM, а проверяемый
корпус кейсов для регрессии. Накапливается из четырёх слоёв.

1. **Сырьё: лог запросов** — `data/query_log.jsonl`. Реальные вопросы,
   статус, ответ, top-источники, params. Пишется автоматически из
   `04_query.py` и `09_chat.py`. Это единственный слой, который сейчас
   полностью автоматический.

2. **Ручная разметка** — отдельный `data/query_log_review.jsonl`: на
   запись лога добавляется вердикт из словаря шага 3 и при необходимости
   ожидаемое поведение и ожидаемые источники. Без авторазметки: иначе
   накопим кейсы на мусоре.

3. **Кандидаты eval** — `data/eval_candidates.jsonl`. Формируются
   скриптом `scripts/13_build_eval_candidates.py` из ручной разметки.
   Статус таких записей — только `candidate`, не `approved`.

4. **Утверждённые eval-кейсы** — после ручного review кандидаты
   переносятся рядом с существующими `docs/quality/rag_eval_questions.md`
   и baseline-отчётами (`docs/quality/rag_eval_baseline_clean_2026-05-07.md`).
   Кейс: вопрос, ожидаемый статус, ожидаемые источники, ссылка на исходный
   запрос.

5. **Golden-ответы** — эталонные ответы для ключевых вопросов.
   Используются только для проверки качества ответа, не для дообучения.

Порядок накопления строго ручной на слоях 2–5: запрос → лог (авто) →
срез первых ~100 → разметка → кандидаты → утверждение кейсов → коррекция
корпуса и параметров → повторный прогон. Автоматически переносить плохие
ответы в eval запрещено.

## Граница Процесса

- Это ручной active-learning поверх RAG: меняются корпус, exclude-правила
  и параметры retrieval, а не веса модели.
- Модель эмбеддингов остаётся `bge-m3`; менять её только через
  явную миграцию cache (см. `AGENTS.md`).
- Все рабочие данные (`data/query_log.jsonl`, `data/query_log_review.jsonl`,
  `data/synthetic_seed_report.jsonl`, `data/synthetic_seed_summary.md`,
  `data/eval_candidates.jsonl`) локальные и не коммитятся.
- Synthetic seed — это стартовый smoke/regression material, а не источник
  истины. Его результаты нельзя считать эталоном без ручного review.

## Что Не Делать

- Не дообучать веса LLM на этих данных.
- Не переносить автоматически плохие ответы в eval.
- Не утверждать synthetic seed как golden set без просмотра человеком.
- Не коммитить `data/query_log*.jsonl`, `data/synthetic_seed_report.jsonl`,
  `data/synthetic_seed_summary.md`, `data/eval_candidates.jsonl`.
- Не менять модель эмбеддингов без отдельной миграции cache.
