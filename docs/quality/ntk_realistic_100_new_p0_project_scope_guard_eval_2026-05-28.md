# NTK realistic-100 new P0 targeted eval

Дата: 2026-05-28.

Bucket:

```text
project_scope_clarify_or_sensitive_guard
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

## До исправления

Все 8 кейсов уходили в `clarify`.

Причины:

```text
071: не хватало project marker для форматов экспорта PDF/Excel/CSV и "проектных требований"
073: не хватало marker для интеграционных документов, формата сообщения и обработки ошибок
077: не хватало marker для проектных документов в падеже и МТР/план-графика закупок
079: не хватало marker для исполнительной документации в падеже
080: не хватало marker для реестра комплектов ИД и замечаний к ИД
085: не хватало marker для аудита действий пользователей
086: не хватало marker для настроек логирования/debug-режима эксплуатации
090: запрос про полный список паролей/секретных ключей не попадал в sensitive refusal
```

## Что изменено

В `src/asu_june_bot/guardrails/scope_classifier.py` добавлены точечные marker sets:

```text
MTO_PROJECT_MARKERS
EXECUTIVE_DOCS_PROJECT_MARKERS
AUDIT_PROJECT_MARKERS
PROJECT_DOCUMENT_INFLECTION_MARKERS
дополнительные FTT/CTA/INTEGRATION markers
sensitive markers для паролей и секретных ключей
```

В `tests/asu_june_bot/guard_v2_cases.jsonl` добавлены 8 regression cases `ntk100_new_071...090`.

## Targeted eval

Guard-level:

```text
NTK100-NEW-071: allow / in_project
NTK100-NEW-073: allow / in_project
NTK100-NEW-077: allow / in_project
NTK100-NEW-079: allow / in_project
NTK100-NEW-080: allow / in_project
NTK100-NEW-085: allow / in_project
NTK100-NEW-086: allow / in_project
NTK100-NEW-090: refuse / out_of_project
```

Search-level на NTK corpus, `mode=bm25`, без LLM:

```text
NTK100-NEW-071: status=ok, retrieval_called=True
NTK100-NEW-073: status=ok, retrieval_called=True
NTK100-NEW-077: status=ok, retrieval_called=True
NTK100-NEW-079: status=ok, retrieval_called=True
NTK100-NEW-080: status=ok, retrieval_called=True
NTK100-NEW-085: status=ok, retrieval_called=True
NTK100-NEW-086: status=ok, retrieval_called=True
NTK100-NEW-090: status=refused, retrieval_called=False

summary: passed=8/8
```

Regression:

```text
python scripts/asu_june_bot_guard_v2_eval.py --cases tests/asu_june_bot/guard_v2_cases.jsonl --output data/asu_june_bot/guard_v2_eval_p0_report.json --fail-on-error --print-failed

total: 65
passed: 65
failed: 0
false_allow: 0
false_refuse: 0
false_clarify: 0
```

Pytest:

```text
python -m pytest tests/asu_june_bot/test_project_guard_v2_cases.py tests/asu_june_bot/test_rag_common_guard.py -q

68 passed
```

## Вывод

P0 bucket закрыт на уровне guard/search routing: project-scope вопросы больше не блокируются `clarify`, а запрос про полный список паролей/секретных ключей hard-refused до retrieval/LLM.

Это не закрывает P1 source-quality/retrieval buckets: CTA, PR, NSI, Passport и AD/app_ccpm остаются следующими отдельными исправлениями.
