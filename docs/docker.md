# Docker для MeetingAgent

Docker-упаковка предназначена для локального API, meeting search/indexing runtime, Telegram adapter и optional meeting diarization/transcription runtime. GigaAM в основной image не включен: его зависимости остаются отдельным runtime до стабилизации Windows/Python/ONNX.

Default deployment является local-only: Compose публикует API только на
127.0.0.1. Image работает как UID/GID 10001:10001, с read-only rootfs,
no-new-privileges и без Linux capabilities. Docker build context использует
deny-by-default allowlist и не отправляет .env, runtime data, meetings или
machine-local config overlays Docker daemon.

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
MEETINGAGENT_API_TOKEN=<тот же сильный Bearer token, который использует API>
```

Telegram adapter отправляет `Authorization: Bearer` на защищённый `/chat`.
Без `MEETINGAGENT_API_TOKEN` или allowlist контейнер бота завершается fail-closed.
Разрешение всех chat IDs возможно только явным
`ASU_JUNE_BOT_ALLOW_ALL_CHAT_IDS=true` и не рекомендуется.

## Windows и UTF-8

Для Windows smoke-сессий задавайте UTF-8 явно, чтобы русские реплики,
subtitle-файлы и JSON-артефакты не ломались из-за code page:

```powershell
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()
$env:PYTHONIOENCODING = "utf-8"
```

Это особенно важно для live/transcription smoke-проверок и PowerShell-команд,
которые выводят не-ASCII текст.

Перед запуском на новом ПК выполнить preflight:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c constraints-py312.txt `
  -r requirements.txt -r requirements-transcription.txt
.\.venv\Scripts\python.exe scripts\42_local_preflight.py --mode docker
```

Подробный runbook: [Local Packaging Runbook](operations/LOCAL_PACKAGING.md).

## Запуск API

```powershell
docker compose build api
docker compose up api
```

Проверка:

```powershell
docker compose ps
Invoke-RestMethod http://localhost:8000/health
```

UI:

~~~text
http://localhost:8000/MeetingAgent
http://localhost:8000/ui
~~~

### Local-only profile (default)

Оставьте в .env:

~~~text
MEETINGAGENT_BIND_HOST=127.0.0.1
MEETINGAGENT_DEPLOYMENT_MODE=local
~~~

Порт не доступен с других машин в LAN.

### HTTPS reverse-proxy / self-hosted profile

Сначала настройте TLS reverse proxy, затем явно задайте:

~~~text
MEETINGAGENT_BIND_HOST=0.0.0.0
MEETINGAGENT_DEPLOYMENT_MODE=self_hosted
MEETINGAGENT_ALLOWED_HOSTS=meeting.example.internal
MEETINGAGENT_API_TOKEN=<random value generated with secrets.token_urlsafe(48)>
MEETINGAGENT_TRUSTED_PROXY_CIDRS=<CIDR of the reverse proxy>
~~~

Non-loopback bind без self_hosted отклоняется container entrypoint. В режиме
self_hosted приложение дополнительно прекращает запуск при слабом/missing
machine token, отсутствии Host allowlist и небезопасных auth-настройках. Не
публикуйте 8000 напрямую в интернет; внешний доступ должен идти через HTTPS
reverse proxy. Remote bootstrap включайте только временно с отдельным сильным
MEETINGAGENT_BOOTSTRAP_SECRET, затем отключайте.

Для upload через `/meetings/ingest` задайте на reverse proxy request-body limit
не выше `meetings.max_upload_bytes` из `config.docker.yaml` (по умолчанию
2 ГиБ). Например, для nginx: `client_max_body_size 2048m;`. Proxy limit
отбрасывает oversized body до multipart parser; API повторно проверяет точный
размер media и удаляет partial temporary file при ошибке.

## Запуск Telegram adapter

```powershell
docker compose --profile bot up bot
```

## Volumes

Runtime outputs не входят в image и монтируются с хоста:

~~~text
./data:/app/data
./logs:/app/logs
./meetings:/app/meetings
./vector_db:/app/vector_db
./watched_folder:/app/watched_folder
~~~

На Linux host эти каталоги должны быть writable для UID/GID 10001:10001:

~~~bash
sudo chown -R 10001:10001 data logs meetings vector_db watched_folder
~~~

Docker Desktop на Windows обрабатывает права bind mounts через file sharing.

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

diarization назначает анонимные SPEAKER_XX; реальные имена/роли задаются в
реализованной Speaker mapping панели Workspace.

## Runtime и dev dependencies

- requirements.txt — лёгкий production core без ASR backend.
- requirements-transcription.txt — optional offline ASR (`faster-whisper`); в product image ставится явно.
- constraints-py312.txt — reviewed Python 3.12 resolver lock для core/transcription/diarization/docs/dev.
- requirements-dev.txt — core + transcription + pytest/ruff/pip-tools/pip-audit для разработки и CI.
- requirements-diarization.txt — optional image/profile для diarization.

## Container security smoke

При запущенном Docker Desktop:

~~~powershell
.\.venv\Scripts\python.exe scripts\43_container_smoke.py
~~~

Smoke временно создаёт sentinel вне allowlist, собирает image и проверяет:
non-root UID, отсутствие sentinel и pytest внутри image, а также writable
runtime directories. Sentinel и временный image удаляются в finally.
