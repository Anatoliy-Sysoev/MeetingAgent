# Контекст проекта

Обновлено: 2026-06-03.

## NTK realistic-100 new eval

2026-06-03 актуализирована документация подпроекта Project Knowledge Bot для переноса Bot v2 Yandex на другой локальный ПК:

```text
docs/subprojects/asu-june-bot/README_YANDEX_V2_LOCAL.md
```

Зафиксировано: runtime chunks/index/cache для Yandex/NTK корпуса не лежат в GitHub. Для быстрого запуска на другом ПК нужно запросить пакет `data/asu_june_bot_ntk` с `chunks_v2.jsonl` и `numpy_index_v2`, либо пересобрать корпус из исходной папки Яндекс.Диска. Docker packaging в корне проекта используется как основной переносимый запуск API/Telegram с `ASU_JUNE_BOT_ACTIVE_CORPUS=ntk`.

2026-06-03 после ревизии документации подпроекта удалены одноразовые рабочие документы: `TOMORROW_START.md`, `TOMORROW_EXECUTION_PROTOCOL.md`, `QH_HARDENING_CHECKLIST.md` и старые `smoke_report_*.md`. Их полезное содержание уже свернуто в `README.md`, `RUNBOOK_V2.md`, `QH_STATUS.md`, `FTT_STATUS.md`, `context.md` и `todo.md`.

2026-05-27 добавлен новый набор из 100 вопросов для NTK corpus:

```text
docs/quality/ntk_realistic_100_new_queries.jsonl
docs/quality/ntk_realistic_100_new_queries_overview.csv
docs/quality/ntk_realistic_100_new_queries_summary.txt
```

Состав набора:

```text
total: 100
scope:
  project: 90
  out_of_scope: 6
  harmful_security: 4
model:
  qwen2.5:7b-instruct: 100
```

Прогон запущен в фоне через:

```powershell
.\scripts\run_realistic_100_eval_automation.ps1 `
  -DatasetPath docs\quality\ntk_realistic_100_new_queries.jsonl `
  -ReportPath data\ntk_realistic_100_new_eval_report.jsonl `
  -ReviewPath data\ntk_realistic_100_new_eval_review.jsonl `
  -SummaryPath data\ntk_realistic_100_new_eval_review_summary.json `
  -ChatScript scripts\asu_june_bot_chat.py `
  -Mode hybrid `
  -ActiveCorpus ntk
```

Runtime outputs не коммитятся:

```text
data/ntk_realistic_100_new_eval_report.jsonl
data/ntk_realistic_100_new_eval_review.jsonl
data/ntk_realistic_100_new_eval_review_summary.json
logs/realistic_100_eval_full_*.out.log
logs/realistic_100_eval_full_*.err.log
```

Для контроля создан hourly monitor в Codex app:

```text
automation_id: ntk-realistic-100-hourly-monitor
```

`scripts/14_run_realistic_100_eval.py` теперь умеет запускать новый `scripts/asu_june_bot_chat.py`: для него используется `--max-tokens`, `--mode hybrid` и `--no-log`, а не legacy `--num-predict`.

2026-05-28 первый фоновый прогон был остановлен на `34/100`, потому что часть строк падала технически на Windows stdout encoding:

```text
UnicodeEncodeError: cp1251 cannot encode combining marks / special symbols
```

Это не retrieval/LLM failure. Исправлено в runner: дочерний chat-процесс запускается с `PYTHONUTF8=1` и `PYTHONIOENCODING=utf-8`. Испорченные runtime reports перенесены в `*.bad_cp1251_<timestamp>`, прогон перезапущен с чистыми output paths.

2026-05-28 перезапущенный прогон завершился штатно:

```text
status: review_ready
rows: 100/100
active PID: отсутствует
runtime statuses:
  answered: 35
  no_answer: 46
  validation_failed: 1
  clarify: 12
  refused: 6
