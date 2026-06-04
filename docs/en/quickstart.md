# Quickstart

[English](quickstart.md) | [Русский](../ru/quickstart.md)

## Install

```powershell
git clone <repo-url>
cd MeetingAgent
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Configure

```powershell
Copy-Item .env.example .env
```

Do not commit `.env` or private runtime data.

For local Ollama workflows:

```powershell
ollama pull bge-m3
ollama pull qwen2.5:7b-instruct
```

## Run API

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_api.py --host 127.0.0.1 --port 8000
```

Check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Open:

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/ui
```

## Ask A Question

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_chat.py `
  "What project integrations are described?" `
  --mode hybrid `
  --top-k 5 `
  --model qwen2.5:7b-instruct
```

## Run Tests

```powershell
.\.venv\Scripts\python.exe -m compileall scripts src tests
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot -q
```
