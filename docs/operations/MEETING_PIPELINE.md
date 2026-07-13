# Поток Обработки Встреч

## Цель

Превратить каждую запись встречи в переиспользуемое знание проекта.

## Целевой Поток

1. Новое видео или аудио появляется в `watched_folder/`.
2. Наблюдатель ждет, пока файл перестанет изменяться.
3. Запускается транскрибация через Whisper-совместимую модель.
4. Транскрипт сохраняется с таймкодами.
5. Локальная модель генерирует:
   - краткое memo;
   - формальный протокол;
   - решения;
   - задачи;
   - риски;
   - открытые вопросы.
6. RAG классифицирует связь с:
   - этапом проекта;
   - ФТТ;
   - задачей;
   - сдачным результатом;
   - существующим документом.
7. Артефакты сохраняются в папку-карточку встречи.
8. Транскрипт и сгенерированные артефакты добавляются в RAG.

## Карточка Встречи

Каждая обработанная встреча должна содержать:

- ссылку на исходный медиафайл;
- транскрипт;
- memo;
- протокол;
- решения;
- задачи;
- риски;
- открытые вопросы;
- metadata классификации;
- ссылки на связанные проектные документы.

Формальный контракт карточки зафиксирован в `configs/schemas/meeting.schema.json`, а человекочитаемый шаблон - в `docs/templates/MEETING_CARD.md`.

Первая итерация `FTT-MA-09` описывает структуру данных и папок. Watcher, live-транскрибация, diarization и DOCX-экспорт относятся к следующим этапам и не являются частью этого контракта.

## Offline-Транскрибация MVP

### 1. Ingest Встречи

Новая запись сначала превращается в каноническую карточку встречи:

```powershell
.\.venv\Scripts\python.exe scripts\20_ingest_meeting.py `
  --file "$env:USERPROFILE\Downloads\meeting.mp4" `
  --title "Встреча по АСУ"
```

Скрипт создает:

```text
meetings/YYYY-MM-DD__slug/
  meeting.json
  source/<original_file>
  transcript/
  artifacts/
  exports/
  _partials/
```

Правила:

- `meeting_id` строится как `YYYY-MM-DD__slug`, не UUID;
- исходное медиа копируется в `source/`;
- `meeting.json` валидируется по `configs/schemas/meeting.schema.json`;
- исходное медиа добавляется в `rag.no_index_artifacts`;
- `processing_status = new`.

### 2. Audio Extraction

Перед ASR можно нормализовать аудио:

```powershell
.\.venv\Scripts\python.exe scripts\21_extract_audio.py `
  --meeting-dir meetings\YYYY-MM-DD__slug
```

Выход:

```text
source/audio_16k_mono.wav
```

Формат:

```text
wav
mono
16000 Hz
```

Успешный audio extraction не вводит новый статус схемы и оставляет `processing_status = new`, чтобы следующий ASR-шаг мог стартовать без миграции `meeting.schema.json`. Нормализованный WAV добавляется в `source.media_files` и `rag.no_index_artifacts`.

### 3. ASR / Transcription

Основной обработчик одной встречи:

```powershell
.\.venv\Scripts\python.exe scripts\22_transcribe_meeting.py `
  --meeting-dir meetings\2026-05-08__test-meeting `
  --engine faster-whisper
```

Проверка без транскрибации:

```powershell
.\.venv\Scripts\python.exe scripts\22_transcribe_meeting.py `
  --meeting-dir meetings\2026-05-08__test-meeting `
  --engine faster-whisper `
  --dry-run
```

Поддерживаемые режимы:

```powershell
.\.venv\Scripts\python.exe scripts\22_transcribe_meeting.py `
  --meeting-dir meetings\YYYY-MM-DD__slug `
  --engine faster-whisper `
  --model large-v3-turbo `
  --language ru `
  --compute-type int8

.\.venv\Scripts\python.exe scripts\22_transcribe_meeting.py `
  --meeting-dir meetings\YYYY-MM-DD__slug `
  --engine gigaam `
  --model v3_e2e_rnnt `
  --language ru

.\.venv\Scripts\python.exe scripts\22_transcribe_meeting.py `
  --meeting-dir meetings\YYYY-MM-DD__slug `
  --engine from-segments `
  --segments-path "$env:USERPROFILE\Downloads\gigaam_output\segments_gigaam.jsonl"
```

