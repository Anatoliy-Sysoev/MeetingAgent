# Запуск Bot v2 Yandex на другом локальном ПК

Обновлено: 2026-06-03.

## Назначение

Инструкция для переноса и запуска `Project Knowledge Bot v2` с корпусом `ntk_yandex_corpus` на другом локальном Windows-ПК.

Целевой режим:

```text
GitHub repo -> Docker API -> локальная Ollama на хосте -> data/asu_june_bot_ntk runtime corpus -> Web UI / Telegram
```

## Что лежит в Git, а что нужно запросить

В Git лежат код, Docker-упаковка, конфиги, тесты и документация.

В Git **не лежат** runtime-данные корпуса:

```text
data/asu_june_bot_ntk/chunks_v2.jsonl
data/asu_june_bot_ntk/source_links.jsonl
data/asu_june_bot_ntk/embeddings_cache_v2.jsonl
data/asu_june_bot_ntk/index_v2_report.json
data/asu_june_bot_ntk/numpy_index_v2/manifest.json
data/asu_june_bot_ntk/numpy_index_v2/metadata.jsonl
data/asu_june_bot_ntk/numpy_index_v2/embeddings.npy
```

Причина: `data/*`, `*.jsonl`, индексы и кеши являются локальными сгенерированными артефактами и игнорируются `.gitignore`.

Для быстрого запуска на другом ПК нужно запросить готовый runtime-пакет:

```text
data/asu_june_bot_ntk/
```

Минимальный обязательный состав пакета:

```text
chunks_v2.jsonl
source_links.jsonl
index_v2_report.json
numpy_index_v2/
  manifest.json
  metadata.jsonl
  embeddings.npy
```

Опционально, но полезно для resumable-пересборки embeddings:

```text
embeddings_cache_v2.jsonl
```

Если пакет не передан, бот можно поднять только после пересборки корпуса из исходной папки Яндекс.Диска.

## Требования

На новом ПК установить:

```text
Git
Docker Desktop
Ollama
```

В Ollama должны быть модели:

```powershell
ollama pull bge-m3
ollama pull qwen2.5:7b-instruct
```

Проверка:

```powershell
ollama list
curl.exe http://localhost:11434/api/tags
```

## Быстрый запуск через Docker

### 1. Склонировать репозиторий

```powershell
cd $env:USERPROFILE\Desktop\AI
git clone https://github.com/Anatoliy-Sysoev/MeetingAgent.git
cd MeetingAgent
```

### 2. Подготовить `.env`

```powershell
Copy-Item .env.example .env
notepad .env
```

Для Yandex/NTK корпуса выставить:

```dotenv
ASU_JUNE_BOT_ACTIVE_CORPUS=ntk
MEETINGAGENT_API_PORT=8000
```

Для Telegram adapter дополнительно заполнить локально, не коммитить:

```dotenv
ASU_JUNE_BOT_TELEGRAM_TOKEN=...
ASU_JUNE_BOT_ALLOWED_CHAT_IDS=...
ASU_JUNE_BOT_CHAT_API_URL=http://api:8000/chat
```

### 3. Положить runtime-пакет корпуса

Создать папку:

```powershell
New-Item -ItemType Directory -Force data\asu_june_bot_ntk
```

Скопировать переданный пакет так, чтобы получилась структура:

```text
MeetingAgent/
  data/
    asu_june_bot_ntk/
      chunks_v2.jsonl
      source_links.jsonl
      index_v2_report.json
      numpy_index_v2/
        manifest.json
        metadata.jsonl
        embeddings.npy
```

Если `chunks_v2.jsonl` и `numpy_index_v2/manifest.json` отсутствуют, GitHub-репозитория недостаточно: нужно запросить runtime-пакет или пересобрать корпус.

### 4. Собрать и запустить API

```powershell
docker compose build api
docker compose up api
```

