# Project Context

Last updated: 2026-05-06.

## Current State

MeetingAgent is now a private GitHub-backed pet project and local product repository.

Repository:

- Local path: `%USERPROFILE%\Desktop\AI\MeetingAgent`
- Remote: `https://github.com/Anatoliy-Sysoev/MeetingAgent`
- Visibility: private
- Branch: `main`

The current product direction is a local-first project memory agent:

- RAG over project documentation;
- meeting transcription;
- memo and protocol generation;
- project-stage, FTT, task, and document classification;
- document generation from cited project sources.

## Runtime Status

The long RAG build is running locally and must not be interrupted without a reason.

Known runtime facts:

- `run_full_rag.ps1` starts the full build.
- `scripts/03_build_index.py` is the long embedding/indexing step.
- `data/embeddings_cache.jsonl` is the resumable embedding cache.
- `monitor_rag.ps1` is the watchdog tick.
- Runtime folders are ignored by Git.

## Important Files

- `README.md`: product overview and run notes.
- `AGENTS.md`: instructions for Codex/AI work.
- `docs/context.md`: current state of the project.
- `docs/decisions.md`: why key decisions were made.
- `docs/todo.md`: next steps.
- `.env.example`: safe example environment variables.
- `config.example.yaml`: safe example local config.
- `scripts/03_build_index.py`: RAG embedding/indexing worker.
- `monitor_rag.ps1`: watchdog for long-running RAG build.

## What Changed Recently

- Product repository structure was created.
- Private GitHub repository was created and pushed.
- Runtime data was excluded from Git.
- Watchdog was hardened around Ollama and live Python build processes.
- `scripts/03_build_index.py` now separates reusable `chunk_id` from Chroma `db_id` so duplicate backup documents do not collide in ChromaDB while embeddings cache remains reusable.
- Standard pet-project files were added: `AGENTS.md`, `docs/context.md`, `docs/decisions.md`, `docs/todo.md`, and `.env.example`.

## What Remains

- Finish current RAG build.
- Validate ChromaDB collection count and smoke queries.
- Improve query output with source citations.
- Add incremental RAG update flow.
- Build the first meeting processing pipeline.

## Restore Context In New Thread

Use this prompt:

```text
Read README.md, AGENTS.md, docs/context.md, docs/todo.md and git log --oneline -10. Restore project context and propose the next step.
```