Скрипт работает только с одной готовой папкой встречи. Он не делает watcher, live-режим, diarization, memo/protocol и RAG-индексацию.

Что делает скрипт:

- валидирует `meeting.json` по `configs/schemas/meeting.schema.json`;
- использует `source/audio_16k_mono.wav`, если он есть, иначе первый доступный media file;
- поддерживает `faster-whisper`, `gigaam` и импорт готового JSONL через `from-segments`;
- для `faster-whisper` берет defaults из `config.yaml/transcription`:
  - `model`;
  - `language`;
  - `compute_type`;
  - `device`;
  - `beam_size`;
  - `vad_filter`;
- сохраняет `avg_logprob` и `no_speech_prob`, если backend возвращает эти поля;
- сохраняет backend metrics в `transcript/transcription_report.json`;
- переводит статус `new -> transcribing -> transcribed`;
- пишет `transcript/segments.jsonl`, `transcript/transcript.md`, `transcript/transcript.txt`, `transcript/transcript.json`, `transcript/transcript.srt`, `transcript/transcript.vtt`;
- пишет `transcript/transcription_report.json`;
- без `--force` не перезаписывает готовый transcript;
- при ошибке переводит встречу в `failed` и записывает причину в `meeting.json.last_error`.

Рекомендуемый offline-профиль для качественной транскрибации встреч: `faster-whisper large-v3-turbo`, `language=ru`, `compute_type=int8`. Модель `small` использовать только для быстрых черновых smoke/live-проверок, где качество transcript не является критичным.

`scripts/06_transcribe_meeting.py` остается legacy compatibility entrypoint и перенаправляет старый CLI на `scripts/22_transcribe_meeting.py --engine faster-whisper`.

### 4. Live Draft Transcription

Live-транскрибация отделена от offline ASR. Ее задача - черновой transcript во время разговора, а не финальный transcript для протокола.

Optional dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-live.txt
```

Vosk-модель хранится локально в ignored `models/`, например:

```text
models/vosk/vosk-model-small-ru-0.22/
```

Проверка без запуска ASR:

```powershell
.\.venv\Scripts\python.exe scripts\33_live_transcribe_meeting.py `
  --meeting-dir meetings\YYYY-MM-DD__slug `
  --engine vosk `
  --model-path models\vosk\vosk-model-small-ru-0.22 `
  --source MIC `
  --dry-run
```

Inventory и hardware/backend preflight без открытия audio stream:

```powershell
.\.venv\Scripts\python.exe scripts\33_live_transcribe_meeting.py `
  --list-audio-sources

.\.venv\Scripts\python.exe scripts\33_live_transcribe_meeting.py `
  --preflight-source `
  --source MIC

.\.venv\Scripts\python.exe scripts\33_live_transcribe_meeting.py `
  --preflight-source `
  --source SYS
```

`--preflight-source` возвращает JSON и exit code `0`, только если источник
готов к запуску текущим backend; blocked source возвращает exit code `2`.
Поля `device_available` и `capture_supported` разделены: наличие Windows WASAPI
output candidate ещё не означает, что SYS loopback capture реализован.

Smoke по готовому `source/audio_16k_mono.wav`:

```powershell
.\.venv\Scripts\python.exe scripts\33_live_transcribe_meeting.py `
  --meeting-dir meetings\YYYY-MM-DD__slug `
  --engine vosk `
  --model-path models\vosk\vosk-model-small-ru-0.22 `
  --input-wav meetings\YYYY-MM-DD__slug\source\audio_16k_mono.wav `
  --source MIX `
  --vad silero `
  --duration-sec 30 `
  --force
