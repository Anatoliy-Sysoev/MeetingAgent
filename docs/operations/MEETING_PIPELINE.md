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

Минимальный обработчик одной встречи:

```powershell
.\.venv\Scripts\python.exe scripts\06_transcribe_meeting.py `
  --meeting-dir meetings\2026-05-08__test-meeting
```

Проверка без транскрибации:

```powershell
.\.venv\Scripts\python.exe scripts\06_transcribe_meeting.py `
  --meeting-dir meetings\2026-05-08__test-meeting `
  --dry-run
```

Скрипт работает только с одной готовой папкой встречи. Он не делает watcher, live-режим, diarization, memo/protocol и RAG-индексацию.

Что делает скрипт:

- валидирует `meeting.json` по `configs/schemas/meeting.schema.json`;
- проверяет `ffmpeg` и первый файл из `source.media_files`;
- использует `faster-whisper` с настройками `small`, `int8`, `ru` по умолчанию;
- передает проектные термины из `docs/glossary.md` как `initial_prompt`;
- переводит статус `new -> transcribing -> transcribed`;
- пишет `transcript/segments.jsonl` и `transcript/transcript.md`;
- при ошибке переводит встречу в `failed` и записывает причину в `meeting.json.last_error`.

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
  --model qwen3:4b `
  --max-transcript-chars 9000
```

На текущем CPU-профиле Qwen3 может быть слишком медленной для длинных transcript. Поэтому `ollama`-режим пока считается экспериментальным, а не обязательным путем MVP.

Map-reduce dry-run:

```powershell
.\.venv\Scripts\python.exe scripts\07_generate_meeting_artifacts.py `
  --meeting-dir meetings\2026-05-08__test-meeting `
  --mode ollama-map-reduce `
  --force `
  --dry-run
```

Перед полным запуском `ollama-map-reduce` нужно прогнать одно окно на выбранной модели и оценить время, валидность JSON и качество классификации.

## Правила Статусов И Артефактов

JSON schema проверяет форму карточки, но не должна превращаться в сложный движок процесса. Проверки переходов между статусами выполняет pipeline:

- `new`: карточка создана, артефакты могут отсутствовать;
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

- diarization спикеров;
- профили голосов;
- синхронизация транскрипта с проигрывателем;
- UI для ручной корректировки;
- экспорт в DOCX/Markdown.
