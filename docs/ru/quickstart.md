# Быстрый Старт

[English](../en/quickstart.md) | [Русский](quickstart.md)

## Установка

```powershell
git clone <repo-url>
cd MeetingAgent
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Настройка

```powershell
Copy-Item .env.example .env
```

Не коммитьте `.env` и приватные runtime data.

Для локальных Ollama workflows:

```powershell
ollama pull bge-m3
ollama pull qwen2.5:7b-instruct
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
  --model qwen2.5:7b-instruct
```

## Тесты

```powershell
.\.venv\Scripts\python.exe -m compileall scripts src tests
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot -q
```
