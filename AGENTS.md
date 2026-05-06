# Agent Instructions

## Startup Context

- Read `README.md`, `AGENTS.md`, `docs/context.md`, and `docs/todo.md` before making changes.
- Review `git log --oneline -10` when restoring context in a new thread.
- Treat one folder as one pet project and one Git repository.

## Git Discipline

- Always record meaningful project changes in Git.
- Prefer small commits with clear messages.
- Inspect `git status --short` before editing and before finishing.
- Do not overwrite or revert user changes unless explicitly asked.
- Do not commit secrets, `.env` files, local configs, build artifacts, `node_modules`, `.venv`, `venv`, `dist`, local IDE settings, runtime logs, vector databases, media files, or generated project data.
- Before finishing a work session, update `docs/context.md` with what changed and what remains.
- Keep `docs/todo.md` current with the next actionable steps.
- At the end of the work session, show or summarize `git status`.

## MeetingAgent-Specific Rules

- Keep the product local-first by default.
- Do not commit `config.yaml`, `data/`, `logs/`, `vector_db/`, `watched_folder/`, or `.venv/`.
- Every Ollama `/api/embeddings` call must include `options.num_ctx=8192`.
- Keep embedding model records as `bge-m3` unless the user explicitly migrates the cache.
- Preserve resumability: do not delete `data/embeddings_cache.jsonl` during recovery.
- Watchdog may restart Ollama, but must not kill a live `03_build_index.py` process.
- Prefer product documents and small implementation steps over large rewrites.

## End-Of-Day Routine

When the user asks to wrap up, do this:

1. Update `docs/context.md`.
2. Update `docs/todo.md`.
3. Run `git status --short`.
4. Commit and push if the changes are ready and safe.

