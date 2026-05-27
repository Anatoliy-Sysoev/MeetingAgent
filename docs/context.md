# Контекст проекта

Обновлено: 2026-05-27.

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

Ручная source-supported проверка retrieval grounding:

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

Решение: NTK corpus можно включать только через feature flag. Безусловным глобальным default корпус пока не становится.

Follow-up кейсы:

```text
NTK-SMOKE-012:
  нужно подтянуть в top-N таблицу соответствия app_ccpm-групп AD и ролей строительного контроля

NTK-SMOKE-017:
  кроме Реестра НСИ нужно явнее маршрутизировать запросы про регламенты ведения в МВД/регламентные документы
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
chunks_v2.jsonl: 31270 chunks
chunks with source_url: 93.8%
numpy_index_v2: 31270 indexed chunks
```

BM25-only smoke:

```text
cases: 20
ok: 8
source_url_in_top5: 12
status_counts: ok=12, clarify=7, refused=1
```

Hybrid smoke после расширения project markers и routing:

```text
cases: 20
ok: 20
source_url_in_top5: 19
status_counts: ok=19, refused=1
failed_ids: []
```

Решение:

```text
дефолт бота на NTK corpus пока не переключён
провести ручной просмотр smoke answers/sources
incremental update проектировать только после подтверждения качества
```

Индекс собран:

