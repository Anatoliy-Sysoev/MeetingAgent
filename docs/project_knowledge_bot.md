# Project Knowledge Bot

Project Knowledge Bot is the reference local assistant included in MeetingAgent.

It demonstrates:

- project-only search over a local private corpus;
- source-grounded chat answers;
- out-of-scope guardrails;
- FastAPI endpoints for `/search`, `/chat`, and `/health`;
- optional Telegram adapter;
- local Docker-friendly deployment.

The repository intentionally does not include a real private corpus, generated chunks, embeddings, indexes, or customer-specific runbooks. To run the bot on another machine, prepare a local corpus package under ignored runtime paths, then configure the bot through `.env`.

Minimal local runtime:

```powershell
Copy-Item .env.example .env
.\.venv\Scripts\python.exe scripts\asu_june_bot_api.py --host 127.0.0.1 --port 8000
```

Telegram adapter:

```powershell
.\scripts\asu_june_bot_start_telegram.ps1
```

Keep tokens only in ignored local `.env` files.