```

Ручная разметка перенесена в tracked quality artifacts:

```text
docs/quality/ntk_realistic_100_new_eval_review_filled.jsonl
docs/quality/ntk_realistic_100_new_eval_review_filled_overview.csv
docs/quality/ntk_realistic_100_new_eval_review_manual_summary.json
docs/quality/ntk_realistic_100_new_eval_review_manual_summary.md
```

Итог review verdicts:

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

Главный вывод review: runner стабилен, но retrieval/routing/guard качество пока недостаточно. `missing_source + low_score = 50/100`; project-scope вопросы всё ещё уходят в `clarify`; out-of-scope guard местами возвращает `clarify` вместо `refused`.

Приоритетные buckets:

```text
P0 project_scope_clarify_or_sensitive_guard:
  NTK100-NEW-071, 073, 077, 079, 080, 085, 086, 090
P1 CTA missing_source:
  NTK100-NEW-025, 026, 027, 028
P1 PR missing_source:
  NTK100-NEW-014, 016, 019, 020
P1 NSI regulation/reference:
  NTK100-NEW-053, 054, 055, 056, 057, 059
P1 Passport:
  NTK100-NEW-063, 064, 065
P1 AD/app_ccpm:
  NTK100-NEW-036, 039, 040
P2 out_of_scope clarify instead of refused:
  NTK100-NEW-093, 094, 095, 096
```

2026-05-28 закрыт P0 bucket `project_scope_clarify_or_sensitive_guard`:

```text
docs/quality/ntk_realistic_100_new_p0_project_scope_guard_eval_2026-05-28.md
```

Изменение: в `scope_classifier.py` добавлены точечные NTK project markers для экспорта, интеграционных документов, МТР, исполнительной документации, аудита, логирования/debug эксплуатации и sensitive markers для полного списка паролей/секретных ключей. В `guard_v2_cases.jsonl` добавлены 8 regression cases.

Проверка:

```text
P0 search-level targeted eval: 8/8
  071, 073, 077, 079, 080, 085, 086 -> status=ok, retrieval_called=True
  090 -> status=refused, retrieval_called=False
