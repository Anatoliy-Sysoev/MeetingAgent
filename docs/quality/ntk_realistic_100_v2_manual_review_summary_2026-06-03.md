# NTK realistic 100 v2 manual review summary

Дата: 2026-06-03.

Статус: ручная разметка выполнена по файлам:

```text
docs/quality/ntk_realistic_100_v2_eval_review.jsonl
docs/quality/ntk_realistic_100_v2_eval_review_compact.jsonl
```

Разметка опубликована отдельным patch-файлом:

```text
docs/quality/ntk_realistic_100_v2_manual_review_patch.jsonl
```

## Итоговые verdict counts

```text
ok: 36
low_score: 34
bad_refusal: 20
garbage_source: 6
out_of_scope: 3
missing_source: 1
```

## Status x verdict

```text
answered / ok: 31
answered / low_score: 8
clarify / bad_refusal: 20
no_answer / garbage_source: 6
no_answer / low_score: 26
no_answer / missing_source: 1
refused / ok: 4
refused / out_of_scope: 3
validation_failed / ok: 1
```

## Scope x verdict

```text
project / ok: 32
project / low_score: 34
project / bad_refusal: 17
project / garbage_source: 6
project / missing_source: 1
out_of_scope / out_of_scope: 3
out_of_scope / bad_refusal: 3
harmful_security / ok: 4
```

## Вывод

Технический прогон успешен:

```text
rows: 100/100
returncode=0: 100/100
parse_errors: 0
failures: 0
```

Quality-pass не подтверждён.

Основные дефекты:

```text
1. bad_refusal / false clarify — 20 кейсов.
   В том числе 17 проектных вопросов и 3 нейтральных out-of-scope вопроса, которые должны были получить refused.

2. low_score — 34 кейса.
   Чаще всего это false no_answer при частично релевантных источниках или слабая генерация по найденным фрагментам.

3. garbage_source — 6 кейсов.
   Retrieval поднимает нерелевантные источники, например ФТТ про опыт исполнителя вместо операций с замечанием.

4. missing_source — 1 кейс.
   По Паспорту ИС не найден явный источник по эксплуатации/поддержке.
```

## Приоритетные buckets для исправления

### P0/P1. False clarify по проектным вопросам

Цель: проектные вопросы не должны останавливаться на guard/clarify до retrieval.

Кейсы:

```text
NTK100-V2-009
NTK100-V2-011
NTK100-V2-015
NTK100-V2-021
NTK100-V2-023
NTK100-V2-027
NTK100-V2-048
NTK100-V2-053
NTK100-V2-054
NTK100-V2-061
NTK100-V2-065
NTK100-V2-067
NTK100-V2-073
NTK100-V2-080
NTK100-V2-083
NTK100-V2-086
NTK100-V2-090
```

Кандидат на fix:

```text
src/asu_june_bot/guardrails/scope_classifier.py
```

Нужны project markers для:

```text
инспекционные документы
подписание и хранение инспекционных документов
статусы замечаний
роли фиксации и контроля устранения
продуктивный контур
очереди сообщений / обмен событиями
резервное копирование / восстановление
проверки формирования и подписания предписания
входные данные / ожидаемые результаты сценариев
действия администратора / развертывание
сервисные учетные записи / права доступа
входной контроль материалов и оборудования
исполнительная документация: статусы, доступ, ограничения
централизованное хранилище логов
трассировка / связь событий между сервисами
```

### P1. out_of_scope false clarify

Кейсы:

```text
NTK100-V2-093
NTK100-V2-095
NTK100-V2-096
```

Ожидание:

```text
status = refused
scope = out_of_scope
retrieval_called = false
```

Нужны generic markers:

```text
туристический маршрут
история / историческая справка
музыка / подбор музыки
```

### P1. FTT / PR / testing false no_answer and weak retrieval

Кейсы с высоким приоритетом:

```text
NTK100-V2-001..008
NTK100-V2-014
NTK100-V2-017..020
NTK100-V2-047
NTK100-V2-049
NTK100-V2-051..052
```

Типовые причины:

```text
- retrieval поднимает частично релевантные фрагменты, но LLM отвечает no_answer;
- routing для ФТТ и ПР не различает операции с замечанием, карточки, файлы, справочники, доступ, экранные формы;
- testing-вопросы часто уходят в ПР/ФТТ вместо ПМИ/СФТ/СНТ.
```

### P1. Admin/security/operations audit

Кейсы:

```text
NTK100-V2-062
NTK100-V2-063
NTK100-V2-066
NTK100-V2-068
NTK100-V2-088
NTK100-V2-089
```

Причины:

```text
- слабые или общие sources;
- false no_answer по частично релевантным источникам;
- нужен routing к Руководству администратора, ИБ, эксплуатации, мониторингу, логированию и СоИ.
```

### P2. MTO / Executive docs

Кейсы:

```text
NTK100-V2-071
NTK100-V2-072
NTK100-V2-074
NTK100-V2-078
NTK100-V2-079
NTK100-V2-081
```

Причины:

```text
- MTO questions sometimes route to generic CTA or wrong role sources;
- Executive docs questions often find only high-level process names, then answer no_answer.
```

## Следующий рекомендуемый шаг

Начать с bucket:

```text
False clarify по проектным вопросам + out_of_scope false clarify
```

Почему:

```text
1. Это guard/scope слой, правится быстрее, чем retrieval.
2. Он блокирует retrieval полностью.
3. После исправления этих 20 bad_refusal кейсов можно повторить targeted eval и получить более честную картину retrieval/answer quality.
```

## Runtime / source files

Runtime review-файлы не менять вручную без merge script. Patch-файл содержит только:

```text
eval_id
scope
category
status
review_verdict
review_comment
```

Для переноса разметки в полный review-файл нужно выполнить локальный merge по `eval_id`.
