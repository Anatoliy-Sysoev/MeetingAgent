# MeetingAgent

[English](README.md) | [Русский](README.ru.md)

Local-first open-source meeting intelligence and project memory tool.

MeetingAgent helps teams turn project documents, meeting recordings, and transcripts into searchable, source-grounded work artifacts: answers with citations, summaries, protocols, decisions, action items, risks, and open questions.

## Why It Matters

Project teams lose requirements, decisions, risks, and action items across calls, chats, shared folders, and evolving documents. MeetingAgent makes that project memory local, searchable, auditable, and reproducible.

The project is intentionally local-first: private documents, transcripts, runtime indexes, and generated artifacts stay on the user's machine unless a workflow explicitly opts into an external model provider.

## Core Capabilities

- Local document ingestion and text extraction.
- RAG index over project documentation.
- Project-only search and chat with citations.
- Source-quality gates and guarded out-of-scope handling.
- Meeting ingestion, transcription, chunking, and artifact generation.
- Meeting memo/protocol generation.
- Decision, action item, risk, and open-question extraction.
- Local FastAPI API, Web UI, and Telegram adapter.
- Evaluation datasets, regression tests, and quality reports.
- Docker packaging for the local API/bot runtime.

## Repository Layout

```text
MeetingAgent/
  scripts/                  CLI entrypoints and automation scripts
  src/                      Python packages
  tests/                    Unit and regression tests
  docs/                     Architecture, context, decisions, quality docs
  docs/subprojects/         Reference Project Knowledge Bot implementation
  eval/                     Evaluation cases and golden answers
  examples/                 Public synthetic examples
  meetings/                 Local meeting cards, not for private data publication
  data/                     Runtime outputs, ignored by Git except placeholders/docs
```

## Main Runtime Areas

### MeetingAgent Core

The core pipeline handles local project documents and meeting artifacts:

```text
documents / audio / video
  -> extraction / transcription
  -> chunking
  -> indexing
  -> source-grounded search/chat
  -> summaries, protocols, decisions, tasks, risks
```

### Project Knowledge Bot

`Project Knowledge Bot` is a reference implementation of a project-only assistant over a private project corpus. It provides:

- `POST /search` for evidence/context retrieval;
- `POST /chat` for grounded answers with citations;
- local Web UI;
- Telegram adapter;
- guardrails for out-of-project, mixed-scope, and unsafe requests;
- quality evaluation and regression workflows.

Detailed documentation:

- [Project Knowledge Bot README](docs/subprojects/asu-june-bot/README.md)
- [Bot v2 Yandex local setup](docs/subprojects/asu-june-bot/README_YANDEX_V2_LOCAL.md)
- [Telegram adapter](docs/subprojects/asu-june-bot/telegram.md)

## Quickstart

### 1. Install Dependencies

```powershell
git clone <repo-url>
cd MeetingAgent
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 2. Configure Local Runtime

```powershell
Copy-Item .env.example .env
```

Do not commit `.env`, tokens, private corpora, meeting files, logs, or local indexes.

For local Ollama workflows, install required models:

```powershell
ollama pull bge-m3
ollama pull qwen2.5:7b-instruct
```

### 3. Run The Project Knowledge Bot API

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_api.py --host 127.0.0.1 --port 8000
```

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Open the local UI:

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/ui
```

### 4. Ask A CLI Question

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_chat.py `
  "What project integrations are described?" `
  --mode hybrid `
  --top-k 5 `
  --model qwen2.5:7b-instruct
```

### 5. Run Telegram Adapter

```powershell
.\scripts\asu_june_bot_start_telegram.ps1
```

See [Telegram adapter docs](docs/subprojects/asu-june-bot/telegram.md).

## Meeting Processing

The meeting pipeline is designed around meeting cards:

```text
meetings/<meeting_id>/
  meeting.json
  source/
  transcript/
  chunks/
  artifacts/
  logs/
```

Important entrypoints:

```powershell
.\.venv\Scripts\python.exe scripts\20_ingest_meeting.py --file "<path>" --title "<title>"
.\.venv\Scripts\python.exe scripts\21_extract_audio.py --meeting-dir "<meeting-dir>"
.\.venv\Scripts\python.exe scripts\22_transcribe_meeting.py --meeting-dir "<meeting-dir>" --engine faster-whisper
.\.venv\Scripts\python.exe scripts\26_chunk_meeting.py --meeting-dir "<meeting-dir>"
.\.venv\Scripts\python.exe scripts\29_analyze_meeting.py --meeting-dir "<meeting-dir>"
```

Runtime meeting outputs may contain private data and should not be committed.

## Docker

The Docker setup packages the local API and optional Telegram adapter. GigaAM is intentionally not included in the main image.

```powershell
Copy-Item .env.example .env
docker compose build api
docker compose up api
```

See [Docker documentation](docs/docker.md).

## Documentation

- [Russian README](README.ru.md)
- [Security policy](SECURITY.md)
- [Contributing guide](CONTRIBUTING.md)
- [Architecture index](docs/architecture/ARCHITECTURE.md)
- [Current project context](docs/context.md)
- [Decisions](docs/decisions.md)
- [TODO](docs/todo.md)
- [Translation policy](docs/translation_policy.md)

Public bilingual documentation is being organized under:

```text
docs/en/
docs/ru/
```

## Examples

Synthetic public examples:

- [Sample transcript](examples/en/sample_transcript.md)
- [Sample protocol](examples/en/sample_protocol.md)
- [Sample summary](examples/en/sample_summary.md)
- [Sample action items](examples/en/sample_action_items.json)

Do not publish real customer transcripts or private project documents as examples.

## Tests

```powershell
.\.venv\Scripts\python.exe -m compileall scripts src tests
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot -q
```

Some tests and smoke checks require local runtime data or local model services. Use synthetic data for public reproduction whenever possible.

## Security

MeetingAgent can touch sensitive local files, transcripts, indexes, and model provider credentials. Read [SECURITY.md](SECURITY.md) before contributing to ingestion, model integrations, API routes, exports, Telegram, Docker, or guardrail logic.

## Contributing

Contributions are welcome. Start with [CONTRIBUTING.md](CONTRIBUTING.md).

Before opening a PR:

- keep the change focused;
- run relevant checks;
- update docs;
- do not commit secrets or runtime data;
- include security notes when data handling changes.

## License

MIT. See [LICENSE](LICENSE).
