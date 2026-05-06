# MeetingAgent

MeetingAgent is a local-first product for turning project documents and meeting recordings into a searchable project memory.

The product goal is simple: every document, meeting, decision, requirement, and task should become findable, attributable, and usable for producing project deliverables.

## What It Does

- Builds a RAG index over project documentation.
- Watches for new meeting recordings.
- Transcribes audio/video with Whisper-compatible models.
- Produces meeting memo, protocol, decisions, risks, and tasks.
- Classifies content by project stage, FTT, deliverable, document, and task.
- Generates draft project documents from existing source materials.

## Current Local Runtime

The current implementation is script-based:

- `run_full_rag.ps1` runs the full RAG build.
- `monitor_rag.ps1` is a single-tick watchdog for recurring monitoring.
- `scripts/01_inventory.py` inventories project files.
- `scripts/02_extract_text.py` extracts text.
- `scripts/03_build_index.py` chunks text, embeds it with `bge-m3`, and writes ChromaDB.
- `scripts/04_query.py` queries the RAG index.

Runtime data is intentionally ignored by git:

- `data/`
- `logs/`
- `vector_db/`
- `watched_folder/`
- `.venv/`

Use `config.example.yaml` as a template for local `config.yaml`.

## Working With Codex

This repository follows a simple pet-project rule: one folder is one Git repository, and meaningful changes should be recorded in Git.

Before making changes, read:

- `AGENTS.md`
- `docs/context.md`
- `docs/decisions.md`
- `docs/todo.md`

Before ending a work session, update `docs/context.md` and `docs/todo.md`, then check `git status`.

## Product Structure

```text
MeetingAgent/
  apps/                  Product surfaces: CLI, local API, desktop/web UI
  src/meeting_agent/      Future package code
  scripts/                Current operational scripts
  templates/              Prompt and document templates
  docs/                   Product, architecture, operations, security
  tests/                  Unit, integration, and evaluation tests
  data/                   Local generated data, ignored by git
  logs/                   Local logs, ignored by git
  vector_db/              Local ChromaDB, ignored by git
  watched_folder/         Incoming media/documents, ignored by git
```

## Product Principles

- Local-first: project data should stay on the user's machine by default.
- Source-grounded: every generated answer or document should cite source files and meeting fragments.
- Resumable: long-running work must continue from cache after interruption.
- Inspectable: user can see what was processed, skipped, classified, and generated.
- Project-aware: outputs should understand stages, FTT, architecture, deliverables, decisions, and tasks.

## Next Milestones

1. Finish and validate the project RAG index.
2. Add query quality checks and source citation review.
3. Create meeting-card output: video, transcript, memo, protocol, tasks, links to project docs.
4. Add document-generation briefs for Passport IS, FTT extracts, architecture notes, and protocols.
5. Build a local API and small UI for inbox, search, and generation.
