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
- локальный Web UI с login-панелью, auth badge и CSRF-safe chat;
- Telegram adapter;
- guardrails для внепроектных, смешанных и unsafe-запросов;
- quality/eval workflows.

Документация:

```text
docs/project_knowledge_bot.md
```

Примечание: приватные корпуса, generated chunks, embeddings, indexes, transcripts и customer-specific runbooks не публикуются. Для локального запуска используется `.env` и ignored runtime paths.

### Legacy Pipeline

`src/meeting_agent/` содержит реализованные product-owned слои transcription,
diarization, live transcription, evaluation и shared infrastructure.
Интегрированный API/UI runtime пока находится в `src/asu_june_bot/`, а его
`core/` и `llm/` являются compatibility shims поверх `meeting_agent.shared`.

Пустые placeholder apps/templates/packages удалены. Скрипты `scripts/01_*` ...
`scripts/18_*` сохранены только для совместимости и при запуске показывают
migration warning. Полный machine-checked inventory находится в
`configs/runtime_inventory.yaml`; см. [границы runtime](docs/ru/runtime_ownership.md).

### Python-Пакеты

`src/meeting_agent/` — независимо запускаемое ядро: API/UI, auth, meetings,
durable jobs, live sessions, transcription, diarization и shared helpers.
`src/asu_june_bot/` — optional-надстройка Project Knowledge Bot. Интегрированный
runtime добавляет search/chat/review/bot UI к core; старые пути перенесённых
модулей временно сохранены как deprecated compatibility aliases.

## Быстрый Старт

```powershell
git clone https://github.com/Anatoliy-Sysoev/MeetingAgent.git
cd MeetingAgent
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c constraints-py312.txt `
  -r requirements.txt -r requirements-transcription.txt
Copy-Item .env.example .env
```

Откройте `.env` и задайте `MEETINGAGENT_API_TOKEN` — длинную случайную строку (не менее 32 символов) — перед первым запуском API.

Для локальных Ollama workflows:

```powershell
ollama pull bge-m3
ollama pull qwen3.5:4b
```

## Запуск MeetingAgent Core

```powershell
.\.venv\Scripts\python.exe scripts\meeting_agent_api.py --host 127.0.0.1 --port 8000
```

## Запуск Интегрированного MeetingAgent + Project Knowledge Bot API

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_api.py --host 127.0.0.1 --port 8000
```

Для одного набора local state запускайте только один API entrypoint. Не
запускайте Core и integrated API одновременно с общими `data/`, `logs/` и
`meetings/`.

Проверка:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

UI:

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/ui
```

Встроенный web UI поддерживает локальный login, показывает auth badge, получает CSRF через `GET /auth/csrf` и отправляет authenticated `/chat` из браузера. См. [Настройка API и авторизации](docs/ru/API_AUTH_SETUP.md).

## Telegram Adapter

```powershell
.\scripts\asu_june_bot_start_telegram.ps1
```

Telegram token и `MEETINGAGENT_API_TOKEN` хранятся только в локальном `.env`.
Обязательно укажите `ASU_JUNE_BOT_ALLOWED_CHAT_IDS`: без allowlist адаптер
запускается только при явном небезопасном opt-in `ASU_JUNE_BOT_ALLOW_ALL_CHAT_IDS=true`.

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
.\.venv\Scripts\python.exe scripts\22_transcribe_meeting.py --meeting-dir "<meeting-dir>" --engine faster-whisper --model large-v3-turbo --language ru --compute-type int8
.\.venv\Scripts\python.exe scripts\23_diarize_meeting.py --meeting-dir "<meeting-dir>" --dry-run
.\.venv\Scripts\python.exe scripts\24_merge_transcript_speakers.py --meeting-dir "<meeting-dir>"
.\.venv\Scripts\python.exe scripts\26_chunk_meeting.py --meeting-dir "<meeting-dir>"
.\.venv\Scripts\python.exe scripts\27_enrich_meeting_chunks.py --meeting-dir "<meeting-dir>"
.\.venv\Scripts\python.exe scripts\28_index_meeting_chunks.py --meeting-dir "<meeting-dir>"
.\.venv\Scripts\python.exe scripts\29_analyze_meeting.py --meeting-dir "<meeting-dir>"
```

Runtime meeting outputs могут содержать приватные данные и не должны попадать в Git.

Для воспроизводимого публичного пути от transcript до protocol см. [Transcript to protocol quickstart](docs/operations/TRANSCRIPT_TO_PROTOCOL_QUICKSTART.md).

### Meeting Workspace

Встречу можно смотреть и запускать из браузера:

```text
http://127.0.0.1:8000/meetings/<meeting_id>/workspace
```

Workspace включает медиаплеер, кликабельный транскрипт, просмотр артефактов, readiness map, stage controls, one-click pipeline profiles и meeting-scoped Q&A с vector retrieval, таймкодами, speaker labels и citations.

Для записи без готового файла откройте `http://127.0.0.1:8000/MeetingAgent`,
выберите **Создать live-встречу**, укажите название/дату/язык и перейдите в
Workspace. Карточка создаётся без фиктивного media; source-scoped WAV появится
только после успешного MIC/SYS capture. Browser POST защищён RBAC и CSRF.

Текущий следующий слой работ: производный MIC+SYS MIX и углубление продуктового
администрирования.

## Публичные Примеры

- [Synthetic meeting dataset](examples/meeting_dataset/README.md)
- [Sample transcript](examples/ru/sample_transcript.md)
- [Sample protocol](examples/ru/sample_protocol.md)
- [Sample summary](examples/ru/sample_summary.md)
- [Sample action items](examples/ru/sample_action_items.json)

## Аутентификация

API использует machine Bearer token (`MEETINGAGENT_API_TOKEN`) для скриптов и сервисных вызовов, и опциональные локальные cookie-сессии для браузера.

Полный справочник: [Настройка API и авторизации](docs/ru/API_AUTH_SETUP.md) — настройка токена, RBAC, CSRF, все эндпоинты, коды ошибок, reverse proxy и безопасное хранение.

## Документация

- [Настройка API и авторизации](docs/ru/API_AUTH_SETUP.md)
- [Текущий контекст](docs/context.md)
- [Решения](docs/decisions.md)
- [Todo](docs/todo.md)
- [Project Knowledge Bot](docs/project_knowledge_bot.md)
- [Quality artifacts policy](docs/quality/README.md)
- [Privacy and data](docs/security/PRIVACY_AND_DATA.md)
- [Meeting pipeline](docs/operations/MEETING_PIPELINE.md)
- [Release process](docs/operations/RELEASE_PROCESS.md)
- [Паритет документации](docs/ru/documentation_parity.md)
- [GitHub Pages documentation site](docs/index.md)

## Разработка

```powershell
.\.venv\Scripts\python.exe -m pip install -c constraints-py312.txt -r requirements-dev.txt
.\.venv\Scripts\python.exe scripts\46_ci_verify.py
```

Перед PR не коммитьте секреты, приватные документы, runtime indexes, transcripts, logs и generated eval reports.
