# Docker для MeetingAgent

Docker-упаковка предназначена для локального API, meeting search/indexing runtime и Telegram adapter. GigaAM в основной image не включен: его зависимости остаются отдельным runtime до стабилизации Windows/Python/ONNX.

## Сервисы

```text
api  - FastAPI Project Knowledge Bot, endpoints /health, /search, /chat, /ui
bot  - Telegram adapter поверх http://api:8000/chat, запускается profile bot
```

Ollama запускается отдельно на хосте или в отдельном контейнере. По умолчанию контейнер ходит к:

```text
http://host.docker.internal:11434
http://host.docker.internal:11434/v1
```

## Подготовка

```powershell
Copy-Item .env.example .env
```

В `.env` не коммитить секреты. Для Telegram указать:

```text
ASU_JUNE_BOT_TELEGRAM_TOKEN=...
ASU_JUNE_BOT_ALLOWED_CHAT_IDS=...
```

## Запуск API

```powershell
docker compose build api
docker compose up api
```

Проверка:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

UI:

```text
http://localhost:8000/ui
```

## Запуск Telegram adapter

```powershell
docker compose --profile bot up bot
```

## Volumes

Runtime outputs не входят в image и монтируются с хоста:

```text
./data:/app/data
./logs:/app/logs
./meetings:/app/meetings
./vector_db:/app/vector_db
./watched_folder:/app/watched_folder
```

## Конфигурация

В контейнере используется:

```text
MEETING_AGENT_CONFIG_PATH=/app/config.docker.yaml
```

`config.docker.yaml` задает `/app`-пути и external Ollama. Локальный `config.yaml` с Windows-путями не нужен внутри контейнера.

## ASR

В image установлен `ffmpeg` и зависимости из `requirements.txt`, включая `faster-whisper`. Базовый CLI доступен внутри контейнера:

```powershell
docker compose run --rm api python scripts/22_transcribe_meeting.py --help
```

GigaAM запускать отдельно или через будущий optional image.