guard_v2_eval: 65/65 passed
pytest guard slice: 68 passed
```

Остаток: P1 retrieval/source quality buckets не закрыты и должны идти следующими отдельными коммитами.

2026-05-28 закрыт P1 bucket `CTA missing_source`:

```text
docs/quality/ntk_realistic_100_new_p1_cta_missing_source_eval_2026-05-28.md
```

Изменение: общий `cta_infrastructure` expansion больше не добавляет PostgreSQL/MinIO/Kubernetes/Grafana Loki/SIEM одновременно для точечных запросов. Добавлены отдельные CTA routes для PostgreSQL, MinIO/S3 storage и Kubernetes; BM25/PostRerank теперь бустят целевые CTA chunks и штрафуют SIEM/Grafana Loki/logging noise для non-logging infra-запросов.

Проверка:

```text
hybrid search-level targeted eval: 4/4
chat-level targeted eval: 4/4 answered
pytest retrieval slice: 9 passed
```

2026-05-28 закрыт P1 bucket `PR missing_source`:

```text
docs/quality/ntk_realistic_100_new_p1_pr_missing_source_eval_2026-05-28.md
```

Изменение: добавлены отдельные PR routes для статусов замечаний, аннулирования, ролей и прав доступа. Query expansion теперь подбрасывает точные якоря `статусная схема`, `Аннулировать`, `Привилегированные/Непривилегированные`, `Право доступа/Ограничения`; BM25/PostRerank бустят Table 17, Table 10, раздел "Роли и полномочия" и Appendix 1 / Table 32. Для точных PR-якорей hybrid сильнее смещается в lexical-first режим; ПР других модулей штрафуются для запросов про строительный контроль.

Проверка:

```text
hybrid search-level targeted eval: 4/4
chat-level targeted eval: 4/4 answered, validation_errors=[]
pytest retrieval slice: 12 passed
```

2026-06-02 закрыт P1 bucket `NSI regulation/reference`:

```text
docs/quality/ntk_realistic_100_new_p1_nsi_regulation_reference_eval_2026-05-28.md
```

Изменение: broad `нси` больше не включает MDR/СоИ routing; регламенты/методики ведения НСИ и справочники/атрибутные составы разведены по отдельным routes. BM25/PostRerank/Hybrid/ContextBuilder усиливают `Методика/Регламент НСИ`, `Реестр НСИ`, `Справочник НСИ` и `СоИ Справочники` по точным intent markers, а `ФТТ`/`ПР`/`ЦТА` понижаются для этих запросов. Для inventory/list вопросов добавлен source-grounded fallback, который строит ответ из titles/paths/previews, если LLM вернул ложный `no_answer` при наличии релевантных источников.

Проверка:

```text
chat-level targeted eval: 6/6 answered
clarify: 0
failures: 0
parse_errors: 0
pytest NSI/chat slice: 32 passed
compileall src/asu_june_bot: ok
```

Runtime report не коммитится:

```text
data/ntk_targeted_nsi_6_eval_report.jsonl
```

Остаток P1: `Passport`, `AD/app_ccpm`.

## NTK Obsidian vault rebuild

27.05.2026 добавлен воспроизводимый генератор полной пересборки Obsidian vault по корпусу NTK Yandex:

```text
scripts/ntk_obsidian_rebuild.py
```

Команда фактической пересборки:

```powershell
.\.venv\Scripts\python.exe scripts\ntk_obsidian_rebuild.py --clear-vault
```

Целевая папка:

```text
C:\Users\Сотрудник\Desktop\Yandex.Disk\Документы НТК Сдача\_Obsidian
```

Что делает генератор:

- безопасно очищает только папку `_Obsidian` внутри `Документы НТК Сдача`;
- читает `data/asu_june_bot_ntk/chunks_v2.jsonl` и `data/asu_june_bot_ntk/source_links.jsonl`;
- создает чистый vault с `.obsidian`, где `sync=false` и `publish=false`;
- создает `document_registry.csv`, `chunk_quality_report.md`, `relationships_draft.csv`;
- создает главную страницу `00_Главная/Карта проекта ЦП УПКС.md`;
- создает карточки документов, модулей, интеграций, сценариев, этапов, типов документов и кандидатов требований;
- создает шаблоны Obsidian для документов, требований, замечаний и ADR.

Итог последней пересборки:

```text
documents: 331
chunked_documents: 171
chunks_total: 31270
relationships: 2183
markdown_files: 670
wikilinks: 2813
broken_wikilinks: 0
ambiguous_wikilinks: 0
```

Ключевое ограничение: `relationships_draft.csv` является черновым графом. Связи `mentions_requirement_candidate` и `related_to_module` нужно проверять вручную, потому что часть `requirement_id` может быть номерами разделов, версиями или нормативными кодами.

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
  точечный retrieval-fix внесен;
  chat-level и retrieval-level проверка подтверждают, что запрос про регламенты ведения теперь должен ожидать `Методика/Регламент НСИ`, а не `Реестр НСИ`;
  expectation smoke обновлен на `category=nsi_regulation`, expected_doc_type=`Методика/Регламент НСИ` и expected_terms_in_top5=[регламент ведения, нси];
  остался отдельный quality-follow-up: primary source сейчас выбирается через weak fallback на краткий registry/note chunk, хотя supporting sources уже содержат полноценные регламентные документы.
```

Текущий статус после обновления expectation:

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
`scripts/asu_june_bot_ntk_smoke_eval.py --mode hybrid` после обновления expectation `NTK-SMOKE-017` -> 20/20 ok;
`NTK-SMOKE-007` проходит по усиленному контракту;
`NTK-SMOKE-017` закрыт как устаревший expectation smoke, а не retrieval-баг.
```

Оставшийся нюанс по `NTK-SMOKE-017`:

```text
answer и top-5 уже корректно маршрутизируются в `Методика/Регламент НСИ`,
но в chat-level diagnostics остается `weak_primary_fallback`:
primary поднимается из короткого registry/note chunk,
а полноценные регламентные документы пока лежат в supporting.
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

## MeetingAgent transcription contract на 2026-06-01

Сделан Этап 1 продуктовой транскрибации: общий Python-модуль контракта без зависимости от конкретного ASR backend.

Добавлено:

```text
src/meeting_agent/transcription/schema.py: dataclass-контракт CanonicalSegment, TranscriptDocument, TranscriptionReport;
src/meeting_agent/transcription/normalize.py: нормализация raw segments из разных backend, segment_id/segment_index, фильтр пустых, проверка start/end, сортировка;
src/meeting_agent/transcription/exporters.py: экспорт TXT, MD, SRT, VTT, JSON, JSONL;
src/meeting_agent/transcription/report.py: duration, segments_count, chars_count, empty_dropped, warnings;
tests/unit/test_transcription_contract.py: unit-тесты canonical contract/export/report.
```

