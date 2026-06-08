# Ollama Local Runtime

## Цель

MeetingAgent использует локальный Ollama для:

- embeddings через `bge-m3`;
- Project Knowledge Bot и meeting analysis через `qwen3.5:4b`;
- Docker runtime через `host.docker.internal:11434`.

Ollama должен быть запущен с одним каноническим model store, иначе Docker/API могут видеть другой набор моделей.

## Канонический Model Store

Для Windows использовать ASCII-путь:

```powershell
C:\ollama-models
```

Причины:

- в этом store уже лежат `qwen3.5:4b` и `qwen3.5:9b`;
- `bge-m3` может падать при загрузке blob из Unicode-пути профиля Windows;
- Docker-контейнеры не читают модели напрямую, а обращаются к активному Ollama API, поэтому важен именно model store запущенного `ollama serve`.

## Запуск

Предпочтительный запуск из репозитория:

```powershell
.\scripts\start_ollama_local.ps1 -Restart
```

Скрипт выставляет:

```text
OLLAMA_MODELS=C:\ollama-models
OLLAMA_KEEP_ALIVE=24h
OLLAMA_NUM_PARALLEL=1
```

Затем запускает `ollama serve` и проверяет `/api/tags`.

## Проверка

```powershell
ollama list
ollama show qwen3.5:4b
ollama show bge-m3
```

Проверка API:

```powershell
Invoke-RestMethod http://localhost:11434/api/tags
```

Проверка из Docker:

```powershell
docker compose --profile diarization run --rm diarization `
  python -c "import requests; print(requests.get('http://host.docker.internal:11434/api/tags').text[:1000])"
```

## Если Модель Не Видна

Если `C:\ollama-models` содержит manifest, но `ollama list` не показывает модель, активный Ollama server запущен с другим `OLLAMA_MODELS`.

Действия:

1. Закрыть Ollama из tray или выполнить `.\scripts\start_ollama_local.ps1 -Restart`.
2. Проверить `ollama list`.
3. Проверить `/api/tags` из Docker.
4. Только после этого запускать `scripts/29_analyze_meeting.py`.

## Дубли Model Store

В локальной машине могут существовать несколько store:

```text
C:\ollama-models
C:\Users\<user>\.ollama\models
C:\ollama_models
```

Не удалять их автоматически. Сначала подтвердить, что `C:\ollama-models` используется активным Ollama server и содержит нужные модели. Очистка дублей выполняется отдельным ручным шагом.