```text
script: scripts/asu_june_bot_build_index_v2.py
chunks: data/asu_june_bot_ntk/chunks_v2.jsonl
cache: data/asu_june_bot_ntk/embeddings_cache_v2.jsonl
index: data/asu_june_bot_ntk/numpy_index_v2
report: data/asu_june_bot_ntk/index_v2_report.json
manifest: data/asu_june_bot_ntk/numpy_index_v2/manifest.json
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

## 2026-05-26 — ФТТ MeetingAgent актуализированы

Обновлен основной execution checklist:

```text
docs/product/PROJECT_STAGES_AND_FTT.md
```

Синхронизированы статусы:

```text
Project Knowledge Bot: /search, /chat, Web UI, Telegram adapter и QH-1..QH-5 отмечены как реализованные;
RAG quality: realistic eval, manual review, approved regression set и targeted bucket eval отмечены как рабочие;
Meeting pipeline: добавлена привязка к roadmap 2026-05-26 и ближайшим шагам 20/21;
GigaAM: зафиксирован как fallback/experimental ASR workflow, не как замена основного faster-whisper пути.
```

## 2026-05-26 — Реализован первый слой FTT-MA-08/09/11

Добавлены:

```text
scripts/20_ingest_meeting.py
scripts/21_extract_audio.py
tests/unit/test_meeting_ingest_audio.py
```

Что закрывает:

```text
FTT-MA-08: входящий mp4/mp3/wav/m4a превращается в карточку встречи;
FTT-MA-09: meeting.json создается по configs/schemas/meeting.schema.json;
FTT-MA-11: нормализованный source/audio_16k_mono.wav фиксируется как MIX-аудио с duration metadata.
```

Принятое поведение: `21_extract_audio.py` на успешном извлечении не меняет `processing_status` на несуществующий `audio_extracted`, а оставляет `new`, чтобы текущий ASR-контракт мог продолжать работу без миграции схемы. При ошибке встреча переводится в `failed` с `last_error`.

Проверка:

```text
.\.venv\Scripts\python.exe -m pytest tests\unit\test_meeting_ingest_audio.py -q
2 passed
```

## 2026-05-26 — Реализован speaker transcript и meeting-aware chunking

Добавлены:

```text
scripts/24_merge_transcript_speakers.py
scripts/26_chunk_meeting.py
tests/unit/test_meeting_speaker_chunk.py
```

Расширена схема:

```text
configs/schemas/meeting.schema.json
artifacts.speaker_transcript
artifacts.chunks
```

Поведение:

```text
24_merge_transcript_speakers.py читает transcript/segments.jsonl и создает transcript/speaker_transcript.jsonl + .txt;
без diarization каждая реплика получает speaker=SPEAKER_UNKNOWN, speaker_name=SPEAKER_UNKNOWN, source=MIX;
26_chunk_meeting.py создает transcript/chunks.jsonl с source_type=meeting_chunk, timestamps, speakers, sources и utterance_ids;
chunker ограничивает chunk по времени и символам, но не разрывает отдельную реплику.
```

Проверка:

```text
.\.venv\Scripts\python.exe -m pytest tests\unit\test_meeting_speaker_chunk.py tests\unit\test_meeting_ingest_audio.py -q
4 passed
```

## 2026-05-26 — Реализован semantic enrichment и meeting index export

Добавлены:

```text
scripts/27_enrich_meeting_chunks.py
scripts/28_index_meeting_chunks.py
tests/unit/test_meeting_enrich_index.py
```

Расширена схема:

```text
configs/schemas/meeting.schema.json
artifacts.enriched_chunks
```

Интеграция с retrieval:

```text
scripts/asu_june_bot_build_index_v2.py default source types теперь включают meeting_chunk;
src/asu_june_bot/retrieval/source_policy.py default allowed source types теперь включают meeting_chunk;
meeting_chunk получил source weight 0.88.
```

Поведение:

```text
27_enrich_meeting_chunks.py добавляет topic, semantic_type, entities, decisions/action_items/risks/open_questions candidates, importance_score, quality_flags;
enrichment_mode=heuristic_v1 и needs_review=true, поэтому это первичный MVP-слой, а не финальная LLM-аналитика;
28_index_meeting_chunks.py экспортирует enriched chunks в data/meeting_chunks.jsonl в RAG-compatible формате с meeting_id, title, timestamps, speakers, topic и semantic_type.
```

Проверка:

```text
.\.venv\Scripts\python.exe -m pytest tests\unit\test_meeting_enrich_index.py tests\unit\test_meeting_speaker_chunk.py tests\unit\test_meeting_ingest_audio.py -q
6 passed
```

## 2026-05-26 — Добавлен smoke meeting search CLI

Добавлены:

```text
scripts/31_meeting_search.py
tests/unit/test_meeting_search.py
```

Поведение:

```text
31_meeting_search.py читает data/meeting_chunks.jsonl;
по умолчанию ищет только source_type=meeting_chunk;
работает без Ollama и numpy index через lexical smoke search;
сохраняет в ответе meeting_id, meeting_title, timestamp_start/timestamp_end, speakers, topic, semantic_type и text preview;
поддерживает --meeting-id, --top-k и --json.
```

Команда отдельной smoke-сборки numpy index по встречам зафиксирована в `docs/operations/MEETING_PIPELINE.md`.

Проверка:

```text
.\.venv\Scripts\python.exe -m pytest tests\unit\test_meeting_search.py -q
3 passed
```

## 2026-05-26 — Первый реальный smoke-прогон встречи

Использована запись `Схема уровня поддержки`. Исходный mp4 по старому пути отсутствовал, поэтому карточка создана из готового GigaAM output:

```text
C:\Users\Сотрудник\Downloads\gigaam_support_scheme\audio_16k_mono.wav
C:\Users\Сотрудник\Downloads\gigaam_support_scheme\segments_gigaam.jsonl
```

Runtime artifacts, которые не коммитятся:

```text
meetings/2026-05-26__support-scheme/
data/meeting_chunks.jsonl
data/meeting_embeddings_cache.jsonl
data/meeting_numpy_index/
data/meeting_index_report.json
```

Результат:

```text
24_merge_transcript_speakers.py: 17 utterances
26_chunk_meeting.py: 3 chunks
27_enrich_meeting_chunks.py: 3 enriched chunks
28_index_meeting_chunks.py: 3 rows in data/meeting_chunks.jsonl
asu_june_bot_build_index_v2.py: 3 bge-m3 embeddings, dim=1024, data/meeting_numpy_index built
31_meeting_search.py: smoke search по meeting_id=2026-05-26__support-scheme возвращает 3 фрагмента с таймкодами
```

## 2026-05-27 — Реализован LLM map-reduce analysis

Добавлены:

```text
scripts/29_analyze_meeting.py
tests/unit/test_meeting_analyze.py
```

Поведение:

```text
29_analyze_meeting.py читает artifacts/enriched_chunks.jsonl;
MAP вызывает локальный Ollama по каждому meeting chunk;
REDUCE объединяет MAP partials в summary/decisions/tasks/risks/open_questions;
каждый финальный пункт получает source_refs с path/start/end/quote;
итоговые JSON валидируются по configs/schemas/meeting.*.schema.json;
при битом JSON или timeout скрипт сохраняет raw output и использует fallback только для сломанной части;
успешный запуск переводит meeting.json processing_status в summarized.
```

Первый реальный прогон:

```text
meeting_id: 2026-05-26__support-scheme
model: qwen2.5:7b-instruct
mode: ollama-map-reduce
MAP: 3 chunks
REDUCE: timeout, использован deterministic fallback поверх MAP partials
decisions: 3
tasks: 5
risks: 3
open_questions: 3
status: summarized
```

Проверка:

```text
.\.venv\Scripts\python.exe -m pytest tests\unit\test_meeting_analyze.py tests\unit\test_meeting_search.py tests\unit\test_meeting_enrich_index.py -q
7 passed
```

## 2026-05-27 — Итоговый статус MeetingAgent pipeline

Что сделано:

```text
ingest/audio source: карточка встречи создается и хранит source media;
ASR import: готовые GigaAM segments можно использовать как transcript/segments.jsonl;
speaker transcript: создается diarization-lite с SPEAKER_UNKNOWN;
meeting chunking: transcript режется на chunks с таймкодами;
semantic enrichment: heuristic MVP добавляет topic/semantic_type/entities/candidates;
meeting index export: data/meeting_chunks.jsonl формируется из enriched chunks;
smoke meeting search: scripts/31_meeting_search.py ищет по meeting chunks и возвращает таймкоды;
smoke numpy index: data/meeting_numpy_index собран по meeting_chunks.jsonl;
LLM map-reduce analysis: scripts/29_analyze_meeting.py создает summary/protocol/decisions/tasks/risks/open_questions;
source_refs: итоговые structured artifacts содержат path/start/end/quote.
```

Что осталось:

```text
экспортировать structured artifacts как отдельные source_type: meeting_decision, meeting_action_item, meeting_risk, meeting_open_question;
добавить buckets для вопросов по решениям, задачам, рискам и открытым вопросам;
подключить meeting search к API/боту;
улучшить качество extraction: убрать мусорные задачи, усилить dedupe, отделить реальные решения от предложений;
добавить speaker mapping и позднее diarization через pyannote;
сделать DOCX/Markdown protocol export после стабилизации JSON-артефактов.
```

Текущая проблема:

```text
локальный REDUCE на qwen2.5:7b-instruct может не укладываться в timeout;
qwen3:8b на CPU слишком медленный для надежного полного map-reduce;
иногда LLM возвращает битый JSON или лишний текст, поэтому включен fallback;
fallback сохраняет работоспособность pipeline, но качество итогов пока требует ручного review;
runtime artifacts в meetings/ и data/meeting_* ignored и не являются переносимым Git-источником истины.
```
