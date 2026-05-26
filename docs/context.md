# Контекст проекта

Обновлено: 2026-05-26.

## NTK Yandex corpus chunk quality

Ветка `codex/ntk-yandex-corpus` используется для отдельного корпуса по очищенной папке:

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

Полная польза появится после пересборки extractor -> chunks -> embeddings/index. Текущая long-running embeddings-сборка идёт по старому `chunks_v2.jsonl`; она может остаться как baseline старого чанкинга или быть остановлена отдельным решением.

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
harmful security queries -> refused
project security/auth questions -> allowed
```

Примеры allowed:

```text
Bearer Token MDR
JWT/OAuth/OIDC в проекте
LDAPS/AD интеграция
```

Примеры refused:

```text
SQL injection payload
взлом
обход авторизации
эксплойт
```

## NTK Yandex Corpus

2026-05-25 создана ветка:

```text
codex/ntk-yandex-corpus
```

Цель ветки: собрать отдельный Project Knowledge Bot corpus по очищенной папке Яндекс.Диска:

```text
C:\Users\Сотрудник\Desktop\Yandex.Disk\Документы НТК Сдача
```

Runtime-каталог:

```text
data/asu_june_bot_ntk/
```

Добавлены:

```text
scripts/asu_june_bot_build_source_links.py
scripts/asu_june_bot_ntk_smoke_eval.py
scripts/monitor_asu_june_bot_ntk_index.ps1
docs/quality/ntk_yandex_smoke_questions.jsonl
docs/subprojects/asu-june-bot/NTK_YANDEX_CORPUS.md
```

В `src/asu_june_bot` добавлена сквозная поддержка:

```text
source_url в ingestion models
source_url в chunks metadata
source_url в SearchResult.to_dict()
source_url в ChatSource
source_url в CLI formatter
source_url как кликабельная ссылка в Web UI
```

Собрано локально:

```text
source_links.jsonl: 1166 local files, 325 matched source_url
extracted_v2: 171 documents, 31018 blocks, 0 errors
chunks_v2.jsonl: 31136 chunks
chunks with source_url: 29196
```

BM25-only smoke:

```text
cases: 20
ok: 8
source_url_in_top5: 12
status_counts: ok=12, clarify=7, refused=1
```

Решение:

```text
дефолт бота на NTK corpus пока не переключён
ждём окончания embeddings/vector index
после готовности data/asu_june_bot_ntk/numpy_index_v2 выполнить hybrid smoke
```

Фоновая сборка индекса запущена:

```text
script: scripts/asu_june_bot_build_index_v2.py
chunks: data/asu_june_bot_ntk/chunks_v2.jsonl
cache: data/asu_june_bot_ntk/embeddings_cache_v2.jsonl
index: data/asu_june_bot_ntk/numpy_index_v2
report: data/asu_june_bot_ntk/index_v2_report.json
```

Фоновый watchdog запущен:

```text
scripts/monitor_asu_june_bot_ntk_index.ps1 -Loop -IntervalMinutes 30
```

Watchdog не удаляет данные. Если build-процесс упадёт до появления `manifest.json`, он перезапустит тот же resumable build.

## 2026-05-26 — GigaAM-прогон записи про схему уровня поддержки

Зафиксирован ручной ASR-прогон файла `%USERPROFILE%\Downloads\Схема уровня поддержки.mp4` через локальный `GigaAM`.

Результат прогона:

```text
duration: 00:06:29
model: gigaam/v3_e2e_rnnt
chunks: 17
nonempty_chunks: 17
errors: 0
runtime output: %USERPROFILE%\Downloads\gigaam_support_scheme
tracked report: docs/references/GIGAAM_SUPPORT_SCHEME_RUN_2026-05-26.md
```

Добавлен воспроизводимый wrapper:

```text
scripts/run_gigaam_transcribe.ps1
scripts/gigaam_transcribe_chunks.py
docs/operations/GIGAAM_TRANSCRIPTION.md
```

Важная деталь окружения: GigaAM и `sentencepiece` могут падать на tokenizer в пути с кириллицей `%USERPROFILE%\.cache\gigaam`. Для стабильного повторного запуска используется ASCII-cache `%ProgramData%\gigaam_cache`; wrapper копирует туда локальные файлы модели, если они уже есть в user-cache.

## 2026-05-26 — MeetingAgent roadmap принят как MVP-план

Зафиксирован детальный план развития MeetingAgent от ingest записи до meeting search:

```text
docs/meeting_agent_architecture.md
docs/meeting_agent_mvp_scope.md
```

План принят с адаптацией под уже существующие решения:

```text
meeting_id остается slug YYYY-MM-DD__short-title, не UUID;
каноническая карточка встречи остается meetings/<meeting_id>/, не data/meetings/<meeting_id>/;
текущие статусы meeting.schema.json сохраняются до отдельной миграции схемы;
scripts/06_transcribe_meeting.py, 07_generate_meeting_artifacts.py и 08_process_meeting_pipeline.py считаются существующей базой для новых шагов 22/29;
diarization не блокирует MVP: допустим SPEAKER_UNKNOWN.
```

Следующий практический шаг: реализовать `scripts/20_ingest_meeting.py` и `scripts/21_extract_audio.py` поверх текущего `configs/schemas/meeting.schema.json`, не создавая второй несовместимый storage contract.
