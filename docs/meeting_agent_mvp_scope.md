# MVP Scope MeetingAgent

## Цель MVP

Первая рабочая версия должна принимать готовую запись встречи и превращать ее в проверяемые артефакты:

```text
media file
  -> transcript
  -> chunks
  -> summary
  -> decisions/tasks/risks/open questions
  -> searchable meeting sources
```

MVP считается успешным, если пользователь может:

```text
загрузить mp4/mp3/wav/m4a;
получить transcript с таймкодами;
получить краткое summary;
получить решения, задачи, риски и открытые вопросы;
найти фрагменты встречи по вопросу;
увидеть source timestamp у каждого важного вывода.
```

## Что Входит В MVP

### 1. Ingestion

Скрипт:

```text
scripts/20_ingest_meeting.py
```

Команда:

```powershell
.\.venv\Scripts\python.exe scripts\20_ingest_meeting.py `
  --file "$env:USERPROFILE\Downloads\meeting.mp4" `
  --title "Встреча по АСУ"
```

Ожидаемый результат:

```text
meetings/<meeting_id>/meeting.json
meetings/<meeting_id>/source/<original_file>
processing_status = new
```

Важно: `meeting_id` должен быть slug `YYYY-MM-DD__short-title`, а не UUID.

### 2. Audio Extraction

Скрипт:

```text
scripts/21_extract_audio.py
```

Выход:

```text
meetings/<meeting_id>/source/audio_16k_mono.wav
```

Формат:

```text
wav
mono
16000 Hz
```

Acceptance:

```text
mp4/mp3/m4a/wav приводятся к 16k mono wav;
ошибка ffmpeg сохраняется в meeting.json.last_error или logs;
pipeline можно перезапустить без повторного копирования raw-файла.
```

### 3. ASR

Скрипт:

```text
scripts/22_transcribe_meeting.py
```

Можно переиспользовать текущую реализацию:

```text
scripts/06_transcribe_meeting.py
```

Выход:

```text
transcript/segments.jsonl
transcript/transcript.md
```

Желаемые дополнительные экспорты:

```text
transcript/transcript.txt
transcript/transcript.srt
transcript/transcript.vtt
transcript/transcript.json
```

Segment schema:

```json
{
  "segment_id": "seg-000001",
  "start": 12.4,
  "end": 18.9,
  "text": "Коллеги, давайте зафиксируем...",
  "language": "ru",
  "avg_logprob": -0.12,
  "no_speech_prob": 0.03
}
```

Acceptance:

```text
есть segments.jsonl;
каждый segment имеет start/end/text;
пустые segments отфильтрованы;
processing_status = transcribed.
```

### 4. Diarization Lite

Для MVP diarization необязательна.

Если pyannote не настроен:

```text
speaker = SPEAKER_UNKNOWN
```

Целевой будущий скрипт:

```text
scripts/23_diarize_meeting.py
```

MVP-совместимый merge:

```text
scripts/24_merge_transcript_speakers.py
```

Acceptance:

```text
speaker_transcript.jsonl создается даже без diarization;
каждый utterance имеет speaker/start/end/text;
без diarization speaker = SPEAKER_UNKNOWN.
```

### 5. Meeting-Aware Chunking

Скрипт:

```text
scripts/26_chunk_meeting.py
```

Выход:

```text
transcript/chunks.jsonl
```

Acceptance:

```text
каждый chunk имеет meeting_id/start/end/text/speakers;
нет пустых chunks;
chunk сохраняет utterance_ids или segment refs;
короткие реплики не режутся пополам.
```

### 6. Semantic Enrichment

Скрипт:

```text
scripts/27_enrich_meeting_chunks.py
```

Выход:

```text
artifacts/enriched_chunks.jsonl
```

Acceptance:

```text
каждый chunk имеет topic;
каждый chunk имеет semantic_type;
decisions/tasks/risks/open_questions проходят JSON validation;
ошибка LLM на одном chunk не ломает весь pipeline.
```

### 7. Structured Analysis

Скрипт:

```text
scripts/29_analyze_meeting.py
```

Можно развивать текущий:

```text
scripts/07_generate_meeting_artifacts.py
scripts/08_process_meeting_pipeline.py
```

Выход:

```text
artifacts/memo.md
artifacts/protocol.md
artifacts/decisions.json
artifacts/tasks.json
artifacts/risks.json
artifacts/open_questions.json
```

Acceptance:

```text
summary/protocol создаются;
каждый decision/task/risk/open_question имеет source_refs;
неуверенные пункты помечаются needs_review;
processing_status = summarized.
```

### 8. Meeting Indexing

Скрипт:

```text
scripts/28_index_meeting_chunks.py
```

Acceptance:

```text
meeting chunks попадают в существующий индекс;
поиск находит фрагменты по теме;
ответ содержит таймкоды;
source-quality gate работает для meeting chunks.
```

### 9. Meeting Search

Скрипт:

```text
scripts/31_meeting_search.py
```

Acceptance:

```text
поиск работает по одной встрече;
поиск работает по всем встречам;
можно фильтровать meeting_id;
ответ содержит sources, timestamps, speaker, meeting title, confidence.
```

## Что Не Входит В MVP

```text
автоматическое определение реальных имен спикеров;
обязательная pyannote diarization;
сложная агентная оркестрация;
DSPy;
graph retrieval;
автоматическое обновление проектной документации;
DOCX export как обязательный выход;
PostgreSQL/Qdrant/object storage;
multi-user режим;
cloud ASR/LLM.
```

## Ближайшие 10 Задач

```text
1. Зафиксировать architecture/scope docs.
2. Реализовать scripts/20_ingest_meeting.py.
3. Реализовать scripts/21_extract_audio.py.
4. Привести scripts/06_transcribe_meeting.py к контракту 22_transcribe_meeting или сделать thin wrapper.
5. Сделать diarization-lite merge с SPEAKER_UNKNOWN.
6. Реализовать scripts/26_chunk_meeting.py.
7. Реализовать scripts/27_enrich_meeting_chunks.py.
8. Реализовать scripts/28_index_meeting_chunks.py.
9. Развить scripts/07/08 до structured analysis или добавить scripts/29_analyze_meeting.py.
10. Добавить meeting search CLI и smoke eval.
```

## Критерий Готовности Первой Версии

На одной реальной записи встреча должна проходить путь:

```text
ingest
  -> audio extraction
  -> ASR
  -> speaker transcript with SPEAKER_UNKNOWN
  -> chunks
  -> artifacts
  -> meeting search
```

И иметь проверяемый результат:

```text
каждый важный вывод имеет timestamp/source_ref;
ошибки пишутся в отчет;
повторный запуск не пересчитывает успешные тяжелые шаги без --force;
runtime artifacts не попадают в Git.
```
