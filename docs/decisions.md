# Decisions

## 2026-05-06 - One Folder, One Git Repository

Decision: each pet project gets its own folder and its own Git repository.

Reason:

- dependencies stay isolated;
- history stays readable;
- projects can be moved, pushed, archived, or deleted independently;
- Codex can restore context from repository files.

## 2026-05-06 - Required Project Memory Files

Decision: every pet project should keep:

- `README.md`;
- `AGENTS.md`;
- `docs/context.md`;
- `docs/decisions.md`;
- `docs/todo.md`;
- `.env.example`.

Reason:

- new threads can recover context quickly;
- decisions are not lost;
- next actions remain explicit;
- secrets and local state stay out of Git.

## 2026-05-06 - Local-First By Default

Decision: MeetingAgent processes project documents locally by default.

Reason:

- project files and meeting transcripts may be confidential;
- local Ollama and local Whisper-compatible models reduce data exposure;
- cloud integrations can be added later as explicit opt-in features.

## 2026-05-06 - Do Not Commit Runtime Data

Decision: ignore `.venv/`, `config.yaml`, `data/`, `logs/`, `vector_db/`, `watched_folder/`, and media files.

Reason:

- these files can be huge;
- they may contain confidential source documents or transcripts;
- they are machine-specific runtime state, not product source.

## 2026-05-06 - bge-m3 With num_ctx 8192

Decision: every Ollama embedding request must send `options.num_ctx=8192` and `keep_alive=24h`.

Reason:

- Ollama may default `bge-m3` to 4096 context;
- real project chunks can exceed that after tokenization;
- explicit context prevents HTTP 500 errors from context overflow.

## 2026-05-06 - Keep Embedding Cache Reusable

Decision: keep `embedding_model="bge-m3"` in cache records and do not delete valid cached embeddings during recovery.

Reason:

- cached embeddings were produced by the same model weights;
- `num_ctx` changes the accepted input length, not vectors for inputs that already fit;
- preserving cache makes multi-day builds resumable.

## 2026-05-06 - Separate chunk_id And db_id

Decision: use `chunk_id` for embedding cache reuse and `db_id` for ChromaDB record identity.

Reason:

- identical backup documents can produce identical `chunk_id`;
- ChromaDB requires unique IDs;
- adding relative path into `db_id` avoids collisions without invalidating existing embeddings cache.

## 2026-05-06 - Watchdog Restarts Ollama, Not Python

Decision: when cache growth stalls, the watchdog restarts Ollama but does not kill live `03_build_index.py`.

Reason:

- the Python worker has retry/backoff and can recover when Ollama returns;
- killing it risks unnecessary interruption;
- lock removal is safe only when no live build worker exists.