Проверено:

```text
python -m pytest tests/unit/test_transcription_contract.py -q
python -m pytest tests/unit/test_transcription_contract.py tests/unit/test_meeting_ingest_audio.py tests/unit/test_meeting_speaker_chunk.py tests/unit/test_meeting_analyze.py tests/unit/test_meeting_search.py -q
```

Этап 2 на 2026-06-01:

```text
scripts/22_transcribe_meeting.py создан как официальный entrypoint;
поддержаны engines: faster-whisper, gigaam, from-segments;
поддержаны options: --model, --language, --compute-type, --force, --resume, --dry-run, --output-formats;
from-segments покрыт unit-тестами без тяжелых ASR-моделей;
meeting.schema.json расширен transcript_txt/transcript_json/transcript_srt/transcript_vtt/transcription_report;
scripts/06_transcribe_meeting.py оставлен как legacy compatibility wrapper.
```

Проверено для Этапа 2:

```text
python -m pytest tests/unit/test_transcription_contract.py tests/unit/test_transcribe_meeting_22.py tests/unit/test_meeting_ingest_audio.py tests/unit/test_meeting_speaker_chunk.py -q
```

Этап 3 на 2026-06-01:

```text
faster-whisper вынесен в src/meeting_agent/transcription/faster_whisper_backend.py;
scripts/22_transcribe_meeting.py больше не использует scripts/06_transcribe_meeting.py для ASR, только для glossary initial_prompt;
defaults faster-whisper берутся из config.yaml/transcription с fallback на predictable values;
приоритет input media: source/audio_16k_mono.wav, затем исходное media из meeting.json;
сегменты сохраняют avg_logprob и no_speech_prob, если faster-whisper их вернул;
transcription_report.json содержит backend_metrics: модель, engine, detected language, duration, device, compute_type, beam_size, vad_filter;
unit-тест покрывает выбор normalized audio и сохранение metrics без загрузки тяжелой ASR-модели.
```

Проверено для Этапа 3:

```text
python -m pytest tests/unit -q
real smoke:
  input: C:\Users\Сотрудник\Desktop\!Проектные документы АСУ\Записи встреч\2026-05-12 14-20-39.mp4
  duration: 34.603 sec
  command: python scripts/22_transcribe_meeting.py --meeting-dir meetings/2026-05-12__transcription-smoke --engine faster-whisper --model small --language ru --compute-type int8 --force
  result: transcribed, 1 segment, transcript TXT/MD/SRT/VTT/JSON/JSONL created
  report: transcript/transcription_report.json with backend_metrics and duration_seconds=34.603
```

Исправлено по результату smoke:

```text
scripts/22_transcribe_meeting.py больше не импортирует scripts/06_transcribe_meeting.py через importlib ради glossary prompt;
duration_seconds в transcription_report использует media duration из faster-whisper backend metrics, если она доступна.
```

## MeetingAgent transcription legacy refactor на 2026-06-01

Сделано:

```text
scripts/08_process_meeting_pipeline.py отвязан от внутренних функций scripts/06_transcribe_meeting.py;
08 теперь использует src/meeting_agent/transcription/faster_whisper_backend.py для ASR окон;
08 использует общий glossary helper и общий markdown transcript exporter;
scripts/06_transcribe_meeting.py превращен в deprecated compatibility wrapper поверх scripts/22_transcribe_meeting.py --engine faster-whisper;
scripts/22_transcribe_meeting.py получил main_with_argv для безопасного wrapper-вызова.
```

Проверено:

```text
python -m pytest tests/unit -q
python scripts/08_process_meeting_pipeline.py --meeting-dir meetings/2026-05-12__transcription-smoke --dry-run --max-windows 1
python scripts/06_transcribe_meeting.py --meeting-dir meetings/2026-05-12__transcription-smoke --dry-run --force --model small
```

## MeetingAgent GigaAM/from-segments backend на 2026-06-01

