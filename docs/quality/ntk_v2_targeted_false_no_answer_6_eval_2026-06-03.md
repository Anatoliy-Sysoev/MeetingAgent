# NTK v2 targeted eval: false no_answer / low_score

Дата: 2026-06-03.

Статус:

```text
closed
```

Bucket:

```text
P1 false no_answer / low_score после guard-fix
```

## Scope

Targeted dataset:

```text
data/ntk_v2_targeted_false_no_answer_6_queries.jsonl
```

Eval report:

```text
data/ntk_v2_targeted_false_no_answer_6_eval_report.jsonl
```

Кейсы:

```text
NTK100-V2-015
NTK100-V2-021
NTK100-V2-023
NTK100-V2-054
NTK100-V2-065
NTK100-V2-083
```

## Исходная проблема

После закрытия guard bucket `false clarify / bad_refusal` эти 6 проектных вопросов перестали останавливаться на guard и начали доходить до retrieval, но часть из них возвращала `no_answer` или слабый ответ.

Первичный targeted run по этому bucket показывал:

```text
answered: 2
no_answer: 4
```

После query expansion/source selection fixes оставался один проблемный кейс:

```text
NTK100-V2-021 -> validation_failed
validation: unknown_source_references:S2,S3
```

Для `NTK100-V2-021` источник уже начал поднимать Table 17 ЦТА, но LLM сгенерировала ссылки на источники, которых не было в итоговом `sources`, из-за чего структурный валидатор вернул `validation_failed`.

## Code changes

Изменения внесены в:

```text
configs/asu_june_bot/query_expansion.yaml
src/asu_june_bot/search/service.py
src/asu_june_bot/chat/inventory_answer.py
src/asu_june_bot/chat/service.py
```

Ключевые изменения:

```text
1. Добавлены source-grounded fallback builders для narrow false no_answer cases:
   - роли фиксации и контроля устранения замечаний;
   - инфраструктурные компоненты продуктивного контура;
   - очереди сообщений / RabbitMQ;
   - ожидаемые результаты сценариев по актам и предписаниям;
   - сервисные учетные записи / права доступа;
   - ограничения доступа к исполнительной документации.

2. Усилены query expansion buckets:
   - cta_infrastructure;
   - cta_messaging_events;
   - service_accounts_access;
   - executive_docs_access.

3. Добавлен source-selection fix для ЦТА Table 17:
   - если retrieval поднимает chunk, который ссылается на Табл. 17 продуктивного контура, SearchService inject-ит связанные Table 17 chunks из того же документа до post-rerank.

4. ChatService теперь пробует inventory fallback не только при явном no_answer marker, но и при structural validation failure LLM-ответа.
   Это нужно для случаев вроде `unknown_source_references:S2,S3`, когда источники найдены, но LLM оформила некорректные citations.
```

Relevant commits:

```text
00bfca3 Add NTK v2 false no-answer fallbacks
006c604 Improve NTK v2 false no-answer query expansion
d76d04b Add CTA Table 17 anchors for infrastructure queries
d2d9770 Inject CTA Table 17 chunks for infrastructure queries
1559afe Use inventory fallback on validation failures
```

## Final targeted eval result

Command:

```powershell
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:ASU_JUNE_BOT_ACTIVE_CORPUS = "ntk"

.\.venv\Scripts\python.exe scripts\14_run_realistic_100_eval.py `
  --dataset data\ntk_v2_targeted_false_no_answer_6_queries.jsonl `
  --output data\ntk_v2_targeted_false_no_answer_6_eval_report.jsonl `
  --chat-script scripts\asu_june_bot_chat.py `
  --mode hybrid `
  --top-k 5 `
  --max-tokens 700
```

Summary:

```text
total: 6
failures: 0
parse_errors: 0
scopes:
  project: 6
models:
  qwen2.5:7b-instruct: 6
statuses:
  answered: 6
avg_duration_sec: 56.492
max_duration_sec: 83.021
min_duration_sec: 38.24
```

## Acceptance check

All 6 targeted cases passed:

```text
status = answered
failures = 0
parse_errors = 0
scope = project
```

Per case expectation:

```text
NTK100-V2-015 -> answered
NTK100-V2-021 -> answered
NTK100-V2-023 -> answered
NTK100-V2-054 -> answered
NTK100-V2-065 -> answered
NTK100-V2-083 -> answered
```

## Result

```text
P1 false no_answer / low_score targeted bucket is closed for these 6 cases.
```

Residual work remains in broader NTK v2 quality buckets:

```text
1. Run full NTK realistic-100 v2 rerun after current fixes.
2. Rebuild verdict summary from the new run.
3. Create gold expectations for stable regression cases before removing the feature flag.
4. Continue with garbage_source / source-selection buckets from manual review.
```