```

Выходы:

```text
transcript/live/live_segments.<SOURCE>.jsonl
transcript/live/live_partials.<SOURCE>.jsonl
transcript/live/live_transcript.<SOURCE>.txt
transcript/live/live_subtitles.<SOURCE>.srt
transcript/live/live_subtitles.<SOURCE>.vtt
transcript/live/live_report.<SOURCE>.json
```

Правила:

- `<SOURCE>` - `MIC`, `SYS` или `MIX`;
- source-scoped filenames позволяют хранить MIC и SYS в одной карточке без перетирания;
- `live_segments.<SOURCE>.jsonl` - черновой finalized live transcript;
- `live_partials.<SOURCE>.jsonl` - промежуточные hypotheses, не индексировать;
- live draft artifacts автоматически добавляются в `rag.no_index_artifacts`;
- canonical offline transcript остается в `transcript/segments.jsonl`;
- для финального протокола после live-сессии нужно сделать offline ASR/import через `scripts/22_transcribe_meeting.py`.
- Ctrl+C во время live-записи считается штатным завершением: backend финализирует накопленные segments/partials и пишет артефакты.
- После live draft статус остается `processing`, а не `transcribed`; это не блокирует финальный offline ASR.

VAD modes:

```text
--vad none      baseline без VAD
--vad silero    optional Silero VAD для --input-wav smoke/preprocessing
```

Параметры Silero:

```powershell
--vad-threshold 0.5 `
--vad-min-speech-ms 250 `
--vad-min-silence-ms 100 `
--vad-speech-pad-ms 100
```

Ограничения текущего шага:

- `--vad silero` пока поддержан только вместе с `--input-wav`. Streaming VAD для микрофона и system-loopback нужно реализовывать отдельно, чтобы не сломать таймкоды.
- В `--vad silero` компрессии таймкодов нет: пропущенные non-speech blocks учитываются в реальном времени файла. Но finalized segment может получать хвостовой fallback span блока, на котором Vosk завершил фразу. Для smoke сравнивать нужно попадание segment в speech window, а не равенство span с `--vad none`.
- System-loopback capture, MIC+SYS mixing и ресэмплинг 44.1/48 кГц stereo -> 16 кГц mono еще не реализованы в live CLI. `SYS`/`MIX` без `--input-wav` fail closed и не маскируются под MIC.
- Микрофонный runtime пишет в `live_report.<SOURCE>.json` счетчики `input_status_events` и `queue_timeouts`; ненулевые значения нужно смотреть при диагностике overflow/dropout.

### 5. Optional Speaker Diarization

Диаризация отделяет говорящих, но не идентифицирует реальные имена людей. Базовый контракт использует анонимные метки:

```text
SPEAKER_00
SPEAKER_01
SPEAKER_UNKNOWN
```

Основной backend - `sherpa-onnx`. Он выбран как CPU-first путь для Windows без HuggingFace-токена и без PyTorch-конфликтов с GigaAM/faster-whisper. Зависимости ставятся отдельно:

```powershell
py -3.12 -m venv .venv-diarization
.\.venv-diarization\Scripts\python.exe -m pip install -c constraints-py312.txt `
  -r requirements-diarization.txt
```

ONNX-модели нужно скачать локально в ignored папку:

```text
models/diarization/
  sherpa-onnx-pyannote-segmentation-3-0/model.onnx
  wespeaker_en_voxceleb_resnet34_LM.onnx
```

Проверка без обработки:

```powershell
.\.venv-diarization\Scripts\python.exe scripts\23_diarize_meeting.py `
  --meeting-dir meetings\YYYY-MM-DD__slug `
  --dry-run
```

Запуск:

```powershell
.\.venv-diarization\Scripts\python.exe scripts\23_diarize_meeting.py `
  --meeting-dir meetings\YYYY-MM-DD__slug `
  --num-speakers 2
```

Если число участников неизвестно, `--num-speakers` не передается и используется auto-clustering. Для известных встреч явное число спикеров повышает качество.

Выход:

```text
transcript/diarization.jsonl
transcript/diarization_report.json
```

`diarization.jsonl` содержит интервалы:

```json
{"speaker":"SPEAKER_00","start":12.1,"end":20.8,"confidence":null,"backend":"sherpa-onnx/pyannote-seg-3.0+wespeaker-resnet34"}
```

`diarization_report.json` фиксирует backend, модели, параметры clustering, длительность аудио, время обработки и RTF.

Контейнерный запуск:

```powershell
docker compose --profile diarization build diarization

$env:MEETINGAGENT_RECORDINGS_DIR = "$env:USERPROFILE\Desktop\ProjectRecordings"

docker compose --profile diarization run --rm diarization `
  python scripts/23_diarize_meeting.py `
  --meeting-dir meetings\YYYY-MM-DD__slug `
  --force
```