Сделано:

```text
src/meeting_agent/transcription/gigaam_backend.py добавлен как продуктовый backend;
GigaAM теперь запускается через scripts/22_transcribe_meeting.py --engine gigaam;
рабочая папка backend: transcript/_gigaam/;
сырой output worker-а сохраняется как transcript/_gigaam/raw_segments.jsonl;
audio/chunks остаются внутри карточки встречи, не в Downloads;
canonical outputs остаются transcript/segments.jsonl и transcript/transcript.*;
from-segments фиксирует input_segments и input_rows в transcription_report.backend_metrics.
```

Проверено:

```text
python -m pytest tests/unit -q
python -m py_compile scripts/22_transcribe_meeting.py src/meeting_agent/transcription/gigaam_backend.py tests/unit/test_transcribe_meeting_22.py
real from-segments smoke:
  command: python scripts/22_transcribe_meeting.py --meeting-dir meetings/2026-05-12__transcription-smoke --engine from-segments --segments-path %USERPROFILE%/Downloads/gigaam_support_scheme/segments_gigaam.jsonl --force
  result: transcribed, 17 segments, all canonical transcript exports rebuilt
```

Ограничение реального GigaAM smoke:

```text
попытка запустить --engine gigaam дошла до worker-а, но текущая .venv не содержит GigaAM runtime dependencies;
pip install зависимостей уперся в onnx==1.19.* на Windows/Python 3.14: wheel отсутствует, source build падает на path length;
зависимости вынесены в requirements-gigaam.txt, чтобы не ломать основной requirements.txt;
для end-to-end GigaAM smoke нужен Python/runtime с готовым onnx wheel или отдельная подготовленная GigaAM-среда.
```

## MeetingAgent transcription exports на 2026-06-01

Сделано:

```text
Этап 6 закрыт:
- segments.jsonl остается основным машинным контрактом;
- transcript.json всегда содержит metadata + segments;
- transcript.txt пишет простой читаемый текст;
- transcript.md пишет markdown с таймкодами;
- transcript.srt пишет subtitles с HH:MM:SS,mmm;
- transcript.vtt пишет WEBVTT с HH:MM:SS.mmm;
- SRT/VTT пропускают пустые cues и не падают на пустом списке segments;
- округление миллисекунд сделано предсказуемым, без banker's rounding Python round().
```

Проверено:

```text
.\.venv\Scripts\python.exe -m pytest tests/unit/test_transcription_contract.py tests/unit/test_transcribe_meeting_22.py -q
.\.venv\Scripts\python.exe -m pytest tests/unit -q
python -m py_compile src/meeting_agent/transcription/exporters.py src/meeting_agent/transcription/schema.py scripts/22_transcribe_meeting.py tests/unit/test_transcription_contract.py
```

## MeetingAgent transcription report/idempotency на 2026-06-01

Сделано:

```text
Этап 7 закрыт:
- transcript/transcription_report.json создается после каждого успешного 22_transcribe_meeting.py;
- report содержит engine, model, language, duration_seconds, segments_count, empty_segments_dropped, chars_count, started_at, finished_at, elapsed_seconds, warnings;
- backend_metrics сохраняет технические детали backend-а: input rows, модель, duration, resume flag и другие backend-specific поля.

Этап 8 закрыт:
- если meeting уже transcribed и нет --force, команда завершается no-op с exit code 0 без перезаписи;
- failed/transcribing требуют --force или --resume;
- --resume переиспользует существующий transcript/segments.jsonl и пересобирает downstream transcript artifacts/report;
- при ошибке meeting.json.last_error заполняется stage/message/type/timestamp;
- после успешного прогона проверяется, что все artifact paths для выбранных output formats реально существуют.
```

Проверено:

```text
.\.venv\Scripts\python.exe -m pytest tests/unit/test_transcribe_meeting_22.py tests/unit/test_transcription_contract.py -q
.\.venv\Scripts\python.exe -m pytest tests/unit -q
.\.venv\Scripts\python.exe -m py_compile scripts/22_transcribe_meeting.py tests/unit/test_transcribe_meeting_22.py
```

## Docker packaging на 2026-06-01

Сделано:

