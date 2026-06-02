# NTK realistic-100 new P1 targeted eval: AD/app_ccpm

Дата: 2026-06-02.

Статус:

```text
closed
```

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
040/041: LLM мог вернуть формально answered, но семантически неверный ответ по наличию mapping.
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

AD role mapping:
  если вопрос содержит app_ccpm_ul_cc и маркеры role/mapping;
  пары app_ccpm_ul_cc_* -> роль извлекаются из source text детерминированно до вызова LLM;
  это устраняет ложный answered/no_answer от LLM на точном табличном mapping.
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

### 3. Pre-LLM deterministic answer

Файл:

```text
src/asu_june_bot/chat/service.py
```

Для узких AD/app_ccpm/LDAPS кейсов deterministic answer формируется после поиска и до вызова LLM:

```text
pre_llm_deterministic_answer = true
llm_called = false
```

## Итоговый targeted eval

Команда:

```powershell
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:ASU_JUNE_BOT_ACTIVE_CORPUS = "ntk"

.\.venv\Scripts\python.exe scripts\14_run_realistic_100_eval.py `
  --dataset data\ntk_targeted_ad_app_ccpm_4_queries.jsonl `
  --output data\ntk_targeted_ad_app_ccpm_4_eval_report.jsonl `
  --chat-script scripts\asu_june_bot_chat.py `
  --mode hybrid `
  --top-k 5 `
  --max-tokens 700
```

Результат:

```text
total: 4
failures: 0
parse_errors: 0
statuses:
  answered: 4
avg_duration_sec: 15.555
max_duration_sec: 16.549
min_duration_sec: 14.801
```

Проверка ответов:

```text
NTK100-NEW-036:
  status = answered
  llm_called = False
  pre_llm_deterministic_answer = True
  validation_errors = []
  primary = СоИ AD
  answer: wildcard-маска app_ccpm отдельной строкой не указана; найден префикс app_ccpm_ и примеры app_ccpm_ul_cc_01/02/03/app_ccpm_ul_headoffice.

NTK100-NEW-039:
  status = answered
  llm_called = False
  pre_llm_deterministic_answer = True
  validation_errors = []
  primary = СоИ AD
  answer: LDAP-каталог доступен по порту 636 через SSL (LDAPS); сервисные учетные записи имеют права чтения к LDAP-каталогам.

NTK100-NEW-040:
  status = answered
  llm_called = False
  pre_llm_deterministic_answer = True
  validation_errors = []
  primary = Описание разработок ИС:Роли / группы AD
  answer: app_ccpm_ul_cc_01 — Куратор Проекта НУЛ; app_ccpm_ul_cc_02 — Отвечающий за выполнение функции строительного контроля; app_ccpm_ul_cc_03 — Отвечающий за подачу факта.

NTK100-NEW-041:
  status = answered
  llm_called = False
  pre_llm_deterministic_answer = True
  validation_errors = []
  primary = Описание разработок ИС:Роли / группы AD
  answer: app_ccpm_ul_cc_01 — Куратор Проекта НУЛ; app_ccpm_ul_cc_02 — Отвечающий за выполнение функции строительного контроля; app_ccpm_ul_cc_03 — Отвечающий за подачу факта.
```

Regression:

```text
pytest tests/asu_june_bot -q -> 170 passed
python -m compileall -q src\asu_june_bot -> ok
```

## Acceptance closed

```text
NTK100-NEW-036 -> answered
NTK100-NEW-039 -> answered
NTK100-NEW-040 -> answered
NTK100-NEW-041 -> answered
clarify = 0
parse_errors = 0
failures = 0
validation_errors = []
no hallucination by manual source review
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
  СоИ AD находится в supporting/related context when present;
  diagnostics.ad_cc_role_mapping_promotion.applied = true;
  deterministic answer перечисляет app_ccpm_ul_cc_01/02/03 и связанные роли.
```

## Runtime data

Runtime reports не коммитятся:

```text
data/ntk_targeted_ad_app_ccpm_4_queries.jsonl
data/ntk_targeted_ad_app_ccpm_4_eval_report.jsonl
```

## Residual risk

```text
Если в будущей версии корпуса появится ПР Стройконтроль / Приложение 2 с точными app_ccpm_ul_cc_01/02/03, acceptance для 040/041 можно вернуть к более строгому primary = ПР.
В текущем chunks_v2 такой источник отсутствует, поэтому текущий accepted primary — Описание разработок ИС / Table 12.
```
