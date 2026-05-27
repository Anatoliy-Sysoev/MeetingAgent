# Контекст проекта

Обновлено: 2026-05-27.

## NTK Yandex corpus chunk quality

Ветка `codex/ntk-yandex-corpus` была влита в `main`. Корпус собирается по очищенной папке:

```text
C:\Users\Сотрудник\Desktop\Yandex.Disk\Документы НТК Сдача
```

Найденные проблемы качества чанков:

```text
гигантские Excel table_row chunks до ~401k символов;
микрошумовые чанки: "{", "}", "},", "end", "…";
document_type=unknown у большой доли xlsx/pptx/pdf/НСИ-материалов;
дубли между версиями ПР-документов;
локальные missing source_url для пары документов.
```

Реализован безопасный технический слой очистки:

```text
scripts/asu_june_bot_extract_text_v2.py:
  - Excel rows обрезаются по полезной ширине;
  - сначала удаляются полностью пустые Excel-колонки;
  - введены soft warning 120 колонок и hard cap 250 колонок;
  - table_row text строится из непустых key:value pairs;
  - headers/cells больше не раздуваются пустыми col_N.

scripts/asu_june_bot_build_chunks_v2.py:
  - table_row больше не дублирует "Заголовки";
  - table_row проходит через split_long_text;
  - добавлен hard split длинных абзацев;
  - headers/cells в metadata ограничены;
  - микрошумовые чанки фильтруются без удаления смысловых заголовков.

src/asu_june_bot/retrieval/metadata.py:
  - добавлены document_type для "Справочник НСИ",
    "Методика/Регламент НСИ", "Статус/Презентация",
    "Схема/Диаграмма";
  - pptx не типизируется только по расширению: нужен WIP/status-маркер.
```

Проверка на старых blocks для `4 СВОК РД.xlsx`:

```text
до фикса: table_row chunks до ~401k символов;
после нового chunker на старых blocks:
  max_chars=3843
  gt6000=0
  document_type=Справочник НСИ
```

Полная пересборка extractor -> chunks -> embeddings/index выполнена 2026-05-27.

Итог нового runtime-корпуса:

```text
chunks_v2.jsonl: 31270 chunks
numpy_index_v2/manifest.json: exists
embedding_model: bge-m3
embedding_dim: 1024
index count: 31270
created_at: 2026-05-27T01:57:30Z
```

Smoke после пересборки:

```text
BM25: 8/20 ok, source_url_in_top5=12/20
hybrid after project markers/routing: 20/20 ok, source_url_in_top5=19/20
```

Ручная source-supported проверка retrieval grounding была выполнена на уровне найденных источников:

```text
manual review: 18/20 strict pass
partial: 2/20
fail: 0/20
```

Артефакты review зафиксированы в Git:

```text
docs/quality/ntk_smoke_manual_review_2026-05-27_summary.md
docs/quality/ntk_smoke_manual_review_2026-05-27.csv
docs/quality/ntk_smoke_manual_review_2026-05-27.jsonl
```

Решение на тот момент: NTK corpus можно включать только через feature flag. Безусловным глобальным default корпус не становится.

Реализован feature flag корпуса:

```text
configs/asu_june_bot/corpus.yaml
ASU_JUNE_BOT_ACTIVE_CORPUS=default|ntk
```

Проверка:

```text
scripts/asu_june_bot_health_v2.py --json с ASU_JUNE_BOT_ACTIVE_CORPUS=ntk
возвращает corpus=ntk_yandex_corpus и пути data/asu_june_bot_ntk/*
```

Chat-level проверка через LLM выявила важное уточнение:

```text
Команда:
.\.venv\Scripts\python.exe scripts\asu_june_bot_chat.py "Что указано в ЦТА про RTO и RPO?"

Результат:
LLM ответил, что в переданных источниках данных недостаточно для ответа.

Фактически в контекст попали фрагменты ЦТА про Grafana Loki / SIEM / HTTPS / порт 443,
а не фрагменты про RTO/RPO, восстановление или резервное копирование.

Вывод:
- chat runtime работает;
- LLM не галлюцинирует и корректно отказывается отвечать без подтверждающих источников;
- проблема находится в retrieval/routing;
- NTK-SMOKE-007 является false positive предыдущего smoke, потому что smoke проверял doc_type=ЦТА,
  но не проверял наличие RTO/RPO anchors в top sources.
```

Актуальные follow-up кейсы:

```text
NTK-SMOKE-007:
  требуется отдельный route/intent cta_recovery_rto_rpo;
  query expansion должен использовать RTO/RPO/время восстановления/точка восстановления/резервное копирование/backup/restore;
  нельзя расширять этот запрос общими инфраструктурными терминами Grafana Loki/SIEM/Kubernetes как primary anchors;
  rerank должен повышать chunks с RTO/RPO/восстановлением и штрафовать port/logging-only chunks без RTO/RPO;
  smoke должен проверять expected_terms_in_top5, а не только expected_doc_type=ЦТА;
  после фикса обязательно повторить chat.py проверку.

NTK-SMOKE-012:
  точечный retrieval-fix внесен;
  теперь в top-2 появляется chunk с таблицей "Роли / группы AD" и app_ccpm_ul_cc_01/02/03;
  нужен повторный ручной review кейса.

NTK-SMOKE-017:
  точечный retrieval-fix внесен;
  запросы про регламенты ведения теперь поднимают Методика/Регламент НСИ в top-1..top-5;
  нужен повторный ручной review кейса.
```

Дополнительная проверка `NTK-SMOKE-007` после chat-level ревью:

```text
предыдущий smoke 20/20 оказался слишком мягким для RTO/RPO;
он проверял doc_type=ЦТА, но не требовал recovery anchors в top-5;
в main это было зафиксировано как false positive retrieval/routing, а не ошибка LLM.
```

Исправление 2026-05-27:

```text
добавлен отдельный intent `cta_recovery_rto_rpo`;
RTO/RPO вынесены из общего `cta_infrastructure` в отдельный query expansion bucket;
для RTO/RPO-запросов добавлен boost recovery chunks и penalty logging/port-only chunks;
smoke-кейс `NTK-SMOKE-007` получил `expected_terms_in_top5 = [rto, rpo, время восстановления]`.
```

Новый результат:

```text
`scripts/asu_june_bot_ntk_smoke_eval.py --mode hybrid` -> 19/20 ok;
`NTK-SMOKE-007` теперь проходит по усиленному контракту;
единственный fail в текущем smoke — `NTK-SMOKE-017`, потому что retrieval уже корректно уходит в `Методика/Регламент НСИ`, а smoke по-прежнему ожидает старый `Реестр НСИ`.
```

## Retrieval quality evolution

После realistic-100 и realistic-500 ручной разметки retrieval quality переведён на bucket-driven pipeline.

Главные failure buckets:

```text
ФТТ не находится
ЦТА не находится
ПР не находится
СоИ AD/LDAPS не находится
MDR/НСИ/Bearer Token ломается
guard ошибочно refuse/allow
hallucination при слабых источниках
```

Для каждого bucket реализуются:

```text
retrieval hints
anchor expansion
lexical aliases
metadata routing
hybrid rerank boost
targeted eval rerun
approved regression set
```

Новый quality-layer:

```text
scripts/rag_bucket_quality.py
```

Назначение:

```text
bucket detection
query expansion by domain
metadata-aware routing
path-aware rerank boosting
bucket diagnostics
failure classification
```

Targeted rerun runner:

```text
scripts/18_targeted_bucket_eval.py
```

Pipeline:

```text
review verdicts
  -> failure buckets
  -> retrieval diagnostics
  -> targeted rerun
  -> rerank tuning
  -> approved regression set
  -> realistic rerun
```

Targeted rerun теперь сохраняет machine-readable артефакты:

```text
data/targeted_bucket_eval/<bucket>_<timestamp>.jsonl
data/targeted_bucket_eval/<bucket>_<timestamp>.summary.json
```

Summary включает:

```text
status_counts
returncode_counts
parse_errors
failures
confidence
sources_count
retrieval diagnostics
```

Approved regression set:

```text
approved_regression_set.jsonl
```

Используется как:

```text
stable retrieval baseline
anti-regression corpus
quality smoke set
```

Hybrid retrieval quality v3:

```text
vector retrieval
+ BM25/FTS5 lexical retrieval
+ targeted lexical scan
+ bucket expansion
+ metadata-aware rerank
+ source-quality hard gate
```

Rerank теперь учитывает:

```text
lexical_score
matched_terms
matched_numbers
phrase_matches
bucket_signals
doc_type_match
path boosts
metadata routing
```

Hard source-quality gate:

```text
weak retrieval -> no_answer
weak retrieval -> retrieval_fix_required
```

LLM не должен выдавать answered если:

```text
нет anchor terms
нет section match
нет metadata/doc-type match
низкий lexical score
```

Guard evolution:

```text
project-safe security questions -> allow
harmful abuse -> refuse
out-of-scope бытовые вопросы -> refused/out_of_scope
```