Если встреча длинная, сначала убедиться, что `source/audio_16k_mono.wav` уже создан. Для качества нужно проверить результат глазами: `sherpa-onnx` разделяет говорящих на `SPEAKER_XX`, но не определяет реальные имена.

### 6. Speaker Transcript

После ASR можно создать speaker transcript. Если `transcript/diarization.jsonl` отсутствует, все реплики получают `SPEAKER_UNKNOWN`. Если файл есть, speaker выбирается по maximum-overlap с порогом `--min-overlap-ratio`:

```powershell
.\.venv\Scripts\python.exe scripts\24_merge_transcript_speakers.py `
  --meeting-dir meetings\YYYY-MM-DD__slug
```

Выход:

```text
transcript/speaker_transcript.jsonl
transcript/speaker_transcript.txt
```

Каждая реплика содержит:

```text
utterance_id
segment_index
speaker = SPEAKER_UNKNOWN
speaker_name = SPEAKER_UNKNOWN
source = MIX
start
end
text
speaker_overlap_seconds
speaker_overlap_ratio
```

Правило merge:

- для каждого ASR segment выбирается speaker interval с максимальным временным пересечением;
- если покрытие меньше `0.3` длительности ASR segment, используется `SPEAKER_UNKNOWN`;
- реальная идентификация людей не выполняется; ручной speaker mapping остается отдельным будущим слоем.

### 6. Meeting-Aware Chunking

Для RAG и LLM analysis transcript режется на чанки с учетом времени и реплик:

```powershell
.\.venv\Scripts\python.exe scripts\26_chunk_meeting.py `
  --meeting-dir meetings\YYYY-MM-DD__slug
```

Выход:

```text
transcript/chunks.jsonl
```

Chunk содержит:

```text
chunk_id
meeting_id
source_type = meeting_chunk
start
end
speakers
sources
text
utterance_ids
```

По умолчанию chunk ограничен 180 секундами и 6000 символами. Скрипт не разрывает отдельную реплику; если следующая реплика превышает лимит, открывается новый chunk.

### 7. Semantic Enrichment MVP

Первый enrichment-слой работает детерминированно, без LLM:

```powershell
.\.venv\Scripts\python.exe scripts\27_enrich_meeting_chunks.py `
  --meeting-dir meetings\YYYY-MM-DD__slug
```

Выход:

```text
artifacts/enriched_chunks.jsonl
```

Скрипт добавляет:

```text
topic
semantic_type
entities
decisions
action_items
risks
open_questions
importance_score
quality_flags
needs_review = true
```

Это MVP-слой для indexing/search и первичного отбора. Он не заменяет production LLM analysis и помечает значимые кандидаты как требующие проверки.

### 8. Meeting Index Export

Для попадания meeting chunks в общий RAG-контур используется экспорт в совместимый JSONL:

```powershell
.\.venv\Scripts\python.exe scripts\28_index_meeting_chunks.py `
  --meeting-dir meetings\YYYY-MM-DD__slug `
  --output data\meeting_chunks.jsonl
```

Экспортированные rows имеют:

```text
source_type = meeting_chunk
document_type = Протокол
meeting_id
meeting_title
timestamp_start
timestamp_end
speaker_names
topic
semantic_type
text
```

`meeting_chunk` добавлен в default allowed source types для `scripts/asu_june_bot_build_index_v2.py` и retrieval source policy. Для сборки отдельного индекса по встречам можно передать `data/meeting_chunks.jsonl` как `--chunks-path` в index builder.

### 9. Smoke Meeting Search

Быстрый поиск по экспортированным meeting chunks работает без Ollama и без основного индекса:

```powershell
.\.venv\Scripts\python.exe scripts\31_meeting_search.py `
  "какие решения приняли" `
  --chunks-path data\meeting_chunks.jsonl
```

Фильтр по одной карточке встречи:

```powershell
.\.venv\Scripts\python.exe scripts\31_meeting_search.py `
  "задачи Сергей" `
  --chunks-path data\meeting_chunks.jsonl `
  --meeting-id YYYY-MM-DD__slug
```

JSON-вывод для интеграции с ботом или UI:

```powershell
.\.venv\Scripts\python.exe scripts\31_meeting_search.py `
  "какие риски" `
  --chunks-path data\meeting_chunks.jsonl `
  --json
