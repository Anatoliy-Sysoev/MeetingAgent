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

Follow-up кейсы после targeted fixes:

```text
NTK-SMOKE-007:
  закрыт;
  добавлен отдельный route/intent cta_recovery_rto_rpo;
  query expansion использует RTO/RPO/время восстановления/точка восстановления/резервное копирование/backup/restore;
  для RTO/RPO-запросов добавлен boost recovery chunks и penalty logging/port-only chunks;
  smoke проверяет expected_terms_in_top5, а не только expected_doc_type=ЦТА;
  chat-level проверка теперь поднимает recovery chunks и отвечает по RTO=4 часа, RPO=4 часа.

NTK-SMOKE-012:
  точечный retrieval-fix внесен;
  теперь в top-2 появляется chunk с таблицей "Роли / группы AD" и app_ccpm_ul_cc_01/02/03;
  нужен повторный ручной review кейса.

NTK-SMOKE-017:
  ручной review выполнен;
  для запроса "Какие регламенты ведения объектов НСИ есть в корпусе?" правильнее ожидать `Методика/Регламент НСИ`, а не `Реестр НСИ`;
  причина: вопрос спрашивает про регламентные документы/методики ведения, а не про сам реестр объектов;
  expectation в `docs/quality/ntk_yandex_smoke_questions.jsonl` обновлен на expected_doc_type=`Методика/Регламент НСИ` и expected_terms_in_top5=[регламент, нси].
```

Текущий статус после обновления expectation:

```text
последний зафиксированный smoke до обновления expectation: 19/20 ok;
единственный fail был NTK-SMOKE-017 из-за устаревшего expected_doc_type=`Реестр НСИ`;
expectation обновлен, но полный hybrid rerun после этого изменения нужно выполнить локально;
ожидаемый результат после rerun: NTK-SMOKE-017 должен пройти, если top-1..top-5 остаются в `Методика/Регламент НСИ` и содержат anchors `регламент` + `нси`.
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

## MeetingAgent status на 2026-05-27

Базовый meeting pipeline реализован от готовой GigaAM-транскрибации до structured artifacts и отдельного meeting index.

Сделано:

```text
20_ingest_meeting.py: карточка встречи и source media;
24_merge_transcript_speakers.py: diarization-lite speaker transcript;
26_chunk_meeting.py: meeting-aware chunks с таймкодами;
27_enrich_meeting_chunks.py: heuristic enrichment;
28_index_meeting_chunks.py: export raw meeting chunks в data/meeting_chunks.jsonl;
29_analyze_meeting.py: LLM map-reduce artifacts summary/protocol/decisions/tasks/risks/open_questions;
31_meeting_search.py: smoke search по meeting_chunk и structured meeting source types;
32_index_meeting_artifacts.py: export decisions/tasks/risks/open_questions как отдельные source_type.
```

Новые indexed source types:

```text
meeting_decision
meeting_action_item
meeting_risk
meeting_open_question
```

Реальный smoke на встрече `2026-05-26__support-scheme`:

```text
32_index_meeting_artifacts.py: 14 structured rows
data/meeting_chunks.jsonl total: 17 rows
source_type counts:
  meeting_chunk: 3
  meeting_decision: 3
  meeting_action_item: 5
  meeting_risk: 3
  meeting_open_question: 3
data/meeting_numpy_index rebuilt: 17 embeddings, bge-m3, dim=1024
31_meeting_search.py "какие решения приняли": первые результаты meeting_decision DEC-001..DEC-003
```

Текущая проблема:

```text
локальный LLM REDUCE на CPU нестабилен: qwen2.5:7b-instruct может уходить в timeout;
qwen3:8b слишком медленный для надежного полного map-reduce;
иногда LLM возвращает битый JSON или лишний текст;
fallback сохраняет работоспособность pipeline, но качество итогов пока требует ручного review.
```
