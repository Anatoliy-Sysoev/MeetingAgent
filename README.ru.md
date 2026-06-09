# MeetingAgent

[English](README.md) | [Русский](README.ru.md)

MeetingAgent — local-first OSS-инструмент для проектной памяти, обработки встреч, транскрибации, RAG-поиска и подготовки рабочих артефактов.

Проект помогает превращать проектные документы, записи встреч и транскрипты в проверяемые результаты: ответы с источниками, summary, memo, протоколы, решения, задачи, риски и открытые вопросы.

## Что Важно

- Приватные документы, транскрипты, индексы и runtime-артефакты остаются локально.
- В публичном репозитории хранятся только код, синтетические examples, шаблоны и обезличенная документация.
- `.env`, `config.yaml`, `data/`, `logs/`, `vector_db/`, `watched_folder/`, runtime meeting cards и private eval reports не коммитятся.

## Основные Контуры

### MeetingAgent Core

Общий pipeline:

```text
documents / audio / video
  -> extraction / transcription
  -> chunking
  -> indexing
  -> source-grounded search/chat
  -> summaries, protocols, decisions, tasks, risks
```

### Project Knowledge Bot

`Project Knowledge Bot` — reference implementation локального project-only ассистента поверх приватного корпуса.

Он предоставляет:

- `POST /search` для retrieval/context;
- `POST /chat` для ответов с citations;
- локальный Web UI;
- Telegram adapter;
- guardrails для внепроектных, смешанных и unsafe-запросов;
- quality/eval workflows.

Документация:

```text
docs/project_knowledge_bot.md
```

Примечание: приватные корпуса, generated chunks, embeddings, indexes, transcripts и customer-specific runbooks не публикуются. Для локального запуска используется `.env` и ignored runtime paths.

### Legacy Pipeline

Скрипты `scripts/01_*` ... `scripts/09_chat.py` относятся к legacy MeetingAgent v1 RAG baseline. Они сохранены для совместимости и миграции. Новый runtime должен опираться на `src/asu_june_bot/`, `src/meeting_agent/transcription/` и задокументированные публичные workflows.

### Planned Package

`src/meeting_agent/` — планируемый общий Python-пакет MeetingAgent. Сейчас большинство подпакетов являются scaffold. Production-ready reference runtime находится в `src/asu_june_bot/`; реализованный общий слой транскрибации находится в `src/meeting_agent/transcription/`.

## Быстрый Старт

```powershell
git clone https://github.com/Anatoliy-Sysoev/MeetingAgent.git
cd MeetingAgent
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Для локальных Ollama workflows:

```powershell
ollama pull bge-m3
ollama pull qwen3.5:4b
```

## Запуск Project Knowledge Bot API

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_api.py --host 127.0.0.1 --port 8000
```

Проверка:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

UI:

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/ui
```

## Telegram Adapter

```powershell
.\scripts\asu_june_bot_start_telegram.ps1
```

Токен хранится только в локальном `.env`.

## Обработка Встреч

Meeting pipeline использует meeting cards:

```text
meetings/<meeting_id>/
  meeting.json
  source/
  transcript/
  chunks/
  artifacts/
  logs/
```

Основные команды:

```powershell
.\.venv\Scripts\python.exe scripts\20_ingest_meeting.py --file "<path>" --title "<title>"
.\.venv\Scripts\python.exe scripts\21_extract_audio.py --meeting-dir "<meeting-dir>"
.\.venv\Scripts\python.exe scripts\22_transcribe_meeting.py --meeting-dir "<meeting-dir>" --engine faster-whisper
.\.venv\Scripts\python.exe scripts\26_chunk_meeting.py --meeting-dir "<meeting-dir>"
.\.venv\Scripts\python.exe scripts\29_analyze_meeting.py --meeting-dir "<meeting-dir>"
```

Runtime meeting outputs могут содержать приватные данные и не должны попадать в Git.

## Публичные Примеры

- [Sample transcript](examples/ru/sample_transcript.md)
- [Sample protocol](examples/ru/sample_protocol.md)
- [Sample summary](examples/ru/sample_summary.md)
- [Sample action items](examples/ru/sample_action_items.json)

## Документация

- [Текущий контекст](docs/context.md)
- [Решения](docs/decisions.md)
- [Todo](docs/todo.md)
- [Project Knowledge Bot](docs/project_knowledge_bot.md)
- [Quality artifacts policy](docs/quality/README.md)
- [Privacy and data](docs/security/PRIVACY_AND_DATA.md)
- [Meeting pipeline](docs/operations/MEETING_PIPELINE.md)

## Разработка

```powershell
.\.venv\Scripts\python.exe -m compileall scripts src tests
.\.venv\Scripts\python.exe -m pytest tests/asu_june_bot -q
```

Перед PR не коммитьте секреты, приватные документы, runtime indexes, transcripts, logs и generated eval reports.