Открыть:

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/ui
```

Проверить health:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

### 5. Проверить поиск и chat

Проверка `/search`:

```powershell
$body = @{
  query = "Что указано в ЦТА про RTO и RPO?"
  mode = "hybrid"
  top_k = 5
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/search" `
  -ContentType "application/json" `
  -Body $body
```

Проверка `/chat`:

```powershell
$body = @{
  query = "Что указано в ЦТА про RTO и RPO?"
  mode = "hybrid"
  top_k = 5
  model = "qwen2.5:7b-instruct"
  max_tokens = 700
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/chat" `
  -ContentType "application/json" `
  -Body $body
```

Ожидаемо:

```text
status = answered
sources не пустые
ответ содержит citations / источники
```

## Запуск Telegram adapter через Docker

В `.env` должны быть заданы:

```dotenv
ASU_JUNE_BOT_TELEGRAM_TOKEN=...
ASU_JUNE_BOT_ALLOWED_CHAT_IDS=...
ASU_JUNE_BOT_ACTIVE_CORPUS=ntk
```

Запуск API + Telegram adapter:

```powershell
docker compose --profile bot up api bot
```

Важно: token хранится только в локальном `.env`; `.env` не коммитится.

## Запуск без Docker

Если Docker недоступен:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Активировать Yandex/NTK corpus:

```powershell
$env:ASU_JUNE_BOT_ACTIVE_CORPUS = "ntk"
```

Health:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_health_v2.py --json
```

API:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_api.py --host 127.0.0.1 --port 8000
```

Telegram:

```powershell
.\scripts\asu_june_bot_start_telegram.ps1 -AllowedChatIds "123456789"
```

## Если runtime-пакета нет

Нужно пересобрать корпус из исходных файлов:

```text
C:\Users\<user>\Desktop\Yandex.Disk\Документы НТК Сдача
```

и, если нужны публичные ссылки на источники:

```text
C:\Users\<user>\Desktop\yandex_disk_full_export\cloud_links_full.csv
```

Команды пересборки описаны в:

```text
docs/subprojects/asu-june-bot/NTK_YANDEX_CORPUS.md
```

Короткая последовательность:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_build_source_links.py `
  --project-root "$env:USERPROFILE\Desktop\Yandex.Disk\Документы НТК Сдача" `
  --cloud-links "$env:USERPROFILE\Desktop\yandex_disk_full_export\cloud_links_full.csv" `
  --output data\asu_june_bot_ntk\source_links.jsonl

.\.venv\Scripts\python.exe scripts\asu_june_bot_extract_text_v2.py `
  --project-root "$env:USERPROFILE\Desktop\Yandex.Disk\Документы НТК Сдача" `
  --source-links data\asu_june_bot_ntk\source_links.jsonl `
  --output-dir data\asu_june_bot_ntk\extracted_v2 `
  --exclude-dir _Obsidian `
  --reset

.\.venv\Scripts\python.exe scripts\asu_june_bot_build_chunks_v2.py `
  --blocks-path data\asu_june_bot_ntk\extracted_v2\blocks.jsonl `
  --output-dir data\asu_june_bot_ntk

.\.venv\Scripts\python.exe scripts\asu_june_bot_build_index_v2.py `
  --chunks-path data\asu_june_bot_ntk\chunks_v2.jsonl `
  --cache-path data\asu_june_bot_ntk\embeddings_cache_v2.jsonl `
  --index-dir data\asu_june_bot_ntk\numpy_index_v2 `
  --report-path data\asu_june_bot_ntk\index_v2_report.json
```

Пересборка embeddings может быть долгой. Для ночной resumable-сборки:

```powershell
.\scripts\monitor_asu_june_bot_ntk_index.ps1 -Loop -IntervalMinutes 30
```

## Troubleshooting

### `vector_ready=false`

Проверить:

```text
data/asu_june_bot_ntk/numpy_index_v2/manifest.json
data/asu_june_bot_ntk/numpy_index_v2/embeddings.npy
```

Проверить Ollama:

```powershell
ollama list
ollama pull bge-m3
```

### `/chat` медленно отвечает

Локальная CPU-модель `qwen2.5:7b-instruct` может отвечать долго. Не использовать `qwen3:8b` как default на CPU.

### API в Docker не видит Ollama

Проверить на хосте:

```powershell
curl.exe http://localhost:11434/api/tags
```

В Docker используется:

```text
http://host.docker.internal:11434
http://host.docker.internal:11434/v1
```

### Нет sources или статус `no_sources`

Проверить, что активен корпус:

```dotenv
ASU_JUNE_BOT_ACTIVE_CORPUS=ntk
```

Проверить наличие:

```text
data/asu_june_bot_ntk/chunks_v2.jsonl
data/asu_june_bot_ntk/numpy_index_v2/metadata.jsonl
```

### Git показывает много файлов в `data/`

Это runtime-артефакты. Их не коммитить.
