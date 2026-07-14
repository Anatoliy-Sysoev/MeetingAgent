# Архитектура MeetingAgent

## Смысл Продукта

MeetingAgent превращает записи встреч и проектные документы в локальную проектную память:

```text
Видео/аудио/документы
  -> transcript и структурированные артефакты
  -> RAG index
  -> поиск, ответы с источниками, протоколы, задачи и решения
```

Ценность продукта не в простой транскрибации, а в проверяемой трассировке:

```text
ответ или пункт протокола
  -> source_refs
  -> transcript segment / meeting chunk / проектный документ
  -> таймкод, спикер, файл, chunk_id
```

## Целевая Модель Встречи

```text
Видео/аудио
  -> audio extraction
  -> ASR
  -> optional diarization
  -> speaker transcript
  -> meeting-aware chunking
  -> semantic enrichment
  -> RAG indexing
  -> LLM analysis
  -> artifacts
```

Целевые артефакты:

```text
transcript
segments.jsonl
speaker_transcript.jsonl
chunks.jsonl
summary.md
protocol.md
decisions.json
tasks.json
risks.json
open_questions.json
pipeline_report.md
```

## Уже Принятые Контракты

MeetingAgent уже имеет контракт карточки встречи:

```text
configs/schemas/meeting.schema.json
docs/templates/MEETING_CARD.md
```

Канонический `meeting_id`:

```text
YYYY-MM-DD__short-title
```

Пример:

```text
2026-05-26__support-level-scheme
```

UUID для MVP не используется, потому что карточки встреч должны быть читаемы в проводнике и Git.

Каноническая папка карточки:

```text
meetings/<meeting_id>/
  meeting.json
  source/
  transcript/
  artifacts/
  exports/
  _partials/
```

`data/` используется для runtime-индексов, cache, eval и временных рабочих данных. Не нужно создавать второй постоянный формат `data/meetings/<meeting_id>/`, пока не появится отдельное storage-решение.

## Статусы MVP

Текущая схема поддерживает:

```text
new
processing
transcribing
transcribed
summarized
classified
indexed
failed
```

Для детальной диагностики шагов pipeline использовать:

```text
artifacts/pipeline_report.md
meeting.json.last_error
logs/
```

Расширенные статусы вроде `uploaded`, `audio_extracted`, `diarized`, `chunked`, `enriched`, `analyzed` полезны как внутренние stage labels, но не должны ломать текущий `meeting.schema.json` без отдельной миграции схемы.

## ASR

Основной путь:

```text
faster-whisper
```

Профили:

```text
large-v3-turbo/int8  качественный offline-профиль для готовых записей
small/int8           быстрый черновик и live MVP
```

GigaAM:

```text
локальный fallback/экспериментальный ASR-путь
scripts/run_gigaam_transcribe.ps1
docs/operations/GIGAAM_TRANSCRIPTION.md
```

GigaAM не заменяет основной ASR-контракт до сравнения качества на 2-3 русскоязычных встречах.

## Live ASR

Первый live MVP:

```text
Vosk
optional Silero VAD для WAV, MIC и Windows SYS
```

Назначение:

```text
черновой live transcript;
partial hypotheses;
таймкоды;
source labels MIC/SYS/MIX.
```

Live outputs пишутся отдельно:

```text
transcript/live/live_segments.<SOURCE>.jsonl
transcript/live/live_partials.<SOURCE>.jsonl
transcript/live/live_transcript.<SOURCE>.txt
transcript/live/live_report.<SOURCE>.json
source/live_audio.<SOURCE>.wav  # real MIC/SYS capture only
```

`<SOURCE>` равен `MIC`, `SYS` или `MIX`, поэтому несколько дорожек могут сосуществовать в одной карточке встречи.

В Workspace пользователь управляет MIC и SYS как одной записью: выбирает оба
устройства и нажимает одну кнопку запуска или остановки. API создаёт две
source-scoped сессии и объединяет их статус, предупреждения, partials и финальные
реплики в одном Live-разделе. Внутреннее разделение не убирается: независимые
WAV/segments/report нужны для provenance, диагностики и offline refinement. Если
SYS не стартует после MIC, групповой запуск останавливает уже созданную MIC-сессию
и возвращает контролируемую ошибку вместо скрытой однодорожечной записи.

Ограничение: live transcript не считается финальным источником истины для протокола. После встречи нужно запускать offline ASR через `scripts/22_transcribe_meeting.py` или импортировать готовые canonical segments. Поэтому live draft completion не ставит `processing_status=transcribed`; статус остается `processing`.

Для реального MIC/SYS полный canonical поток до VAD сохраняется как PCM16 mono
16 kHz WAV. Запись потоковая, ограничена по размеру и свободному месту,
публикуется атомарно, регистрируется в `source.media_files` и остаётся в
`rag.no_index_artifacts`. Это обязательный source input для последующего
offline refinement; текстовый live draft сам по себе входом ASR не является.

Offline refinement запускается явно и отдельно для `MIC` или `SYS`. Он
переиспользует canonical `scripts/22_transcribe_meeting.py` и штатный durable
JobRunner, а не вводит второй ASR-оркестратор. Состояния `draft`, `refining`,
`final`, `failed` доступны через API и Workspace. Canonical transcript
перезаписывается только offline ASR; source-scoped live artifacts сохраняются и
остаются no-index. Отчёт `transcript/live/refinement.<SOURCE>.json` содержит
только безопасные engine/model/timing/count metadata и дельты, без текста,
абсолютных путей и автоматической оценки качества.