```text
Добавлена базовая Docker-упаковка без GigaAM:
- Dockerfile;
- docker-compose.yml;
- .dockerignore;
- config.docker.yaml;
- docs/docker.md;
- README.md обновлен разделом Docker;
- .env.example дополнен Docker-переменными;
- src/asu_june_bot/core/config.py поддерживает MEETING_AGENT_CONFIG_PATH.
```

Назначение:

```text
api: FastAPI Project Knowledge Bot /health, /search, /chat, /ui;
bot: Telegram adapter через profile bot;
volumes: data, logs, meetings, vector_db, watched_folder;
Ollama остается external dependency через host.docker.internal:11434;
GigaAM не включен в основной image.
```

Проверено:

```text
docker compose config --quiet
.\.venv\Scripts\python.exe -m pytest tests/unit -q
.\.venv\Scripts\python.exe -m py_compile src/asu_june_bot/core/config.py scripts/22_transcribe_meeting.py
```

Ограничение:

```text
docker compose build api не выполнен, потому что Docker Desktop/daemon не запущен:
failed to connect to dockerDesktopLinuxEngine.
После запуска Docker Desktop нужно повторить: docker compose build api && docker compose up api.
```

## Runtime smoke ПСИ Справочники на 2026-06-01

Исходный запуск:

```text
source video: C:\Users\Сотрудник\Desktop\!Проектные документы АСУ\Записи встреч\ПСИ Справочники.mp4
meeting_id: 2026-06-01__psi-spravochniki
audio: meetings/2026-06-01__psi-spravochniki/source/audio_16k_mono.wav
duration_seconds: 3083.883
ASR command: scripts/22_transcribe_meeting.py --engine faster-whisper --model small --language ru --compute-type int8 --force
logs: logs/psi_spravochniki_transcribe.out.log, logs/psi_spravochniki_transcribe.err.log
```

Завершено:

```text
22_transcribe_meeting.py:
- engine=faster-whisper
- model=small
- duration_seconds=3083.883
- segments=994
- artifacts: segments.jsonl, transcript.json/md/txt/srt/vtt, transcription_report.json

24_merge_transcript_speakers.py:
- utterances=994
- output: transcript/speaker_transcript.jsonl
- current mode: diarization-lite, speaker=SPEAKER_UNKNOWN

26_chunk_meeting.py:
- chunks=18
- output: transcript/chunks.jsonl
```

Smoke поиска:

```text
31_meeting_search.py по transcript/chunks.jsonl возвращает релевантные фрагменты по запросам
"справочник организации удаление" и "методика группа компаний новатэк".
Ограничение: на raw chunks script печатает ??:??:??, потому что timestamp_start/timestamp_end появляются после index/export шага, а не в transcript/chunks.jsonl.
```

## Full meeting pipeline smoke ПСИ Справочники на 2026-06-02

Завершено для карточки `meetings/2026-06-01__psi-spravochniki`:

```text
27_enrich_meeting_chunks.py:
- chunks=18
- output: artifacts/enriched_chunks.jsonl

28_index_meeting_chunks.py:
- chunks=18
- output: data/meeting_chunks.jsonl
- meeting.rag.indexed_artifacts пополнен transcript/chunks.jsonl и artifacts/enriched_chunks.jsonl

29_analyze_meeting.py --mode extractive:
- processing_status=summarized
- summary.md, protocol.md, decisions.json, tasks.json, risks.json, open_questions.json созданы
- decisions=0
- tasks=44
- risks=0
- open_questions=273
```

Проверено:

```text
31_meeting_search.py по data/meeting_chunks.jsonl с meeting_id=2026-06-01__psi-spravochniki возвращает timestamp_start/timestamp_end и релевантные фрагменты по запросам:
- "справочник организации удаление"
- "группа компаний новотек методика"
```

Замечание по качеству:

```text
extractive/heuristic pipeline рабочий, но сильно переизвлекает tasks/open_questions из обычной речи.
Для качественного memo/protocol нужен следующий проход через реальный LLM map-reduce и более строгие post-filters.
```

## LLM map-reduce smoke ПСИ Справочники на 2026-06-02

Проверено:

```text
29_analyze_meeting.py --mode ollama-map-reduce
model=qwen2.5:7b-instruct
model=qwen3:4b
meeting=2026-06-01__psi-spravochniki
```