```

Отдельный smoke numpy index по встречам собирается той же сборкой v2, но с отдельными путями:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_build_index_v2.py `
  --chunks-path data\meeting_chunks.jsonl `
  --cache-path data\meeting_embeddings_cache.jsonl `
  --index-dir data\meeting_numpy_index `
  --report-path data\meeting_index_report.json `
  --include-source-type meeting_chunk `
  --limit 20
```

Если embeddings уже есть и нужно только пересобрать numpy-файлы:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_build_index_v2.py `
  --chunks-path data\meeting_chunks.jsonl `
  --cache-path data\meeting_embeddings_cache.jsonl `
  --index-dir data\meeting_numpy_index `
  --report-path data\meeting_index_report.json `
  --include-source-type meeting_chunk `
  --index-only
```

### 9.1. Восстановление Meeting Q&A Embedding Cache

Meeting-scoped semantic Q&A лениво пишет chunk embeddings в
`data/meeting_embeddings_cache.jsonl`. Запись защищена общим thread/process
lock и публикуется атомарно. Конкурентные первые запросы не создают повторные
rows и не считают один chunk повторно; повреждённая или оборванная JSONL-строка
пропускается, а при следующей записи cache автоматически очищается.

Проверить, сколько строк можно восстановить, ничего не меняя:

```powershell
.\.venv\Scripts\python.exe scripts\49_rebuild_meeting_vector_cache.py `
  --cache-path data\meeting_embeddings_cache.jsonl `
  --dry-run
```

Удалить malformed/invalid/duplicate rows и атомарно пересобрать cache:

```powershell
.\.venv\Scripts\python.exe scripts\49_rebuild_meeting_vector_cache.py `
  --cache-path data\meeting_embeddings_cache.jsonl
```

Команда не вызывает Ollama и не меняет `embedding_model`. Valid rows всех
моделей сохраняются. Если cache или lock недоступен во время пользовательского
Q&A, API не падает и использует lexical fallback.

### 10. LLM Map-Reduce Analysis

Структурированные артефакты встречи создаются после enrichment:

```powershell
.\.venv\Scripts\python.exe scripts\29_analyze_meeting.py `
  --meeting-dir meetings\YYYY-MM-DD__slug `
  --mode ollama-map-reduce `
  --model qwen3.5:4b `
  --force
```

Выход:

```text
artifacts/summary.md
artifacts/protocol.md
artifacts/decisions.json
artifacts/tasks.json
artifacts/risks.json
artifacts/open_questions.json
artifacts/_partials/llm_map_reduce/
```

Правила:

- MAP работает по `artifacts/enriched_chunks.jsonl`;
- каждый финальный пункт получает `source_refs` с `path`, `start`, `end`, `quote`;
- JSON валидируется по `configs/schemas/meeting.*.schema.json`;
- если отдельный MAP/REDUCE ответ модели не парсится или не успевает по timeout, скрипт сохраняет raw output и использует безопасный extractive fallback для этой части;
- для строгой отладки без fallback есть флаг `--strict-llm`;
- повторный запуск с `--force` перезаписывает итоговые артефакты, но переиспользует уже готовые partial JSON; для полного пересчета partials добавить `--recompute-partials`.

### 11. Structured Artifact Indexing

После `29_analyze_meeting.py` structured JSON-артефакты можно экспортировать в общий meeting index как отдельные source types:

```powershell
.\.venv\Scripts\python.exe scripts\32_index_meeting_artifacts.py `
  --meeting-dir meetings\YYYY-MM-DD__slug `
  --output data\meeting_chunks.jsonl
```

Экспортируемые типы:

```text
artifacts/decisions.json -> meeting_decision
artifacts/tasks.json -> meeting_action_item
artifacts/risks.json -> meeting_risk
artifacts/open_questions.json -> meeting_open_question
```

Каждая row содержит:

```text
meeting_id
meeting_title
artifact_type
artifact_id
source_type
timestamp_start
timestamp_end
source_refs
text
```

`31_meeting_search.py` читает эти source types вместе с `meeting_chunk` и повышает релевантность structured rows для запросов про решения, задачи, риски и открытые вопросы.

После экспорта нужно пересобрать smoke numpy index:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_build_index_v2.py `
  --chunks-path data\meeting_chunks.jsonl `
  --cache-path data\meeting_embeddings_cache.jsonl `
  --index-dir data\meeting_numpy_index `
  --report-path data\meeting_index_report.json
