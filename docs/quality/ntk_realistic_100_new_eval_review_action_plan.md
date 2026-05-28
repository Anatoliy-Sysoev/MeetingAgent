# NTK realistic 100 new — action plan after manual review

Дата: 2026-05-28.

Источник:

```text
docs/quality/ntk_realistic_100_new_eval_review_filled.jsonl
docs/quality/ntk_realistic_100_new_eval_review_manual_summary.json
```

## Итог

```text
total: 100
ok: 34
missing_source: 27
low_score: 23
bad_refusal: 8
needs_clarification: 4
garbage_source: 2
out_of_scope: 2
hallucination: 0
```

Главный вывод: eval-runner стабилен, но quality gate не пройден по retrieval/routing/guard. Основной дефект — не генерация ответа, а выбор источников и неверная маршрутизация проектных вопросов.

## P0

### project_scope_clarify_or_sensitive_guard

Статус: закрыто 2026-05-28.

Отчет targeted eval:

```text
docs/quality/ntk_realistic_100_new_p0_project_scope_guard_eval_2026-05-28.md
```

Кейсы:

```text
NTK100-NEW-071
NTK100-NEW-073
NTK100-NEW-077
NTK100-NEW-079
NTK100-NEW-080
NTK100-NEW-085
NTK100-NEW-086
NTK100-NEW-090
```

Цель:

```text
Проектные вопросы не должны уходить в clarify.
Вопросы про пароли/секреты должны hard-refuse без retrieval/LLM.
```

Проверка:

```text
targeted bucket eval -> 8/8 expected behavior
guard regression -> 65/65 passed
pytest guard slice -> 68 passed
```

## P1

### CTA missing_source

Кейсы:

```text
NTK100-NEW-025
NTK100-NEW-026
NTK100-NEW-027
NTK100-NEW-028
```

Цель: запросы по PostgreSQL, MinIO, Kubernetes и инфраструктуре должны поднимать релевантные ЦТА chunks, а не уходить в таблицы логирования.

### PR missing_source

Кейсы:

```text
NTK100-NEW-014
NTK100-NEW-016
NTK100-NEW-019
NTK100-NEW-020
```

Цель: вопросы по ПР СМР должны поднимать процессные/ролевые chunks ПР, а не слабые или мусорные источники.

### NSI regulation/reference

Кейсы:

```text
NTK100-NEW-053
NTK100-NEW-054
NTK100-NEW-055
NTK100-NEW-056
NTK100-NEW-057
NTK100-NEW-059
```

Цель: routing к Методика/Регламент НСИ, реестрам и атрибутным составам должен быть сильнее коротких registry/note chunks.

### Passport

Кейсы:

```text
NTK100-NEW-063
NTK100-NEW-064
NTK100-NEW-065
```

Цель: запросы по паспорту ИС должны поднимать паспортные chunks, а не соседние сдачные документы.

### AD/app_ccpm

Кейсы:

```text
NTK100-NEW-036
NTK100-NEW-039
NTK100-NEW-040
```

Цель: mapping `app_ccpm_ul_cc_01/02/03` должен стабильно попадать в primary/supporting sources.

## P2

### out_of_scope clarify instead of refused

Кейсы:

```text
NTK100-NEW-093
NTK100-NEW-094
NTK100-NEW-095
NTK100-NEW-096
```

Цель: растения, медицина, shopping и Chrome должны получать `refused`, а не `clarify`.

## Правило работы

Каждый bucket исправлять отдельным коммитом:

```text
1. Воспроизвести текущий failure.
2. Внести минимальный routing/guard/retrieval fix.
3. Запустить targeted bucket eval.
4. После P0/P1 серии запустить полный realistic-100.
5. Обновить summary и todo.
```
