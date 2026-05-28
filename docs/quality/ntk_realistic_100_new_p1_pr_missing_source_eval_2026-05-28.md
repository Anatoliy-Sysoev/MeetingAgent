# NTK realistic-100 new P1 targeted eval: PR missing_source

Дата: 2026-05-28.

Bucket:

```text
PR missing_source
```

Кейсы:

```text
NTK100-NEW-014
NTK100-NEW-016
NTK100-NEW-019
NTK100-NEW-020
```

## До исправления

Все 4 кейса были размечены как `missing_source`.

Симптом:

```text
014: запрос по статусам замечаний поднимал общие строки Table 8 "Управление замечаниями", но не список статусов.
016: запрос по аннулированию поднимал закрытие/устранение, но не процесс "Аннулировать" при необоснованности замечания.
019: запрос по ролям поднимал процесс закрытия замечания и короткий указатель на матрицу, но не состав ролей.
020: запрос по ограничениям прав поднимал процессные строки/указатели, но не строки матрицы прав доступа.
```

## Что изменено

В `configs/asu_june_bot/query_expansion.yaml` добавлены отдельные PR expansion-группы:

```text
pr_notice_statuses
pr_notice_annulment
pr_roles_rights
```

В retrieval layer добавлены точечные PR routes:

```text
src/asu_june_bot/retrieval/bm25.py
src/asu_june_bot/retrieval/post_rerank.py
src/asu_june_bot/retrieval/hybrid.py
```

Логика:

```text
Статусы замечаний -> boost строки Table 17 "Параметр отчета: Статус" со значениями К устранению / На проверке / На доработке / Просрочено / Не устранено / Устранено / Аннулировано.
Аннулирование -> boost Table 10, где кнопка "Аннулировать" применяется при необоснованности замечания и переводит процесс в "Аннулировано".
Роли -> boost раздел "Роли и полномочия" с привилегированными и непривилегированными ролями.
Права доступа -> boost строки Приложения 1 / Table 32 с "Ограничения" и "Право доступа" по ролям.
Точные PR-якоря -> сильнее lexical-first hybrid weighting.
Запросы по строительному контролю -> penalty для ПР других модулей, например исполнительной документации.
```

Добавлены regression tests:

```text
tests/asu_june_bot/retrieval/test_bm25_ntk_routes.py
```

## Targeted eval

Search-level `hybrid`, NTK corpus, top-k=5:

```text
NTK100-NEW-014: status=ok, top source Table 17 row 6 со списком статусов замечаний.
NTK100-NEW-016: status=ok, top sources Table 10 row 12 + closing paragraph про аннулирование необоснованного замечания.
NTK100-NEW-019: status=ok, top sources "Роли и полномочия": привилегированные и непривилегированные роли.
NTK100-NEW-020: status=ok, top sources Appendix 1 / Table 32 с ограничениями и правами доступа по ролям.

summary: passed=4/4
```

Chat-level `hybrid`, model `qwen2.5:7b-instruct`, top-k=5:

```text
NTK100-NEW-014: answered, validation_errors=[], anchors: К устранению, На проверке, На доработке, Аннулировано.
NTK100-NEW-016: answered, validation_errors=[], anchors: Аннулировать.
NTK100-NEW-019: answered, validation_errors=[], anchors: привилегированные, непривилегированные.
NTK100-NEW-020: answered, validation_errors=[], anchors: ограничения, право доступа.

summary: passed=4/4
```

Примечание: chat-level команда вывела `DONE` по всем четырем кейсам и все результаты, но оболочка вернула timeout после завершения полезного вывода. Результаты выше взяты из полного stdout этой команды.

Regression:

```text
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\retrieval\test_query_intent_project_markers.py tests\asu_june_bot\retrieval\test_bm25_ntk_routes.py -q

12 passed
```

## Вывод

P1 `PR missing_source` закрыт на уровне targeted retrieval/chat eval. Запросы по ПР СМР теперь поднимают не общие процессные строки, а конкретные источники по статусам, аннулированию, ролям и матрице прав доступа.

Остаток P1: `NSI regulation/reference`, `Passport`, `AD/app_ccpm`.
