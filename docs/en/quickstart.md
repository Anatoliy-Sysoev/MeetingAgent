# Quickstart

[English](quickstart.md) | [Русский](../ru/quickstart.md)

## Install

```powershell
git clone https://github.com/Anatoliy-Sysoev/MeetingAgent.git
cd MeetingAgent
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c constraints-py312.txt `
  -r requirements.txt -r requirements-transcription.txt
```

## Configure

```powershell
Copy-Item .env.example .env
```

Do not commit `.env` or private runtime data.

For local Ollama workflows:

```powershell
ollama pull bge-m3
ollama pull qwen3.5:4b
```

## Run API

MeetingAgent Core only:

```powershell
.\.venv\Scripts\python.exe scripts\meeting_agent_api.py --host 127.0.0.1 --port 8000
```

Integrated MeetingAgent + Project Knowledge Bot:

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
http://127.0.0.1:8000/MeetingAgent
```

## Ask A Question

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_chat.py `
  "What project integrations are described?" `
  --mode hybrid `
  --top-k 5 `
  --model qwen3.5:4b
```

## Run Tests

```powershell
.\.venv\Scripts\python.exe -m pip install -c constraints-py312.txt -r requirements-dev.txt
.\.venv\Scripts\python.exe scripts\46_ci_verify.py
```