T-one рассматривается как будущий экспериментальный backend для сравнительного прогона. Основной риск T-one - телефонная специализация модели; на широкополосных встречах качество нужно подтверждать отдельно.

Silero VAD является общим optional preprocessing-слоем для Vosk/T-one/future
backends. `--input-wav` заранее вычисляет speech windows. MIC и Windows SYS
используют stateful streaming filter по 512 frames; accepted blocks записываются
в `AcceptedAudioTimeline`, и word timestamps Vosk переводятся обратно в исходное
время capture. Поэтому отфильтрованная тишина не сжимает таймкоды. Общий
canonical consumer обеспечивает одинаковый timing contract после MIC capture и
после SYS `WASAPI -> SoXR -> mono 16 kHz`. Ctrl+C трактуется как graceful stop с
записью накопленных артефактов.

Windows SYS не вызывает native blocking read без предварительной проверки:
`get_read_available()` ограничивает размер каждого read, а monotonic scheduler
добавляет native-rate zero PCM для idle-интервалов. Так bounded capture и Ctrl+C
не зависят от появления output packets, а исходная шкала времени продолжается.
Known limitations: live endpointing может сохранить небольшой уже переданный в
Vosk хвост тишины; аппаратный `MIX` пока fail closed.

## Diarization

Текущий default:

```text
sherpa-onnx
```

Модели:

```text
sherpa-onnx-pyannote-segmentation-3-0/model.onnx
wespeaker_en_voxceleb_resnet34_LM.onnx
```

Почему так:

```text
CPU-first;
без HuggingFace token в runtime;
меньше риск конфликтов torch-зависимостей с GigaAM;
можно изолировать в optional Docker profile.
```

Optional fallback/high-quality направление:

```text
pyannote.audio 3.1+
```

Ограничение pyannote: может потребоваться HuggingFace token, license acceptance и отдельная проверка совместимости PyTorch-зависимостей.

MVP/product pipeline может работать без diarization:

```text
speaker = SPEAKER_UNKNOWN
```

Ручной speaker mapping допускается позже как отдельный слой:

```json
{
  "SPEAKER_01": {
    "name": "Анатолий",
    "role": "Системный аналитик"
  }
}
```

## Meeting-Aware Chunking

Нельзя резать transcript только по N символов.

Chunk должен учитывать:

```text
таймкоды
спикеров, если они есть
длину текста
смысловую завершенность
source_refs
```

MVP-ориентир:

```text
1-3 минуты
500-1500 tokens
не разрывать короткую реплику
```

Базовая схема chunk:

```json
{
  "chunk_id": "2026-05-26__support-level-scheme-chunk-0001",
  "meeting_id": "2026-05-26__support-level-scheme",
  "source_type": "meeting_chunk",
  "start": 120.0,
  "end": 240.0,
  "speakers": ["SPEAKER_UNKNOWN"],
  "text": "...",
  "utterance_ids": ["utt-000010"]
}
```

## Semantic Enrichment

Каждый meeting chunk должен получить смысловые metadata:

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
```

Semantic types:

```text
discussion
decision
action_item
risk
issue
open_question
requirement_change
status_update
offtopic
```

LLM-ошибка на одном chunk не должна ломать весь pipeline. Неудачный chunk получает `needs_review` или `quality_flags`, а pipeline продолжает работу.

## RAG Indexing

Новые source types для встреч:

```text
meeting_transcript
meeting_chunk
meeting_decision
meeting_action_item
meeting_risk
meeting_open_question
meeting_protocol
```

Metadata для meeting sources:

```json
{
  "source_type": "meeting_chunk",
  "meeting_id": "2026-05-26__synthetic-support-handoff",
  "meeting_title": "Передача поддержки проекта",
  "timestamp_start": "00:02:00",
  "timestamp_end": "00:03:00",
  "speaker_names": ["SPEAKER_UNKNOWN"],
  "topic": "Зоны ответственности команды",
  "semantic_type": "decision"
}
```

Meeting chunks должны проходить через существующий retrieval quality слой:

```text
hybrid retrieval
FTS5
rerank
bucket routing
source-quality gate
```

## Meeting Buckets

Нужно добавить retrieval buckets:

```text
meeting_decision
meeting_action_item
meeting_risk
meeting_open_question
meeting_requirement_change
meeting_summary
```

Примеры запросов:

```text
Какие решения приняли на встрече?
Какие задачи у Сергея?
Какие риски зафиксировали?
Что осталось открытым?
Что обсуждали про AD?
```

## Quality

Для meeting pipeline нужны:

```text
docs/quality/meeting_eval_questions.jsonl
docs/quality/meeting_regression_set.jsonl
```

Категории:

```text
meeting_summary
meeting_decisions
meeting_tasks
meeting_risks
meeting_open_questions
meeting_search
speaker_attribution
timestamp_accuracy
```

Минимальный quality gate:

```text
20 smoke questions
100 realistic questions после появления нескольких реальных встреч
regression set из подтвержденных ответов
```

## Storage Evolution

MVP:

```text
filesystem + json/jsonl
```

Позже, только при росте:

```text
PostgreSQL
Qdrant
object storage
```

Переход на БД не должен ломать файловый экспорт карточки встречи.
