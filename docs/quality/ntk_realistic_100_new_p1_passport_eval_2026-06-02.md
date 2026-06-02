# NTK realistic-100: P1 Passport routing follow-up

Дата: 2026-06-02

## Scope

Закрывался bucket `P1 Passport` из `ntk_realistic_100_new`:

- `NTK100-NEW-063` — что входит в Паспорт ИС и какие связанные документы указаны;
- `NTK100-NEW-064` — какие приложения перечислены в Паспорте ИС;
- `NTK100-NEW-065` — какие сведения о системе и назначении ИС указаны в Паспорте ИС.

Исходная проблема ручной проверки: все три кейса были `missing_source/no_answer`, потому что retrieval поднимал слишком узкие или частичные фрагменты Паспорта ИС.

## Changes

Внесены точечные изменения:

- расширен `passport_is` query expansion для связанных документов Table 2;
- добавлен Passport-specific BM25/post-rerank boost для Table 2, Table 3 и exact purpose chunks;
- Passport-specific bucket в `ContextBuilder` выполняется до общего `DOCUMENT_OVERVIEW`;
- добавлена агрегация строк Passport Table 2/Table 3 в один source block;
- `BuiltContext.to_dict()` отдаёт primary/supporting preview до 1800 символов, чтобы prompt не терял агрегированный список;
- расширен deterministic fallback для Passport list/purpose false `no_answer`;
- добавлены regression tests для intent, BM25, context builder, source quality и chat fallback.

## Verification

Search-level:

```text
ASU_JUNE_BOT_ACTIVE_CORPUS=ntk
scripts/asu_june_bot_search_v2.py ... --mode hybrid --top-k 8

063: Passport Table 2 expanded_count=4
064: Passport Table 3 expanded_count=3
065: exact chunk "Система предназначена..." стал primary
```

Chat-level targeted eval:

```text
scripts/14_run_realistic_100_eval.py
  --dataset data/ntk_targeted_passport_3_queries.jsonl
  --output data/ntk_targeted_passport_3_eval_report.jsonl
  --chat-script scripts/asu_june_bot_chat.py
  --mode hybrid
  --top-k 5
  --max-tokens 700

total: 3
failures: 0
parse_errors: 0
statuses:
  answered: 3
avg_duration_sec: 124.588
max_duration_sec: 147.068
min_duration_sec: 103.803
```

Tests:

```text
pytest tests/asu_june_bot/retrieval/test_query_intent_project_markers.py \
       tests/asu_june_bot/retrieval/test_bm25_ntk_routes.py \
       tests/asu_june_bot/retrieval/test_context_builder_qh.py \
       tests/asu_june_bot/retrieval/test_source_quality.py \
       tests/asu_june_bot/chat/test_chat_service.py -q

47 passed

pytest tests/asu_june_bot -q
170 passed

python -m compileall -q src/asu_june_bot
ok
```

## Result

`P1 Passport` закрыт по runtime-критерию targeted eval: `NTK100-NEW-063`, `064`, `065` дают `answered`.

Ограничение: `NTK100-NEW-064` и `065` могут закрываться через deterministic fallback, если LLM снова выдаёт false `no_answer` при наличии релевантных источников. Это допустимо для MVP, потому что fallback строит ответ только из переданных `ChatSource`.

## Next bucket

Следующий рабочий bucket: `P1 AD/app_ccpm`.

Ключевой риск: вопрос про группы AD для ролей строительного контроля должен поднимать `ПР Стройконтроль, приложение 2 - группы`, а не только общие строки СоИ AD.
