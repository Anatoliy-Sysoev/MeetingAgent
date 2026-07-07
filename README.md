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
- Meeting Workspace UI with media, transcript, artifacts, jobs, readiness, and meeting-scoped Q&A.
- One-click meeting pipeline profiles for transcript-only, Q&A-ready, default, and full processing.
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

- [Project Knowledge Bot](docs/project_knowledge_bot.md)

### Package Status

`src/meeting_agent/` is the planned general MeetingAgent package. The implemented shared meeting-processing layers currently include transcription, diarization, and live-transcription helpers.

The production-ready reference API/UI runtime currently lives in `src/asu_june_bot/`. Legacy `scripts/01_*` ... `scripts/09_chat.py` are kept for compatibility and migration reference.

## Public Examples

Synthetic examples are available for a safe first look at the meeting artifact format:

- [Synthetic meeting dataset](examples/meeting_dataset/README.md)
- [Sample transcript](examples/en/sample_transcript.md)
- [Sample protocol](examples/en/sample_protocol.md)
- [Sample summary](examples/en/sample_summary.md)
- [Sample action items](examples/en/sample_action_items.json)

These examples do not contain private project data.

## Quickstart

### 1. Install Dependencies

```powershell
git clone https://github.com/Anatoliy-Sysoev/MeetingAgent.git
cd MeetingAgent
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 2. Configure Local Runtime

```powershell
Copy-Item .env.example .env
```

Edit `.env` and set `MEETINGAGENT_API_TOKEN` to a strong random secret before starting the API. Do not commit `.env`, tokens, private corpora, meeting files, logs, or local indexes.

For local Ollama workflows, install required models:

```powershell
ollama pull bge-m3
ollama pull qwen3.5:4b
```

On Windows, use a single ASCII Ollama model store before running Docker/API workflows:

```powershell
.\scripts\start_ollama_local.ps1 -Restart
```

See [Ollama local runtime](docs/operations/OLLAMA_LOCAL_RUNTIME.md).

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

The built-in web UI supports local login, displays the current auth state, obtains CSRF tokens through `GET /auth/csrf`, and sends authenticated `/chat` requests from the browser. See [API and Auth Setup](docs/en/API_AUTH_SETUP.md).

### 4. Ask A CLI Question

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_chat.py `
  "What project integrations are described?" `
  --mode hybrid `
  --top-k 5 `
  --model qwen3.5:4b
```

### 5. Run Telegram Adapter

```powershell
.\scripts\asu_june_bot_start_telegram.ps1
```

Keep the Telegram token in local `.env` only. See [Project Knowledge Bot](docs/project_knowledge_bot.md).

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
.\.venv\Scripts\python.exe scripts\22_transcribe_meeting.py --meeting-dir "<meeting-dir>" --engine faster-whisper --model large-v3-turbo --language ru --compute-type int8
.\.venv\Scripts\python.exe scripts\23_diarize_meeting.py --meeting-dir "<meeting-dir>" --dry-run
.\.venv\Scripts\python.exe scripts\24_merge_transcript_speakers.py --meeting-dir "<meeting-dir>"
.\.venv\Scripts\python.exe scripts\26_chunk_meeting.py --meeting-dir "<meeting-dir>"
.\.venv\Scripts\python.exe scripts\27_enrich_meeting_chunks.py --meeting-dir "<meeting-dir>"
.\.venv\Scripts\python.exe scripts\28_index_meeting_chunks.py --meeting-dir "<meeting-dir>"
.\.venv\Scripts\python.exe scripts\29_analyze_meeting.py --meeting-dir "<meeting-dir>"
```

Speaker diarization is optional and uses an isolated `sherpa-onnx` path by default. Install optional dependencies from `requirements-diarization.txt` and keep downloaded ONNX models under ignored `models/diarization/`.

Runtime meeting outputs may contain private data and should not be committed.

### Meeting Workspace

Processed or partially processed meetings can be reviewed in the browser:

```text
http://127.0.0.1:8000/meetings/<meeting_id>/workspace
```

The workspace includes:

- media player and clickable transcript;
- artifact viewer;
- pipeline stage controls and readiness map;
- one-click pipeline profiles through `POST /meetings/{id}/jobs/pipeline`;
- meeting-scoped search and Q&A with vector retrieval fallback, timestamps, speaker labels, and source citations.

The current product gap is not the basic pipeline, but the next layer of product contracts: artifact manifest, stage error/retry contract, and a smoother upload-to-review UI flow.

### Live Transcription

Live transcription is an optional draft workflow. The first supported backend is local Vosk; it writes source-scoped draft live artifacts into `transcript/live/` and does not replace the canonical offline transcript from `scripts/22_transcribe_meeting.py`.

Install optional live dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-live.txt
```

Keep Vosk models under ignored `models/`, for example:

```text
models/vosk/vosk-model-small-ru-0.22/
```

Dry-run:

```powershell
.\.venv\Scripts\python.exe scripts\33_live_transcribe_meeting.py `
  --meeting-dir "<meeting-dir>" `
  --engine vosk `
  --model-path models\vosk\vosk-model-small-ru-0.22 `
  --source MIC `
  --dry-run
```

Deterministic smoke from a prepared mono 16 kHz WAV:

```powershell
.\.venv\Scripts\python.exe scripts\33_live_transcribe_meeting.py `
  --meeting-dir "<meeting-dir>" `
  --engine vosk `
  --model-path models\vosk\vosk-model-small-ru-0.22 `
  --input-wav "<meeting-dir>\source\audio_16k_mono.wav" `
  --source MIX `
  --vad silero `
  --duration-sec 30 `
  --force
```

For live microphone sessions, `Ctrl+C` is treated as a graceful stop: accumulated segments are finalized and written. Live draft completion leaves `processing_status=processing`, so final offline ASR can still run afterwards.

## Docker

The Docker setup packages the local API, optional Telegram adapter, and an optional diarization/meeting-processing profile. GigaAM is intentionally not included in the main image.

```powershell
Copy-Item .env.example .env
docker compose build api
docker compose up api
```

Optional diarization image:

```powershell
docker compose --profile diarization build diarization
```

See [Docker documentation](docs/docker.md).
For a repeatable local machine setup, run preflight first and follow
[Local Packaging Runbook](docs/operations/LOCAL_PACKAGING.md).

## Authentication

The API uses a machine Bearer token (`MEETINGAGENT_API_TOKEN`) for script and service-to-service access, and optional local cookie sessions for browser use.

See [API and Auth Setup](docs/en/API_AUTH_SETUP.md) for the full reference: token setup, RBAC, CSRF, all endpoints, error codes, reverse proxy, and secure storage.

## Documentation

- [Russian README](README.ru.md)
- [API and Auth Setup](docs/en/API_AUTH_SETUP.md)
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
