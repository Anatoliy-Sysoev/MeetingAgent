# Быстрый Старт

[English](../en/quickstart.md) | [Русский](quickstart.md)

## Установка

```powershell
git clone https://github.com/Anatoliy-Sysoev/MeetingAgent.git
cd MeetingAgent
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c constraints-py312.txt `
  -r requirements.txt -r requirements-transcription.txt
```

## Настройка

```powershell
Copy-Item .env.example .env
```

Не коммитьте `.env` и приватные runtime data.

Для локальных Ollama workflows:

```powershell
ollama pull bge-m3
ollama pull qwen3.5:4b
```

## Запуск API

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_api.py --host 127.0.0.1 --port 8000
```

Проверка:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Открыть:

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/ui
```

## Задать Вопрос

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_chat.py `
  "Какие интеграции описаны в проекте?" `
  --mode hybrid `
  --top-k 5 `
  --model qwen3.5:4b
```

## Тесты

```powershell
.\.venv\Scripts\python.exe -m pip install -c constraints-py312.txt -r requirements-dev.txt
.\.venv\Scripts\python.exe scripts\46_ci_verify.py
```
