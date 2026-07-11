# Contributing

[English](CONTRIBUTING.md) | [Русский](CONTRIBUTING.ru.md)

Thank you for contributing to MeetingAgent. This project is an early local-first OSS tool for project memory, meeting processing, source-grounded RAG, and evaluation workflows.

## Development Setup

```powershell
git clone <repo-url>
cd MeetingAgent
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Copy `.env.example` to `.env` only for local runtime settings. Do not commit `.env`.

## Running Checks

```powershell
.\.venv\Scripts\python.exe -m compileall scripts src tests
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot -q
```

Some workflows need local tools or models:

- Ollama for local chat and embeddings;
- `bge-m3` for embeddings;
- `qwen2.5:7b-instruct` or another local chat model;
- ffmpeg/faster-whisper/GigaAM for meeting transcription workflows.

If a check requires private runtime data, use synthetic examples or document the skipped dependency.

## Pull Request Checklist

Before opening a PR:

- keep the change focused;
- run relevant tests or explain why they were not run;
- update `README.md`, `docs/context.md`, `docs/todo.md`, or more specific docs when behavior changes;
- do not commit secrets, `.env`, `config.yaml`, local logs, vector indexes, corpora, meeting media, or generated runtime data;
- include security notes for file handling, model providers, API routes, exports, or guardrail changes.

## Documentation

Public OSS documentation is maintained in English and Russian:

- `README.md` / `README.ru.md`;
- `SECURITY.md` / `SECURITY.ru.md`;
- `CONTRIBUTING.md` / `CONTRIBUTING.ru.md`;
- `docs/en/*` / `docs/ru/*` for public docs.

When changing public documentation, update both language versions or mark the translation as outdated.

Internal project state is tracked in:

- `docs/context.md`;
- `docs/todo.md`;
- `docs/decisions.md`.

## Security-Sensitive Contributions

Open a smaller PR and request explicit review for changes involving:

- local path handling and file ingestion;
- transcript parsing and artifact export;
- API keys or external model providers;
- guardrails and project-only routing;
- Telegram, Web UI, FastAPI, or Docker runtime behavior;
- generated files and customer-specific corpora.

See `SECURITY.md` for the security policy.

## Issues

Good issues include:

- clear reproduction steps;
- expected and actual behavior;
- synthetic input files when possible;
- relevant command output;
- whether local models, Docker, Telegram, or external APIs were involved.

Do not paste private transcripts, customer documents, API keys, tokens, or internal project data into public issues.
