# Local Packaging Runbook

Цель: повторяемо запустить MeetingAgent API/UI/pipeline на другом локальном ПК без приватных данных в Git.

## Что входит

- Docker Compose runtime для API/UI.
- Host-mounted runtime volumes:
  - `./meetings:/app/meetings`
  - `./data:/app/data`
  - `./logs:/app/logs`
  - `./vector_db:/app/vector_db`
  - `./watched_folder:/app/watched_folder`
- Healthcheck контейнера API через `GET /health`.
- Preflight CLI для проверки Docker, Ollama, моделей и ASR-зависимостей.
- Non-root image (10001:10001), deny-by-default build context и localhost-only publish.

## Что не входит

- GigaAM runtime в default Docker image.
- Приватные модели, записи встреч, транскрипты, индексы и customer corpus.
- Cloud deployment.

GigaAM остаётся отдельным локальным backend. Для него использовать `requirements-gigaam.txt`
и ignored runtime окружение/кэш по инструкции `docs/operations/GIGAAM_TRANSCRIPTION.md`.

## Требования

На хосте:

- Windows PowerShell.
- Docker Desktop.
- Python 3.11+ для preflight, если запускаете проверку до сборки контейнера.
- Ollama с моделями:
  - `bge-m3`
  - `qwen3.5:4b`

Ollama должен быть доступен с хоста и из Docker через:

```text
http://localhost:11434
http://host.docker.internal:11434
```

## Подготовка

```powershell
git clone https://github.com/Anatoliy-Sysoev/MeetingAgent.git
cd MeetingAgent
Copy-Item .env.example .env
```

В `.env` заменить:

```text
MEETINGAGENT_API_TOKEN=CHANGE_THIS_TO_A_LONG_RANDOM_SECRET
```

Сгенерировать токен:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Создать runtime-папки, если Git их не создал:

```powershell
New-Item -ItemType Directory -Force data,logs,meetings,vector_db,watched_folder | Out-Null
```

На Linux назначить их container user:

~~~bash
sudo chown -R 10001:10001 data logs meetings vector_db watched_folder
~~~

## Preflight

Проверка Docker-пути:

```powershell
.\.venv\Scripts\python.exe scripts\42_local_preflight.py --mode docker
```

Если `.venv` ещё нет:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts\42_local_preflight.py --mode docker
```

Проверка локального Python/ASR-пути:

```powershell
.\.venv\Scripts\python.exe scripts\42_local_preflight.py --mode local --optional-asr
```

JSON-вывод для диагностики:

```powershell
.\.venv\Scripts\python.exe scripts\42_local_preflight.py --mode docker --json
```

Типовые ошибки:

| Check | Причина | Действие |
| --- | --- | --- |
| `docker` / `docker_compose` | Docker Desktop не запущен или не в PATH | Запустить Docker Desktop, проверить `docker compose version` |
| `ollama_api` | Ollama не отвечает | Запустить `ollama serve` или desktop app |
| `embedding_model` | Нет `bge-m3` | `ollama pull bge-m3` |
| `chat_model` | Нет `qwen3.5:4b` | `ollama pull qwen3.5:4b` |
| `ffmpeg` | Нет ffmpeg на host | Для Docker API не блокер; для local ASR установить ffmpeg |

## Запуск API/UI

```powershell
docker compose build api
docker compose up -d api
```

Проверка:

```powershell
docker compose ps
Invoke-RestMethod http://localhost:8000/health
```

Workspace/API:

~~~text
http://localhost:8000/MeetingAgent
http://localhost:8000/ui
http://localhost:8000/meetings
~~~

Для браузера сначала создать локального admin:

```powershell
$body = @{
  email = "admin@example.local"
  password = "<strong-local-password>"
  display_name = "Admin"
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8000/admin/bootstrap `
  -ContentType "application/json" `
  -Body $body
```

## Deployment profiles

### Local-only (default)

~~~text
MEETINGAGENT_BIND_HOST=127.0.0.1
MEETINGAGENT_DEPLOYMENT_MODE=local
~~~

### Self-hosted behind HTTPS reverse proxy

~~~text
MEETINGAGENT_BIND_HOST=0.0.0.0
MEETINGAGENT_DEPLOYMENT_MODE=self_hosted
MEETINGAGENT_ALLOWED_HOSTS=meeting.example.internal
MEETINGAGENT_API_TOKEN=<strong random token>
MEETINGAGENT_TRUSTED_PROXY_CIDRS=<proxy CIDR>
~~~

Container entrypoint запрещает non-loopback publish в local mode. Startup
safety validator в self_hosted mode проверяет token strength, Host allowlist,
cookie/bootstrap/proxy policy и завершает процесс при небезопасной конфигурации.
Не открывайте Uvicorn напрямую в интернет.

## Container smoke

~~~powershell
.\.venv\Scripts\python.exe scripts\43_container_smoke.py
~~~

Проверяются non-root UID, исключение private sentinel из image, отсутствие
test dependencies и writable runtime paths. Для разработки/тестов используйте
requirements-dev.txt; production image ставит только requirements.txt.

## Запуск pipeline через Docker

Если записи лежат вне репозитория:

```powershell
$env:MEETINGAGENT_RECORDINGS_DIR = "$env:USERPROFILE\Desktop\Recordings"
```

Ingest:

```powershell
docker compose run --rm api `
  python scripts/20_ingest_meeting.py `
  --file "/app/watched_folder/meeting.mp4" `
  --title "Рабочая встреча"
```

Если файл монтируется через `MEETINGAGENT_RECORDINGS_DIR`, используйте optional profile:

```powershell
docker compose --profile diarization run --rm diarization `
  python scripts/20_ingest_meeting.py `
  --file "/host/recordings/meeting.mp4" `
  --title "Рабочая встреча"
```

Дальше удобнее запускать из Workspace: `Run full pipeline`, `Resume pipeline`,
`Retry failed stage`. CLI остаётся доступен для отладки:

```powershell
docker compose run --rm api python scripts/21_extract_audio.py --meeting-dir meetings/<id>
docker compose run --rm api python scripts/22_transcribe_meeting.py --meeting-dir meetings/<id> --engine faster-whisper --model large-v3-turbo
docker compose run --rm api python scripts/26_chunk_meeting.py --meeting-dir meetings/<id>
docker compose run --rm api python scripts/28_index_meeting_chunks.py --meeting-dir meetings/<id>
```

## Telegram adapter

Заполнить `.env`:

```text
ASU_JUNE_BOT_TELEGRAM_TOKEN=...
ASU_JUNE_BOT_ALLOWED_CHAT_IDS=...
MEETINGAGENT_API_TOKEN=<strong API Bearer token>
```

Bot startup is fail-closed: it requires both the API Bearer token and either
an allowlist or an explicit `ASU_JUNE_BOT_ALLOW_ALL_CHAT_IDS=true` development opt-in.

Запуск:

```powershell
docker compose --profile bot up -d bot
```

## Остановка

```powershell
docker compose down
```

Runtime outputs остаются в `data/`, `logs/`, `meetings/`, `vector_db/`,
`watched_folder/` и не должны попадать в Git.
