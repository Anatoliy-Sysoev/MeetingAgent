# NTK realistic 100 v2 eval status — 2026-06-02

## Статус

Прогон `NTK realistic 100 v2` завершен штатно.

```text
dataset: docs/quality/ntk_realistic_100_v2_queries_2026-06-02.jsonl
report: docs/quality/ntk_realistic_100_v2_eval_report.jsonl
review: docs/quality/ntk_realistic_100_v2_eval_review.jsonl
summary: docs/quality/ntk_realistic_100_v2_eval_review_summary.json
model: qwen2.5:7b-instruct
mode: hybrid
active_corpus: ntk
```

## Итоги прогона

```text
rows: 100/100
returncode=0: 100/100
parse_errors: 0
failures: 0
```

## Распределение по scope

```text
project: 90
out_of_scope: 6
harmful_security: 4
```

## Runtime statuses

```text
answered: 39
no_answer: 33
clarify: 20
refused: 7
validation_failed: 1
```

## Время

```text
avg_duration_sec: 84.463
max_duration_sec: 300.377
min_duration_sec: 0.676
```

## Вывод

Технически прогон успешен: все 100 кейсов обработаны, ошибок парсинга и failures нет.

Качество пока не оценено вручную. Файл `docs/quality/ntk_realistic_100_v2_eval_review.jsonl` подготовлен для ручной разметки полей:

```text
review_verdict
review_comment
```

До ручной разметки этот прогон нельзя считать quality-pass или quality-fail по смысловому качеству ответов.

## Следующий шаг

1. Заполнить `review_verdict` и `review_comment`.
2. Сформировать manual summary.
3. Выделить bucket'ы дефектов: false no_answer, false clarify, weak retrieval, validation_failed, false/refused behavior.
4. Исправлять только targeted bucket'ами с повторным targeted rerun.