```

## Итоги Встречи

После статуса `transcribed` следующий слой pipeline создает человекочитаемые и машинные артефакты встречи.

Архитектура production-пути описана в `docs/architecture/MEETING_ARTIFACTS_PIPELINE.md`.

Целевой подход:

1. `MAP`: transcript делится на окна по 6 минут с overlap 30 секунд.
2. `REDUCE`: частичные JSON-артефакты объединяются, дедуплицируются и нормализуются.
3. `RENDER`: `memo.md` и `protocol.md` строятся из финальных JSON-артефактов, а не из сырого transcript.

Prompt-шаблоны первого слоя:

- `configs/prompts/meeting_memo.md` - краткое memo встречи;
- `configs/prompts/meeting_protocol.md` - формальный протокол;
- `configs/prompts/meeting_artifacts_json.md` - структурированное извлечение решений, задач, рисков и открытых вопросов.

Prompt-шаблоны map-reduce-render:

- `configs/prompts/meeting_map_extract.md` - извлечение из одного окна transcript;
- `configs/prompts/meeting_reduce_artifacts.md` - объединение partial artifacts;
- `configs/prompts/meeting_render_documents.md` - будущий LLM-слой для коротких текстовых разделов memo/protocol.

JSON-схемы структурированных артефактов:

- `configs/schemas/meeting.decisions.schema.json` -> `artifacts/decisions.json`;
- `configs/schemas/meeting.tasks.schema.json` -> `artifacts/tasks.json`;
- `configs/schemas/meeting.risks.schema.json` -> `artifacts/risks.json`;
- `configs/schemas/meeting.open_questions.schema.json` -> `artifacts/open_questions.json`.

Правило качества: каждый структурированный пункт должен иметь `source_refs` со ссылкой на transcript segment, RAG-источник или ручную заметку. Если модель не уверена в пункте, он остается в JSON, но получает `needs_review = true`.

Минимальный генератор артефактов:

```powershell
.\.venv\Scripts\python.exe scripts\07_generate_meeting_artifacts.py `
  --meeting-dir meetings\2026-05-08__test-meeting
```

По умолчанию используется быстрый `extractive`-режим: он ищет решения, задачи, риски и вопросы по transcript segments и всегда помечает результат как требующий ручной проверки. Это нужно, чтобы pipeline `transcribed -> summarized` работал предсказуемо даже без долгого LLM-вызова.

Важно: `extractive`-режим является скаффолдом контракта, а не продуктовым качеством FTT-MA-12. Его результаты нельзя считать готовым memo/protocol без ручной проверки.

Экспериментальный LLM-режим:

```powershell
.\.venv\Scripts\python.exe scripts\07_generate_meeting_artifacts.py `
  --meeting-dir meetings\2026-05-08__test-meeting `
  --mode ollama `
  --model qwen3.5:4b `
  --max-transcript-chars 9000
```

На текущем CPU-профиле длинные transcript могут быть медленными даже с единой локальной моделью `qwen3.5:4b`. Поэтому `ollama`-режим для больших встреч остается измеряемым runtime-путем, а не обязательным быстрым сценарием.

Map-reduce dry-run:

```powershell
.\.venv\Scripts\python.exe scripts\07_generate_meeting_artifacts.py `
  --meeting-dir meetings\2026-05-08__test-meeting `
  --mode ollama-map-reduce `
  --force `
  --dry-run
```

Перед полным запуском `ollama-map-reduce` нужно прогнать одно окно на выбранной модели и оценить время, валидность JSON и качество классификации.

## Устойчивость API Job Runner

Запуски из `/MeetingAgent` и Workspace сохраняют runtime state в ignored файле:

```text
logs/jobs_state.json
```

Путь можно изменить в локальном config:

```yaml
paths:
  jobs_state: logs/jobs_state.json
```

Правила восстановления:

- snapshot пишется через temp file + `os.replace` под межпроцессным lock;
- active reservation блокирует второй stage/pipeline даже для другого runner
  instance;
- после рестарта API живой child с тем же PID и process start identity получает
  `status=orphaned` и остаётся доступен для Cancel;
- запись с исчезнувшим или неидентифицируемым child становится `failed`, пишет
  нормализованный `last_error` и переводит stage в `ready_for_retry`;
