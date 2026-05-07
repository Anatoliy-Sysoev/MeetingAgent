# Шаблон Карточки Встречи

Карточка встречи - это человекочитаемый документ плюс машинный `meeting.json`. Формат должен быть одинаковым для offline-записи и live-сессии.

## Метаданные

- Название:
- Дата:
- Исходный файл:
- Этап проекта:
- Связанные ФТТ:
- Связанная задача:
- Связанный документ:

## Краткое Содержание

## Протокол

## Решения

## Задачи

## Риски

## Открытые Вопросы

## Ссылки На Источники

## Минимальная Структура Папки

```text
meetings/
  YYYY-MM-DD/
    meeting_slug/
      source/
      transcript/
      artifacts/
      exports/
      meeting.json
```

## Минимальный Контракт `meeting.json`

```json
{
  "schema_version": 1,
  "meeting_id": "2026-05-07__project-sync",
  "title": "Название встречи",
  "created_at": "2026-05-07T10:00:00+03:00",
  "source": {
    "mode": "file или live",
    "files": [],
    "audio_tracks": ["MIC", "SYS"],
    "derived_tracks": ["MIX"]
  },
  "status": {
    "transcription": "pending | processing | completed | failed",
    "artifacts": "pending | processing | completed | failed",
    "classification": "pending | needs_review | completed | failed",
    "rag_update": "pending | completed | skipped | failed"
  },
  "classification": {
    "project_stage": "PRJ-00",
    "document_types": [],
    "ftt_refs": [],
    "confidence": 0.0,
    "reason": "",
    "alternatives": []
  },
  "artifacts": {
    "transcript_jsonl": "transcript/segments.jsonl",
    "transcript_text": "transcript/transcript.md",
    "memo": "artifacts/memo.md",
    "protocol": "artifacts/protocol.md",
    "decisions": "artifacts/decisions.json",
    "tasks": "artifacts/tasks.json",
    "risks": "artifacts/risks.json"
  },
  "rag": {
    "index_policy": "structured_artifacts_and_final_transcript",
    "indexed_files": [],
    "no_index_files": []
  }
}
```

## Правила Индексации

В RAG попадают:

- memo;
- протокол;
- решения;
- задачи;
- риски;
- открытые вопросы;
- финальный transcript сегментами.

В RAG не попадают:

- исходное видео/аудио;
- временные live-файлы;
- сырой transcript, если он явно помечен как `no_index`.