Результат:

```text
На текущей CPU-машине полноценный MAP/REDUCE для этой встречи непрактичен.
qwen2.5:7b-instruct слишком медленный для chunk-level map.
qwen3:4b тоже не укладывается в разумный runtime.

Прагматичный прогон с qwen3:4b и timeout=30 показал:
- все 18 MAP chunks ушли в fallback по read timeout;
- LLM-улучшения качества не получено;
- финальные artifacts остались от extractive run.
```

Вывод:

```text
Для текущего железа quality path должен идти либо через:
- более сильные post-filters поверх extractive pipeline;
- более маленькие chunks/prompts;
- отдельную более быструю LLM runtime/GPU;
- либо внешний LLM-only step вне основного CPU pipeline.
```

## NTK realistic-100 P1 Passport закрыт на 2026-06-02

Рабочая ветка: `codex/ntk-p1-passport-routing`.

Закрыт bucket `P1 Passport`:

```text
NTK100-NEW-063
NTK100-NEW-064
NTK100-NEW-065
```

Что было сломано:

```text
063: Паспорт ИС поднимал только один фрагмент Table 2, поэтому LLM считал список связанных документов неполным.
064: Table 3 попадала частично, но LLM ставил false no_answer по приложениям.
065: exact purpose chunk "Система предназначена..." был найден search-level, но LLM всё равно ставил false no_answer.
```

Что изменено:

```text
- query_expansion.yaml: Passport expansion для Table 2 related docs.
- BM25/post-rerank: Passport boosts для Table 2, Table 3, exact system purpose.
- ContextBuilder: Passport-specific routes выполняются до общего DOCUMENT_OVERVIEW.
- ContextBuilder: строки Passport Table 2/Table 3 агрегируются в один source block.
- BuiltContext.to_dict(): primary/supporting preview увеличен до 1800 символов.
- Chat fallback: узкий Passport fallback для related documents / appendices / system purpose false no_answer.
```

Проверка:

```text
targeted chat eval 063-065:
- total=3
- answered=3
- failures=0
- parse_errors=0

pytest tests/asu_june_bot -q:
- 170 passed

compileall src/asu_june_bot:
- ok
```

Quality report:

```text
docs/quality/ntk_realistic_100_new_p1_passport_eval_2026-06-02.md
```

Следующий рабочий bucket:

```text
P1 AD/app_ccpm.
Важно: вопрос про группы AD для ролей строительного контроля должен поднимать ПР Стройконтроль, приложение 2 - группы, а не только СоИ AD.
```

## NTK realistic 100 v2 завершен на 2026-06-02

Прогон нового набора `NTK realistic 100 v2` завершен штатно.

Артефакты опубликованы в Git:

```text
docs/quality/ntk_realistic_100_v2_queries_2026-06-02.jsonl
docs/quality/ntk_realistic_100_v2_eval_report.jsonl
docs/quality/ntk_realistic_100_v2_eval_review.jsonl
docs/quality/ntk_realistic_100_v2_eval_review_summary.json
docs/quality/ntk_realistic_100_v2_eval_status_2026-06-02.md
```

Параметры:

```text
model: qwen2.5:7b-instruct
mode: hybrid
active_corpus: ntk
rows: 100/100
returncode=0: 100/100
parse_errors: 0
failures: 0
```

Распределение runtime statuses:

```text
answered: 39
no_answer: 33
clarify: 20
refused: 7
validation_failed: 1
```

Время:

```text
avg_duration_sec: 84.463
max_duration_sec: 300.377
min_duration_sec: 0.676
```

Текущий вывод:

```text
Технически прогон успешен.
Quality verdict еще не выставлен.
Следующий шаг - ручная разметка review_verdict/review_comment в docs/quality/ntk_realistic_100_v2_eval_review.jsonl.
```

## NTK realistic 100 v2 ручная разметка опубликована на 2026-06-03

Ручная разметка `NTK realistic 100 v2` получена и слита в полные review-файлы.

Артефакты:

```text
docs/quality/ntk_realistic_100_v2_manual_review_patch.jsonl
docs/quality/ntk_realistic_100_v2_manual_review_summary_2026-06-03.md
docs/quality/ntk_realistic_100_v2_eval_review_filled.jsonl
docs/quality/ntk_realistic_100_v2_eval_review_compact_filled.jsonl
```

Проверка merge:

```text
full_patched: 100/100
compact_patched: 100/100
bad_json: 0
```

Manual verdict counts:

```text
ok: 36
low_score: 34
bad_refusal: 20
garbage_source: 6
out_of_scope: 3
missing_source: 1
```

Status x verdict:

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

Вывод:

```text
Технически прогон успешен, но quality-pass не подтвержден.
Главный следующий bucket: false clarify / bad_refusal.
Начинать надо с guard/scope, потому что он блокирует retrieval и искажает оценку качества поиска.
```

False clarify project cases:

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

Out-of-scope false clarify:

```text
NTK100-V2-093
NTK100-V2-095
NTK100-V2-096
```

## NTK v2 false clarify guard slice зеленый на 2026-06-03

После коммита `ec9a964` локальный guard regression все еще падал на форме:

```text
Какие требования к резервному копированию и восстановлению указаны в архитектурных документах?
```

Причина:

```text
RuleBasedScopeClassifier имел project markers в именительном падеже:
- резервное копирование;
- восстановление.

Запрос использовал дательный падеж:
- резервному копированию;
- восстановлению.

Из-за этого classifier видел только generic markers "требования" / "документ" и возвращал clarify.
```

Дополнительно после первого фикса проявились еще две формы:

```text
Какие результаты ожидаются после выполнения сценариев по актам и предписаниям?
Какие ограничения доступа описаны для работы с исполнительной документацией?
```

Исправление:

```text
src/asu_june_bot/guardrails/scope_classifier.py

Добавлены точечные project markers:
- резервному копированию;
- резервного копирования;
- восстановлению;
- восстановления;
- архитектурные документы;
- архитектурных документах;
- актам и предписаниям;
- сценариев по актам;
- сценариев по актам и предписаниям;
- результаты ожидаются;
- после выполнения сценариев;
- ограничения доступа;
- работы с исполнительной документацией.
```

Проверка:

```text
python -m pytest tests/asu_june_bot/test_project_guard_v2.py -q
12 passed

python -m pytest tests/asu_june_bot -q
172 passed

python -m compileall -q src/asu_june_bot
ok
```

Статус:

```text
False clarify guard regression slice зеленый локально.
Следующий шаг - targeted eval по 20 bad_refusal/false clarify cases из NTK v2 manual review.
```

## NTK realistic 500 v3 guard-only baseline на 2026-06-04

Снят дешевый baseline только через `ProjectGuard.evaluate_v2()`, без retrieval, embeddings и LLM.

Артефакты:

```text
scripts/asu_june_bot_guard_dataset_eval.py
docs/quality/ntk_realistic_500_v3_guard_only_report_2026-06-04.jsonl
docs/quality/ntk_realistic_500_v3_guard_only_summary_2026-06-04.md
```

Команда:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_guard_dataset_eval.py
```

Результат:

```text
total: 500
ok: 411
false_clarify_project: 65
false_clarify_boundary: 20
false_allow: 4

actual_status:
ok: 389
clarify: 85
refused: 26
```

Вывод:

```text
Guard остается значимым блокером: 65 project-вопросов уходят в clarify до retrieval.
Одновременно есть P0-риск: 4 harmful_security вопроса ошибочно проходят как ok из-за сильных project markers
PostgreSQL / LDAPS / app_ccpm / ЭЦП.
```

Следующий порядок:

```text
1. Сначала закрыть 4 false_allow harmful_security, чтобы не ухудшить безопасность.
2. Затем точечно расширять project-recognition для шаблонов:
   - "какие источники подтверждают ...";
   - "какие разделы документации нужно использовать ...";
   - "что в функционально-технических требованиях указано ...";
   - domain anchors: журнал замечаний, обязательные поля, история изменений, разграничение доступа,
     печатные формы, поиск/фильтрация, Consul, Patroni.
3. После guard-fix повторить guard-only 500 baseline.
4. Только после снижения guard false_clarify переходить к retrieval/validator baseline.
```
