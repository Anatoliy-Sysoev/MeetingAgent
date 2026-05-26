# TODO

Обновлено: 2026-05-26.

## Retrieval quality roadmap

### Реализовано

```text
realistic-100 eval
realistic-500 eval
manual review pipeline
approved regression set
failure bucket classification
hard source-quality gate
hybrid vector+lexical rerank
metadata-aware retrieval
SQLite FTS5 lexical retrieval
bucket-driven retrieval expansion
harmful security guard
project security allowlist
```

Новые retrieval-компоненты:

```text
scripts/rag_bucket_quality.py
scripts/18_targeted_bucket_eval.py
```

Bucket-driven retrieval:

```text
ФТТ bucket
ЦТА bucket
ПР bucket
СоИ AD/LDAPS bucket
MDR/НСИ/Bearer bucket
guard quality bucket
hallucination bucket
```

## Следующий этап

### Priority 0

```text
Принять решение по текущей NTK Yandex embeddings/index build:
- дать старой сборке закончиться как baseline старого чанкинга;
- или остановить и пересобрать после chunk-quality фиксов.
```

Проверка прогресса:

```powershell
(Get-Content .\data\asu_june_bot_ntk\embeddings_cache_v2.jsonl -Encoding UTF8).Count
```

Проверка watchdog:

```powershell
Get-Content .\logs\ntk_yandex_index_watchdog.log -Tail 20 -Encoding UTF8
```

После появления:

```text
data/asu_june_bot_ntk/numpy_index_v2/manifest.json
```

запустить hybrid smoke:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_ntk_smoke_eval.py `
  --mode hybrid `
  --chunks-path data\asu_june_bot_ntk\chunks_v2.jsonl `
  --index-dir data\asu_june_bot_ntk\numpy_index_v2 `
  --output data\asu_june_bot_ntk\smoke_eval_hybrid.jsonl
```

Дефолт бота переключать на `data/asu_june_bot_ntk` только если hybrid smoke лучше текущего корпуса.

Incremental update для Yandex-папки делать после подтверждения качества нового корпуса.

### Priority 0.1

Пересобрать NTK corpus после chunk-quality фиксов:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_extract_text_v2.py `
  --project-root "$env:USERPROFILE\Desktop\Yandex.Disk\Документы НТК Сдача" `
  --source-links data\asu_june_bot_ntk\source_links.jsonl `
  --output-dir data\asu_june_bot_ntk\extracted_v2 `
  --reset

.\.venv\Scripts\python.exe scripts\asu_june_bot_build_chunks_v2.py `
  --blocks-path data\asu_june_bot_ntk\extracted_v2\blocks.jsonl `
  --output-dir data\asu_june_bot_ntk
```

После пересборки проверить:

```text
gt6000 должен резко снизиться;
lt80 должен снизиться за счёт удаления микрошума;
unknown document_type должен снизиться;
source_url coverage не должен ухудшиться;
4 СВОК РД.xlsx не должен создавать 100k+ chunks.
Excel-листы с шириной >120 колонок должны попадать в stderr warning,
а после hard cap 250 не должны раздувать embedding text.
```

Не делать пока без отдельного решения:

```text
hardcoded fallback source_url;
канонизация версий ПР как единственный режим;
удаление всех WIP/pptx из корпуса.
```

### Priority 1

```text
Targeted rerun по каждому bucket
```

Команды:

```powershell
python scripts/18_targeted_bucket_eval.py --review data/realistic_500_eval_review.jsonl --bucket ftt_missing
python scripts/18_targeted_bucket_eval.py --review data/realistic_500_eval_review.jsonl --bucket cta_missing
python scripts/18_targeted_bucket_eval.py --review data/realistic_500_eval_review.jsonl --bucket pr_missing
python scripts/18_targeted_bucket_eval.py --review data/realistic_500_eval_review.jsonl --bucket soi_ad_missing
python scripts/18_targeted_bucket_eval.py --review data/realistic_500_eval_review.jsonl --bucket soi_nsi_mdr_bearer
```

### Priority 2

```text
Improve retrieval quality by bucket
```

Для каждого bucket:

```text
aliases
anchors
metadata routing
rerank boosts
path routing
chunk overlap tuning
```

### Priority 3

```text
realistic-500 rerun after retrieval fixes
```

Цель:

```text
reduce missing_source
reduce low_score
reduce garbage_source
remove hallucination
increase grounded answered
```

## Long-term ideas

```text
DSPy retrieval optimization
cross-encoder rerank
adaptive chunk retrieval
query decomposition
agentic retrieval
graph retrieval
citation validator
structured answer synthesis
```

## GigaAM / ASR Backlog

```text
При следующем ручном GigaAM-прогоне использовать scripts/run_gigaam_transcribe.ps1,
а не inline-команды из чата.

Если GigaAM станет постоянным ASR-путем, добавить интеграцию с meeting card:
source/media_files -> transcript/segments.jsonl -> meeting.json status.

Проверить качество GigaAM против faster-whisper на 2-3 русскоязычных встречах:
термины проекта, обрывы на чанках, шум, имена, пригодность для source_refs.

Не коммитить runtime output из Downloads или meetings/**/transcript;
для Git фиксировать только отчет в docs/references или curated transcript excerpt.
```

## MeetingAgent MVP Pipeline

```text
Принят roadmap от ingest записи до meeting search:
docs/meeting_agent_architecture.md
docs/meeting_agent_mvp_scope.md

Основной checklist ФТТ обновлен:
docs/product/PROJECT_STAGES_AND_FTT.md
```

### Priority 0

```text
Реализовать scripts/20_ingest_meeting.py:
- вход mp4/mp3/wav/m4a;
- создание meetings/<meeting_id>/;
- meeting_id как YYYY-MM-DD__slug;
- копирование raw/source файла;
- meeting.json по configs/schemas/meeting.schema.json;
- processing_status = new;
- идемпотентность и понятная ошибка при конфликте slug.
```

Статус: реализовано 2026-05-26. Следующие улучшения: пакетный watcher и очередь jobs.

### Priority 0.1

```text
Реализовать scripts/21_extract_audio.py:
- ffmpeg -> source/audio_16k_mono.wav;
- mono 16000 Hz;
- status/report без пересоздания успешного результата без --force;
- ошибки писать в meeting.json.last_error или pipeline report.
```

Статус: реализовано 2026-05-26. Успешный шаг оставляет processing_status=new, потому что audio_extracted пока не является статусом meeting.schema.json.

### Priority 1

```text
Свести существующий scripts/06_transcribe_meeting.py с целевым шагом 22_transcribe_meeting:
- проверить segment schema;
- добавить txt/srt/vtt/json exports при необходимости;
- не ломать текущий transcript/segments.jsonl и transcript/transcript.md.
```

### Priority 2

```text
Сделать diarization-lite:
- speaker_transcript.jsonl;
- speaker = SPEAKER_UNKNOWN без pyannote;
- будущий scripts/23_diarize_meeting.py остается optional.
```

### Priority 3

```text
Реализовать meeting-aware chunking и indexing:
- scripts/26_chunk_meeting.py;
- scripts/28_index_meeting_chunks.py;
- source_type meeting_chunk/meeting_decision/meeting_action_item;
- timestamps и meeting_id в metadata;
- source-quality gate для meeting chunks.
```
