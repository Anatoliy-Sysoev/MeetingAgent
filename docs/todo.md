# TODO

Обновлено: 2026-05-27.

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
NTK Yandex corpus после chunk-quality фиксов пересобран:
- extracted_v2 готов;
- chunks_v2.jsonl: 31270 chunks;
- numpy_index_v2/manifest.json создан;
- BM25 smoke: 8/20 ok;
- hybrid smoke после расширения project markers/routing: 20/20 ok.
```

Ручная проверка hybrid smoke уже выполнена:

```text
strict source-supported pass: 18/20
partial: 2/20
fail: 0/20
```

Следующий шаг: включить NTK corpus только через feature flag, не как безусловный default.

Перед глобальным переключением нужно закрыть два follow-up кейса:

```text
NTK-SMOKE-012:
- добиться, чтобы в top-N стабильно попадала таблица соответствия app_ccpm-групп AD и ролей

NTK-SMOKE-017:
- улучшить routing запросов про регламенты ведения объектов НСИ в МВД/регламентные документы, а не только в Реестр НСИ
```

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

Статус: реализовано 2026-05-26 через `scripts/24_merge_transcript_speakers.py`.

### Priority 3

```text
Реализовать meeting-aware chunking и indexing:
- scripts/26_chunk_meeting.py;
- scripts/28_index_meeting_chunks.py;
- source_type meeting_chunk/meeting_decision/meeting_action_item;
- timestamps и meeting_id в metadata;
- source-quality gate для meeting chunks.
```

Статус: реализовано 2026-05-26 через `scripts/26_chunk_meeting.py` и `scripts/28_index_meeting_chunks.py`.

### Priority 4

```text
Реализовать semantic enrichment и meeting indexing:
- scripts/27_enrich_meeting_chunks.py;
- scripts/28_index_meeting_chunks.py;
- topic/semantic_type/entities;
- decisions/action_items/risks/open_questions candidates;
- source_type meeting_chunk в retrieval metadata;
- smoke search по одной встрече.
```

Статус: реализовано 2026-05-26:

```text
scripts/27_enrich_meeting_chunks.py готов как heuristic MVP enrichment;
scripts/28_index_meeting_chunks.py готов как export в data/meeting_chunks.jsonl;
meeting_chunk добавлен в default source policy/index source types;
scripts/31_meeting_search.py готов для smoke search по встречам;
на реальной встрече 2026-05-26__support-scheme собран data/meeting_numpy_index: 3 chunks, bge-m3, dim=1024.
```

Осталось:

```text
заменить heuristic enrichment на LLM map/reduce для production artifacts.
```

Статус update 2026-05-26:

```text
meeting search CLI реализован через scripts/31_meeting_search.py;
smoke lexical search работает без Ollama и отдельного numpy index;
отдельный smoke numpy index по data/meeting_chunks.jsonl собран на встрече 2026-05-26__support-scheme;
runtime artifacts лежат в meetings/2026-05-26__support-scheme/ и data/meeting_* и не коммитятся.
```

Следующий шаг:

```text
LLM map/reduce extraction реализован в scripts/29_analyze_meeting.py;
structured artifacts с source timestamps созданы на smoke-встрече 2026-05-26__support-scheme;
подключить meeting search к будущему API/боту.
```

### Priority 5

```text
Подключить structured meeting artifacts к индексации и поиску:
- экспортировать decisions/tasks/risks/open_questions как отдельные source_type;
- добавить meeting_decision/meeting_action_item/meeting_risk/meeting_open_question buckets;
- проверить 31_meeting_search.py и будущий bot/API на вопросах "какие решения", "какие задачи", "какие риски";
- сохранить таймкоды в ответах.
```

Статус на 2026-05-27:

```text
Базовый meeting pipeline от готовой транскрибации до structured artifacts реализован и прогнан на 2026-05-26__support-scheme.
В Git зафиксированы код, тесты и документация; runtime artifacts остаются ignored.
Главная техническая проблема сейчас — стабильность локального LLM REDUCE на CPU: qwen2.5:7b-instruct может уходить в timeout, qwen3:8b слишком медленный, а ответы иногда требуют JSON fallback.
```

Ближайшие действия:

```text
1. Реализовать scripts/32_index_meeting_artifacts.py:
   - decisions.json -> source_type=meeting_decision;
   - tasks.json -> source_type=meeting_action_item;
   - risks.json -> source_type=meeting_risk;
   - open_questions.json -> source_type=meeting_open_question.
2. Расширить 31_meeting_search.py или retrieval buckets, чтобы запросы "какие задачи/решения/риски" били по structured artifacts, а не только по raw chunks.
3. Стабилизировать LLM:
   - уменьшить размер REDUCE prompt;
   - добавить chunk-level dedupe до REDUCE;
   - протестировать qwen3:4b и mistral:7b-instruct-q4_0;
   - оставить --strict-llm только для отладки, а fallback как production-safe режим.
4. После этого подключить meeting-search слой к API/боту.
```
