# Как Участвовать

[English](CONTRIBUTING.md) | [Русский](CONTRIBUTING.ru.md)

Спасибо за вклад в MeetingAgent. Это ранний local-first OSS-инструмент для проектной памяти, обработки встреч, source-grounded RAG и evaluation workflows.

## Настройка Разработки

```powershell
git clone <repo-url>
cd MeetingAgent
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Копируйте `.env.example` в `.env` только для локальных runtime-настроек. `.env` нельзя коммитить.

## Проверки

```powershell
.\.venv\Scripts\python.exe -m compileall scripts src tests
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot -q
```

Некоторые workflows требуют локальные инструменты или модели:

- Ollama для локального chat и embeddings;
- `bge-m3` для embeddings;
- `qwen2.5:7b-instruct` или другая локальная chat model;
- ffmpeg/faster-whisper/GigaAM для transcription workflows.

Если проверка требует приватные runtime data, используйте synthetic examples или явно укажите skipped dependency.

## Checklist Pull Request

Перед PR:

- держите change focused;
- запустите релевантные tests или объясните, почему они не запускались;
- обновите `README.md`, `docs/context.md`, `docs/todo.md` или более точную документацию, если меняется behavior;
- не коммитьте secrets, `.env`, `config.yaml`, local logs, vector indexes, corpora, meeting media или generated runtime data;
- добавьте security notes для file handling, model providers, API routes, exports или guardrail changes.

## Документация

Публичная OSS-документация поддерживается на английском и русском:

- `README.md` / `README.ru.md`;
- `SECURITY.md` / `SECURITY.ru.md`;
- `CONTRIBUTING.md` / `CONTRIBUTING.ru.md`;
- `docs/en/*` / `docs/ru/*` для public docs.

При изменении публичной документации обновляйте обе языковые версии или помечайте translation как outdated.

Текущее состояние проекта фиксируется в:

- `docs/context.md`;
- `docs/todo.md`;
- `docs/decisions.md`.

## Security-Sensitive Изменения

Делайте небольшой PR и запрашивайте явный review для изменений, затрагивающих:

- local path handling и file ingestion;
- transcript parsing и artifact export;
- API keys или external model providers;
- guardrails и project-only routing;
- Telegram, Web UI, FastAPI или Docker runtime behavior;
- generated files и customer-specific corpora.

См. `SECURITY.md`.

## Issues

Хороший issue содержит:

- понятные шаги воспроизведения;
- expected и actual behavior;
- synthetic input files, если возможно;
- релевантный command output;
- информацию о том, участвовали ли local models, Docker, Telegram или external APIs.

Не вставляйте публично private transcripts, customer documents, API keys, tokens или internal project data.
