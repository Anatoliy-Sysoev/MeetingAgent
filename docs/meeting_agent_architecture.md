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
small/int8      быстрый черновик и live MVP
large-v3-turbo  качественный offline-профиль
```

GigaAM:

```text
локальный fallback/экспериментальный ASR-путь
scripts/run_gigaam_transcribe.ps1
docs/operations/GIGAAM_TRANSCRIPTION.md
```

GigaAM не заменяет основной ASR-контракт до сравнения качества на 2-3 русскоязычных встречах.

## Diarization

Целевой инструмент:

```text
pyannote.audio 3.1+
```

Ограничение:

```text
может потребоваться HuggingFace token и принятие license
```

MVP может работать без diarization:

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
  "meeting_id": "2026-05-26__support-level-scheme",
  "meeting_title": "Схема уровня поддержки",
  "timestamp_start": "00:02:00",
  "timestamp_end": "00:03:00",
  "speaker_names": ["SPEAKER_UNKNOWN"],
  "topic": "Зоны ответственности поддержки",
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
