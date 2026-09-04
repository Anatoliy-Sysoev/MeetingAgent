# Шаблон Карточки Встречи

Карточка встречи - это папка с исходными материалами, машинным `meeting.json` и человекочитаемыми артефактами. Формат одинаковый для offline-записи и live-сессии: live отличается способом появления transcript, но не контрактом хранения.

Формальная JSON schema хранится в `configs/schemas/meeting.schema.json`. Этот markdown-шаблон нужен для чтения человеком и для будущих UI/API-экранов.

## Идентификатор

`meeting_id` совпадает с именем папки и строится как:

```text
YYYY-MM-DD__short-title
```

Пример:

```text
2026-05-07__project-sync
```

`short-title` пишется латиницей в slug-формате: маленькие буквы, цифры и дефисы.

## Структура Папки

```text
meetings/
  2026-05-07__project-sync/
    source/
      original.mp4
      mic.wav
      sys.wav
      mix.wav
    transcript/
      transcript.md
      segments.jsonl
    artifacts/
      memo.md
      protocol.md
      decisions.json
      tasks.json
      risks.json
      open_questions.json
      classification.json
    exports/
    meeting.json
```

Правила:

- `source/` хранит исходные и производные медиа, но не индексируется в RAG.
- `transcript/segments.jsonl` хранит сегменты с таймкодами и, когда возможно, `source`.
- `artifacts/` хранит очищенные проектные артефакты.
- `exports/` зарезервирован для будущих Markdown/DOCX/PDF-экспортов.
- `meeting.json` является машинной карточкой и источником статуса.
- `last_error` в `meeting.json` заполняется только при `processing_status = failed` и очищается при успешном повторном запуске.

## Markdown-Карточка

Markdown-карточка является человекочитаемым представлением данных из `meeting.json` и JSON-артефактов в `artifacts/`. Решения, задачи, риски и открытые вопросы не должны иметь две независимые версии: машинные JSON-файлы остаются источником истины, а таблицы в Markdown генерируются или обновляются из них.

```markdown
# Название Встречи

## Метаданные

| Поле | Значение |
|---|---|
| meeting_id | 2026-05-07__project-sync |
| Дата | 2026-05-07 |
| Время начала | 10:00+03:00 |
| Длительность | 60 минут |
| Источник | offline_record / live_session |
| Статус | new / transcribing / transcribed / summarized / classified / indexed / failed |
| Retention | default / protected |

## Участники

- Участник 1
- Участник 2

## Краткое Содержание

Короткий ответ: что обсуждали и чем встреча важна для проекта.

## Протокол

### Вопрос 1

- Обсуждение:
- Итог:
- Источники:

## Решения

| ID | Решение | Ответственный | Основание |
|---|---|---|---|
| DEC-001 |  |  |  |

## Задачи

| ID | Задача | Ответственный | Срок | Статус |
|---|---|---|---|---|
| TASK-001 |  |  |  | open |

## Риски

| ID | Риск | Влияние | Что делать |
|---|---|---|---|
| RISK-001 |  |  |  |

## Открытые Вопросы

- Вопрос:
- Кому адресован:
- Когда вернуться:

## Классификация

- Этап проекта: PRJ-XX
- Кандидаты ФТТ:
- Кандидаты документов:
- Уверенность:
- Требует ручной проверки: да/нет

## Связи

- Связанные документы:
- Связанные встречи:
- Связанные решения:

## RAG

Индексируются: memo, protocol, decisions, tasks, risks, open_questions, финальный transcript.

Не индексируются: исходные медиа, временные live-файлы, черновики до очистки.
```

## Минимальный `meeting.json` Для Статуса `new`

В новой встрече большинство артефактов еще отсутствует. Поэтому `artifacts`, `classification` и `links` могут быть пустыми объектами, а `rag.indexed_artifacts` - пустым списком.

```json
{
  "schema_version": 1,
  "meeting_id": "2026-05-07__project-sync",
  "title": "Проектная синхронизация",
  "date": "2026-05-07",
  "start_time": "10:00+03:00",
  "duration_minutes": 60,
  "participants": [
    "Участник 1",
    "Участник 2"
  ],
  "source": {
    "kind": "offline_record",
    "original_location": "watched_folder/project-sync.mp4",
    "media_files": [
      {
        "path": "source/original.mp4",
        "media_type": "video"
      }
    ],
    "audio_tracks": [
      "MIC",
      "SYS"
    ],
    "derived_tracks": [
      "MIX"
    ]
  },
  "processing_status": "new",
  "artifacts": {},
  "classification": {},
  "links": {},
  "retention": {
    "policy": "default"
  },
  "rag": {
    "index_policy": "structured_artifacts_and_final_transcript",
    "indexed_artifacts": [],
    "no_index_artifacts": [
      "source/original.mp4"
    ]
  },
  "created_at": "2026-05-07T10:00:00+03:00",
  "updated_at": "2026-05-07T10:00:00+03:00"
}
```

## Фрагмент `meeting.json` После Обработки

Когда встреча дошла до статуса `indexed`, обработчик должен заполнить ссылки на созданные файлы и явно перечислить артефакты, которые попали в RAG.

```json
{
  "processing_status": "indexed",
  "artifacts": {
    "transcript": "transcript/transcript.md",
    "segments": "transcript/segments.jsonl",
    "memo": "artifacts/memo.md",
    "protocol": "artifacts/protocol.md",
    "decisions": "artifacts/decisions.json",
    "tasks": "artifacts/tasks.json",
    "risks": "artifacts/risks.json",
    "open_questions": "artifacts/open_questions.json",
    "classification_report": "artifacts/classification.json"
  },
  "classification": {
    "project_stage": "PRJ-00",
    "ftt_candidates": [],
    "document_candidates": [],
    "task_candidates": [],
    "confidence": 0,
    "summary": "",
    "needs_review": true
  },
  "links": {
    "related_documents": [],
    "related_meetings": [],
    "related_decisions": []
  },
  "rag": {
    "index_policy": "structured_artifacts_and_final_transcript",
    "indexed_artifacts": [
      "transcript/transcript.md",
      "artifacts/memo.md",
      "artifacts/protocol.md",
      "artifacts/decisions.json",
      "artifacts/tasks.json",
      "artifacts/risks.json",
      "artifacts/open_questions.json"
    ],
    "no_index_artifacts": [
      "source/original.mp4"
    ]
  }
}
```

## Правила Готовности Карточки

Карточка считается пригодной для ручного чтения, если:

- папка названа по `meeting_id`;
- `meeting.json` проходит `configs/schemas/meeting.schema.json`;
- у встречи есть понятный статус обработки;
- пути в `artifacts` указывают на реальные файлы внутри папки встречи;
- retention явно указан как `default` или `protected`;
- RAG-политика явно перечисляет, что индексируется и что не индексируется.

## Поведение В Пограничных Случаях

- Встреча, которая длится через полночь, остается одной карточкой с исходной `date`, `start_time` и фактическим `duration_minutes`.
- Если в `source.media_files` есть `screen_recording`, приложение должно предложить или выставить `retention.policy = protected`. Это бизнес-правило pipeline, а не структурное ограничение JSON schema.
- При переходе между статусами pipeline должен проверять наличие файлов, соответствующих статусу. Например, `transcribed` требует transcript, `summarized` требует memo/protocol, `classified` требует classification report, `indexed` требует заполненного `rag.indexed_artifacts`.
- При ошибке обработки карточка не должна оставаться в `transcribing`: статус меняется на `failed`, а причина фиксируется в `last_error`.
