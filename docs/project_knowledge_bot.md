# Project Knowledge Bot

Project Knowledge Bot is the reference local assistant included in MeetingAgent.

It demonstrates:

- project-only search over a local private corpus;
- source-grounded chat answers;
- out-of-scope guardrails;
- FastAPI endpoints for `/search`, `/chat`, and `/health`;
- optional Telegram adapter;
- local Docker-friendly deployment.

The repository intentionally does not include a real private corpus, generated chunks, embeddings, indexes, customer-specific vocabulary, or customer runbooks. To run the bot on another machine, prepare a local corpus package under ignored runtime paths, then configure the bot through `.env`.

Customer-specific corpus profiles belong in ignored local overlays. For example,
create `configs/asu_june_bot/corpus.local.yaml` with only the private profile:

```yaml
corpora:
  private_project:
    key: private_project
    name: private_project_corpus
    chunks_path: data/private_project/chunks_v2.jsonl
    cache_path: data/private_project/embeddings_cache_v2.jsonl
    index_dir: data/private_project/numpy_index_v2
    report_path: data/private_project/index_v2_report.json
```

Then set `ASU_JUNE_BOT_ACTIVE_CORPUS=private_project` in the ignored `.env`.
The loader merges `configs/asu_june_bot/*.local.yaml` over the public defaults;
these overlays must never be committed.

Minimal local runtime:

```powershell
Copy-Item .env.example .env
.\.venv\Scripts\python.exe scripts\asu_june_bot_api.py --host 127.0.0.1 --port 8000
```

Telegram adapter:

```powershell
.\scripts\asu_june_bot_start_telegram.ps1
```

The adapter authenticates to `/chat` with `MEETINGAGENT_API_TOKEN` and denies
all Telegram chats unless `ASU_JUNE_BOT_ALLOWED_CHAT_IDS` is configured.
`ASU_JUNE_BOT_ALLOW_ALL_CHAT_IDS=true` is an explicit unsafe development-only
opt-in. Keep all tokens only in ignored local `.env` files.