- aggregate pipeline не продолжает потерянную Python coroutine автоматически:
  после terminal recovery используйте Resume pipeline;
- Cancel идемпотентен; process tree завершается целиком (`taskkill /T /F` на
  Windows, process group на Linux/Unix);
- snapshot больше 4 МиБ или повреждённый JSON останавливает API fail-closed.

Recovery виден в `GET /meetings/{id}/pipeline/readiness` как `job_recovery` и
в Pipeline-панели Workspace. Для production используйте один API worker:
durable reservation безопасна между процессами, но status routing не является
распределённой очередью задач.

`logs/jobs_state.json` и `.lock` — локальные runtime-файлы. Их нельзя добавлять
в Git или переносить между машинами как часть meeting card.

## Оконный Offline-Pipeline

Для сокращения общего времени обработки добавлен отдельный конвейерный offline-режим:

```powershell
.\.venv\Scripts\python.exe scripts\08_process_meeting_pipeline.py `
  --meeting-dir meetings\2026-05-08__test-meeting `
  --asr-model small `
  --llm-model qwen3.5:4b `
  --window-seconds 120 `
  --window-overlap-seconds 15 `
  --max-asr-workers 1 `
  --max-llm-workers 1
```

Проверка без записи файлов:

```powershell
.\.venv\Scripts\python.exe scripts\08_process_meeting_pipeline.py `
  --meeting-dir meetings\2026-05-08__test-meeting `
  --dry-run
```

Что делает `scripts/08_process_meeting_pipeline.py`:

- режет готовое аудио или видео на окна `transcript/chunks/Wxx.audio.wav`;
- пишет сегменты каждого окна в `transcript/chunks/Wxx.segments.jsonl`;
- запускает MAP-этап сразу после готовности окна;
- сохраняет partial JSON в `artifacts/_partials/window_Wxx.json`;
- после всех валидных partial запускает REDUCE и RENDER;
- пишет `artifacts/pipeline_report.md` с параметрами, временем этапов и ошибками;
- нормализует `source_refs` по реальному `transcript/segments.jsonl`, чтобы финальные решения, риски и задачи ссылались на существующие segment index и абсолютные таймкоды.

Если partial уже существует и `--force` не указан, окно не пересчитывается. Это позволяет продолжать обработку после падения REDUCE/RENDER без повторного ASR и MAP.

Текущий статус: 2-window smoke на тестовой встрече прошел. Полный прогон всей встречи и обработка новых записей остаются следующими задачами.

## Правила Статусов И Артефактов

JSON schema проверяет форму карточки, но не должна превращаться в сложный движок процесса. Проверки переходов между статусами выполняет pipeline:

- `new`: карточка создана, артефакты могут отсутствовать;
- `processing`: оконный offline-pipeline выполняет ASR, MAP, REDUCE или RENDER;
- `transcribing`: исходное медиа найдено, транскрибация идет;
- `transcribed`: должны существовать transcript и segments;
- `summarized`: должны существовать memo, protocol, decisions, tasks, risks и open_questions;
- `classified`: должен существовать classification report и заполненный блок `classification`;
- `indexed`: должны существовать все файлы из `rag.indexed_artifacts`;
- `failed`: pipeline должен сохранить причину ошибки в логах и не затирать уже созданные артефакты.

Если в исходниках встречи есть `screen_recording`, pipeline должен предложить или выставить `retention.policy = protected`. Это бизнес-правило уровня обработки, а не структурное ограничение JSON schema.

## Человекочитаемая Карточка Как Представление

Markdown-карточка и таблицы решений, задач, рисков и открытых вопросов являются представлением JSON-артефактов из `artifacts/`.

Правило: машинные JSON-файлы остаются источником истины. Если пользователь правит итог встречи вручную, сначала обновляется соответствующий JSON-артефакт, затем из него обновляется Markdown-представление. Это нужно, чтобы `decisions.json`, `tasks.json`, `risks.json` и текстовая карточка не расходились.

## Будущие Улучшения

- профили голосов;
- ручной speaker mapping на реальные имена;
- optional pyannote backend как high-quality режим после сравнения с sherpa-onnx;
- синхронизация транскрипта с проигрывателем;
- UI для ручной корректировки;
- экспорт в DOCX/Markdown.
