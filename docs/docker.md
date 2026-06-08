# Docker для MeetingAgent

Docker-упаковка предназначена для локального API, meeting search/indexing runtime, Telegram adapter и optional meeting diarization/transcription runtime. GigaAM в основной image не включен: его зависимости остаются отдельным runtime до стабилизации Windows/Python/ONNX.

## Сервисы

```text
api          - FastAPI Project Knowledge Bot, endpoints /health, /search, /chat, /ui
bot          - Telegram adapter поверх http://api:8000/chat, запускается profile bot
diarization  - optional image с requirements-diarization.txt для sherpa-onnx и meeting CLI
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

Для качественной offline-транскрибации готовых встреч использовать `large-v3-turbo`:

```powershell
docker compose run --rm api `
  python scripts/22_transcribe_meeting.py `
  --meeting-dir meetings/YYYY-MM-DD__slug `
  --engine faster-whisper `
  --model large-v3-turbo `
  --language ru `
  --compute-type int8 `
  --force
```

`small` допустим только для быстрых черновых smoke/live-проверок.

GigaAM запускать отдельно или через будущий optional image.

## Optional Diarization Image

Сборка:

```powershell
docker compose --profile diarization build diarization
```

ONNX-модели хранятся локально и не коммитятся:

```text
models/diarization/
  sherpa-onnx-pyannote-segmentation-3-0/model.onnx
  wespeaker_en_voxceleb_resnet34_LM.onnx
```

Если исходные записи лежат вне репозитория, смонтировать папку через переменную:

```powershell
$env:MEETINGAGENT_RECORDINGS_DIR = "$env:USERPROFILE\Desktop\ProjectRecordings"
```

Пример полного начала pipeline в контейнере:

```powershell
docker compose --profile diarization run --rm diarization `
  python scripts/20_ingest_meeting.py `
  --file "/host/recordings/meeting.mp4" `
  --title "Рабочая встреча" `
  --meeting-id YYYY-MM-DD__slug `
  --force

docker compose --profile diarization run --rm diarization `
  python scripts/21_extract_audio.py `
  --meeting-dir meetings/YYYY-MM-DD__slug `
  --force

docker compose --profile diarization run --rm diarization `
  python scripts/23_diarize_meeting.py `
  --meeting-dir meetings/YYYY-MM-DD__slug `
  --force
```

После завершения ASR запустить merge:

```powershell
docker compose --profile diarization run --rm diarization `
  python scripts/24_merge_transcript_speakers.py `
  --meeting-dir meetings/YYYY-MM-DD__slug `
  --force
```

`diarization` назначает анонимные `SPEAKER_XX`; реальные имена добавляются только будущим ручным speaker mapping слоем.
