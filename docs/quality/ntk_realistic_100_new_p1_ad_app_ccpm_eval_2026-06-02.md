# NTK realistic-100 new P1 targeted eval: AD/app_ccpm

Дата: 2026-06-02.

Bucket:

```text
AD/app_ccpm
```

Кейсы:

```text
NTK100-NEW-036
NTK100-NEW-039
NTK100-NEW-040
NTK100-NEW-041
```

## Целевое поведение

```text
NTK100-NEW-036:
  вопрос про маску/префикс групп app_ccpm в интеграции с AD;
  ответ должен быть source-grounded: не утверждать wildcard как формальный факт, если он не указан явно;
  если найдены конкретные группы app_ccpm_..., отвечать по найденному префиксу и примерам.

NTK100-NEW-039:
  вопрос про LDAPS и порты в СоИ AD;
  ответ должен поднимать фрагмент СоИ AD с портом 636, SSL/LDAPS и сервисными учетными записями с правами чтения.

NTK100-NEW-040/041:
  вопрос про соответствие app_ccpm_ul_cc_01/02/03 ролям строительного контроля;
  primary source должен содержать явный mapping групп к ролям;
  СоИ AD должен оставаться supporting source.
```

## Проверка корпуса

По загруженному `chunks_v2.jsonl` выполнен поиск точных якорей:

```text
app_ccpm_ul_cc_01
app_ccpm_ul_cc_02
app_ccpm_ul_cc_03
Роли / группы AD
```

Найдено 5 chunks, все относятся к одному документу:

```text
Этап 1.2/3.2 Описание разработок и настроек ИС/Описание разработок и настроек ИС_ЦП УПКС_Этап 1_v1.docx
Table 12
```

Ключевой chunk:

```text
line: 25945
chunk_id: d0ec1b207a3ed32b49a85c335912c72c
document_type: None
title: None
table_id: Table 12
text: Роли / группы AD: app_ccpm_ul_cc_01 — Куратор Проекта НУЛ; app_ccpm_ul_cc_02 — Отвечающий за выполнение функции строительного контроля; app_ccpm_ul_cc_03 — Отвечающий за подачу факта; app_ccpm_ul_headoffice — Куратор ПАО НУЛ
```

Corpus gap:

```text
ПР Стройконтроль / Приложение 2 с точными группами app_ccpm_ul_cc_01/02/03 в текущем chunks_v2 не найден.
```

Следствие:

```text
До переиндексации/добавления источника acceptance для 040/041 принимается как:
  primary = Описание разработок и настроек ИС / Table 12 / Роли / группы AD;
  supporting = СоИ AD.
```

## Состояние до follow-up fix

Локальный targeted run после первого promotion-fix:

```text
total: 4
failures: 0
parse_errors: 0
statuses:
  no_answer: 2
  answered: 2
```

Детализация:

```text
NTK100-NEW-036 -> no_answer
NTK100-NEW-039 -> no_answer
NTK100-NEW-040 -> answered, ad_cc_role_mapping_promotion.applied=true
NTK100-NEW-041 -> answered, ad_cc_role_mapping_promotion.applied=true
```

Проблемы:

```text
036: false no_answer — источники содержат конкретные app_ccpm_... группы, но LLM не формирует безопасный ответ по префиксу/примерам.
039: false no_answer — источники содержат LDAPS/SSL/порт 636, но LLM возвращает no_answer.
040/041: answered, но у promoted source отсутствовали document_type/title, поэтому diagnostics отображались как primary "::".
```

## Что исправлено

### 1. AD deterministic fallback

Файл:

```text
src/asu_june_bot/chat/inventory_answer.py
```

Добавлены fallback-сценарии:

```text
app_ccpm mask/prefix:
  если вопрос содержит app_ccpm и маркеры маски/групп/AD;
  если в sources найдены группы app_ccpm_...;
  ответ строится по найденному префиксу и примерам;
  формальная wildcard-маска не утверждается как факт, если не указана явно.

LDAPS/636:
  если вопрос содержит LDAPS/LDAP/порт/636/SSL и AD;
  если в sources найден фрагмент с 636 + LDAPS или LDAP+SSL;
  ответ строится по найденному фрагменту: порт 636, SSL/LDAPS, сервисные УЗ с правами чтения при наличии в preview.
```

### 2. Metadata inference для mapping source

Файл:

```text
src/asu_june_bot/search/service.py
```

Добавлена runtime-normalization для promoted AD role mapping chunk:

```text
if relative_path содержит "Описание разработок и настроек ИС":
  document_type = "Описание разработок ИС"

if text/table содержит "Роли / группы AD":
  title = "Роли / группы AD"
  table_title = "Роли / группы AD"
```

В diagnostics promotion добавлено поле:

```text
metadata_inference: ad_cc_role_mapping_table
```

## Acceptance criteria

Нужно подтвердить локальным targeted eval на актуальном NTK corpus:

```text
NTK100-NEW-036 -> answered
NTK100-NEW-039 -> answered
NTK100-NEW-040 -> answered
NTK100-NEW-041 -> answered
clarify = 0
parse_errors = 0
failures = 0
```

Source acceptance:

```text
036:
  ответ не галлюцинирует wildcard-маску;
  отвечает по найденному префиксу app_ccpm_ и примерам групп.

039:
  ответ содержит LDAPS/SSL и порт 636 по СоИ AD.

040/041:
  primary содержит Описание разработок ИС / Table 12 / Роли / группы AD;
  СоИ AD находится в supporting;
  diagnostics.ad_cc_role_mapping_promotion.applied = true.
```

Regression:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot -q
.\.venv\Scripts\python.exe -m compileall -q src\asu_june_bot
```

## Runtime data

Runtime reports не коммитятся:

```text
data/ntk_targeted_ad_app_ccpm_4_queries.jsonl
data/ntk_targeted_ad_app_ccpm_4_eval_report.jsonl
```
