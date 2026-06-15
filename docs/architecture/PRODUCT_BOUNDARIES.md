# Product Boundaries: MeetingAgent and Project Knowledge Bot

Updated: 2026-06-15.

This document defines the intended product split between **MeetingAgent Core** and **Project Knowledge Bot**, classifies current files by ownership, and provides a phased migration plan. No code moves are performed in this task.

---

## A. Current State

### Package Layout

```
src/
├── asu_june_bot/          # ACTIVE — all production runtime currently lives here
│   ├── api/               # FastAPI app + all routes
│   ├── auth/              # RBAC, sessions, throttle, audit
│   ├── chat/              # Grounded answer generation
│   ├── core/              # Config, hashing, JSONL, limits, path filters
│   ├── eval/              # Evaluation framework
│   ├── guardrails/        # Scope classification, project guard, output policy
│   ├── health/            # Health check service
│   ├── ingestion/         # Project/corpus document ingestion models and utils
│   ├── jobs/              # Async job runner (transcription, diarization, …)
│   ├── llm/               # LLM client abstractions (Ollama OpenAI-compat)
│   ├── meetings/          # Meeting card service
│   ├── observability/     # Chat run logging
│   ├── qh/                # Quality/health release gate
│   ├── retrieval/         # RAG: BM25 + vector + hybrid + re-ranking
│   ├── search/            # Search service and FTT stage routing
│   └── telegram_bot.py    # Telegram adapter
└── meeting_agent/         # SCAFFOLD — future MeetingAgent Core package
    ├── transcription/     # ACTIVE: faster-whisper, gigaam, glossary
    ├── diarization/       # ACTIVE: sherpa backend, speaker assignment
    ├── live_transcription/# ACTIVE: real-time VAD + export
    └── <rest>             # PLACEHOLDER: .gitkeep only (api/, config/, rag/, …)
```

### Why `asu_june_bot` Is Both Products at Once

The `asu_june_bot` package started as the Project Knowledge Bot runtime, but over time it became the accidental holder of three distinct concerns:

1. **Project Knowledge Bot product code** — search, chat, retrieval, guardrails, Telegram, corpus switching, bot-specific eval. This is legitimately owned by the bot.

2. **MeetingAgent Core infrastructure** — meeting ingestion, job pipeline orchestration, meeting card service, meeting REST API routes (`/meetings`, `/meetings/ingest`, `/meetings/{id}/jobs/*`). These belong to MeetingAgent and ended up in the bot package because both products share the same FastAPI process.

3. **Shared/common utilities** — config loading (`core/config.py`), JSONL helpers (`core/jsonl.py`), hashing/IDs (`core/hashing.py`), size/schema limits (`core/limits.py`), LLM client abstraction (`llm/`), auth/security layer (`auth/`). These are infrastructure consumed by both products and belong in neither product alone.

The `meeting_agent/` package exists as a structural scaffold intended to receive MeetingAgent Core code, but most of its directories are empty placeholders today. The transcription, diarization, and live transcription modules are active there already.

---

## B. Target Product Split

### MeetingAgent Core API

Owns all meeting lifecycle and administration endpoints:

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | Service health |
| POST | `/auth/local/login` | Session auth |
| GET | `/auth/me` | Identity |
| POST | `/auth/logout` | Session revocation |
| POST | `/admin/bootstrap` | First admin creation |
| GET/POST/PATCH | `/admin/users/*` | User management |
| GET | `/meetings` | List meetings |
| GET | `/meetings/{id}` | Meeting card |
| GET | `/meetings/{id}/transcript` | Transcript |
| GET | `/meetings/{id}/artifacts` | Artifact list |
| GET | `/meetings/{id}/artifacts/{name}` | Artifact content |
| POST | `/meetings/ingest` | Upload + dedup |
| POST | `/meetings/{id}/jobs/{stage}` | Start pipeline job |
| GET | `/meetings/{id}/jobs/{job_id}` | Job status |
| POST | `/meetings/{id}/jobs/{job_id}/cancel` | Cancel job |
| GET | `/jobs/active` | Active job |
| — | Meeting Workspace UI | Future |

### Project Knowledge Bot API

Owns all search, chat, and corpus endpoints:

| Method | Path | Notes |
|---|---|---|
| POST | `/search` | RAG retrieval + source refs |
| POST | `/chat` | Grounded answer with citations |
| GET | `/sources` | Available corpora (future) |
| — | Bot UI | Future |
| — | Telegram adapter | Currently `telegram_bot.py` |
| — | Corpus health/search diagnostics | Currently `scripts/asu_june_bot_health_v2.py` |

### Shared/Common Layer

Utilities consumed by both products. No dedicated process or public API — distributed as an internal package:

- Config loading and YAML parsing
- JSONL read/write helpers
- Hashing (SHA-256, IDs)
- LLM client interface and Ollama adapters
- Schema/size limits
- Auth/security contracts (Principal, permissions, RBAC definitions, session models)
- Logging/audit primitives shared across products

---

## C. File Ownership Matrix

### Ownership Categories

| Symbol | Meaning |
|---|---|
| **MA** | MeetingAgent Core |
| **PKB** | Project Knowledge Bot |
| **SH** | Shared/Common |
| **BR** | Compatibility/Bridge (temporary, to be removed after split) |
| **?** | Undecided — needs later decision |

### `src/asu_june_bot/`

| Path | Owner | Notes |
|---|---|---|
| `api/app.py` | BR | Creates single FastAPI app for both products; split in Phase 2/3 |
| `api/auth.py` | SH | Auth dependencies used by both products' routes |
| `api/bootstrap_policy.py` | SH | Bootstrap safety policy — security primitive |
| `api/dependencies.py` | BR | Wires AppState including both MA and PKB services |
| `api/errors.py` | SH | Shared HTTP error helpers |
| `api/middleware.py` | SH | Logging/request middleware (shared concern) |
| `api/routes_admin.py` | MA | User management — belongs to MeetingAgent platform |
| `api/routes_auth.py` | MA | Session auth — belongs to MeetingAgent platform |
| `api/routes_chat.py` | PKB | Chat endpoint |
| `api/routes_health.py` | BR | Single-process compatibility endpoint; currently delegates to PKB-specific health service |
| `api/routes_ingest.py` | MA | Meeting ingest |
| `api/routes_jobs.py` | MA | Job pipeline |
| `api/routes_meetings.py` | MA | Meeting reads |
| `api/routes_search.py` | PKB | Search endpoint |
| `api/routes_ui.py` | PKB | Bot UI route |
| `auth/` (entire directory) | SH | Auth domain model, RBAC, sessions, throttle — shared security primitive, not bot-only |
| `chat/` (entire directory) | PKB | Grounded answer generation, prompt builder, validators |
| `core/config.py` | SH | Config loading shared by both products |
| `core/corpus.py` | PKB | Corpus switching — bot concern |
| `core/hashing.py` | SH | SHA-256 / ID generation utilities |
| `core/jsonl.py` | SH | JSONL read/write helpers |
| `core/limits.py` | SH | Schema/size limit constants and parsers |
| `core/path_filters.py` | SH | File exclusion patterns (used by corpus build) |
| `eval/` (entire directory) | PKB | Bot-specific eval framework and quality pipeline |
| `guardrails/` (entire directory) | PKB | Scope classifier, project guard, output policy |
| `health/service.py` | PKB | PKB-specific health: checks corpus indices, Ollama, chunks/cache |
| `ingestion/models.py` | PKB | Project/corpus document ingestion models |
| `ingestion/utils.py` | PKB | Project/corpus document ingestion utilities |
| `jobs/runner.py` | MA | Async subprocess job runner |
| `llm/client.py` | SH | LLM client interface |
| `llm/ollama_common.py` | SH | Ollama common utilities |
| `llm/ollama_openai.py` | SH | Ollama OpenAI-compat adapter |
| `meetings/service.py` | MA | Meeting card read/write service |
| `observability/chat_runs.py` | PKB | Bot chat run logging |
| `qh/release_gate.py` | PKB | Quality/health gate for bot corpus |
| `retrieval/` (entire directory) | PKB | RAG retrieval stack |
| `search/` (entire directory) | PKB | Search service and FTT routing |
| `telegram_bot.py` | PKB | Telegram adapter |

### `src/meeting_agent/`

| Path | Owner | Notes |
|---|---|---|
| `transcription/` | MA | Active: faster-whisper, gigaam, glossary, hotwords |
| `diarization/` | MA | Active: sherpa backend, speaker assignment |
| `live_transcription/` | MA | Active: real-time VAD, exporters |
| `api/` | MA | Placeholder — future MeetingAgent HTTP layer |
| `config/` | SH | Placeholder — future config module |
| `core/` | SH | Placeholder — future shared utilities |
| `ingest/` | MA | Placeholder — future ingest domain |
| `meetings/` | MA | Placeholder — future meeting domain |
| `rag/` | ? | Placeholder — decide scope (meeting search vs. bot RAG) |
| `storage/` | MA | Placeholder — future storage abstraction |
| `integrations/` | ? | Placeholder — undecided; may host PKB adapter contract |
| `classification/` | MA | Placeholder — future artifact classification |
| `document_generation/` | MA | Placeholder — future artifact generation |
| `extraction/` | MA | Placeholder — future text extraction |
| `observability/` | SH | Placeholder — future shared audit/logging |

### `scripts/`

| Pattern | Owner | Notes |
|---|---|---|
| `20_*.py` – `33_*.py` | MA | Meeting pipeline: ingest, audio, transcribe, diarize, merge, chunk, enrich, index, analyze, search |
| `asu_june_bot_*.py` | PKB | Bot corpus build, search, chat, eval, Telegram, health |
| `01_*.py` – `09_chat.py` | PKB | Legacy v1 RAG / baseline bot pipeline |
| `rag_*.py` | PKB | RAG utilities (corpus) |
| `scripts/README.md` | ? | Covers both products; should split after Phase 2 |

Specifically for the required classification:

| File | Owner |
|---|---|
| `scripts/20_ingest_meeting.py` | MA |
| `scripts/21_extract_audio.py` | MA |
| `scripts/22_transcribe_meeting.py` | MA |
| `scripts/23_diarize_meeting.py` | MA |
| `scripts/24_merge_transcript_speakers.py` | MA |
| `scripts/26_chunk_meeting.py` | MA |
| `scripts/27_enrich_meeting_chunks.py` | MA |
| `scripts/28_index_meeting_chunks.py` | MA |
| `scripts/29_analyze_meeting.py` | MA |
| `scripts/31_meeting_search.py` | MA |

---

## D. Shared Layer Proposal

The following groups should move into a shared package (recommended name: `meeting_agent/shared` or `meeting_agent/common`) during Phase 1. Do not perform the move in this task.

| Group | Current Location | What to Move |
|---|---|---|
| **Config** | `asu_june_bot/core/config.py` | YAML loading, env overrides, deep merge |
| **JSONL / file IO** | `asu_june_bot/core/jsonl.py` | `read_jsonl`, `write_jsonl`, streaming helpers |
| **Hashing / IDs** | `asu_june_bot/core/hashing.py` | `sha256_file`, `new_id` |
| **LLM client** | `asu_june_bot/llm/` | `LLMClient`, Ollama adapters, retry logic |
| **Schema / size limits** | `asu_june_bot/core/limits.py` | `parse_max_text_artifact_bytes`, limit constants |
| **Auth / security contracts** | `asu_june_bot/auth/` | `Principal`, `ROLE_PERMISSIONS`, `permissions_for_roles`, session models — shared security layer used by both products; do NOT classify as bot-only |
| **Logging / audit primitives** | `asu_june_bot/auth/repository.py` (audit events) | Audit event schema if consumed by both products post-split |

**Health note:** `asu_june_bot/health/service.py` is PKB-specific (checks corpus indices, Ollama, chunks) and should move with PKB in Phase 4. A future `meeting_agent/shared/health.py` may define a minimal shared health contract if MeetingAgent Core requires its own health checks.

**Package name constraint:** do not name this package `platform` — it conflicts conceptually with the Python standard library `platform` module. Use `meeting_agent/shared`, `meeting_agent/common`, or `meeting_agent/security` for the auth sub-group.

---

## E. Adapter Contract

After the split, MeetingAgent Core will integrate with Project Knowledge Bot over HTTP when search or chat capability is requested. This replaces the current in-process direct import.

### Minimum Viable Adapter Endpoints

| Method | Path | Direction | Description |
|---|---|---|---|
| `GET` | `/health` | MA → PKB | Liveness probe before sending queries |
| `POST` | `/search` | MA → PKB | RAG retrieval for meeting artifacts |
| `POST` | `/chat` | MA → PKB | Grounded answer generation |
| `GET` | `/sources` | MA → PKB | Available corpora (future; optional at MVP) |

### Request/Response Contract

**POST /search**
```json
{
  "query": "string",
  "corpus_id": "string | null",
  "meeting_id": "string | null",
  "top_k": 4
}
```
Response:
```json
{
  "results": [
    {
      "chunk_id": "string",
      "score": 0.0,
      "text": "string",
      "source": { "meeting_id": "string | null", "document": "string | null" }
    }
  ]
}
```

**POST /chat**
```json
{
  "query": "string",
  "corpus_id": "string | null",
  "meeting_id": "string | null"
}
```
Response:
```json
{
  "answer": "string",
  "refusal": "string | null",
  "citations": [
    { "chunk_id": "string", "source": "string", "excerpt": "string" }
  ]
}
```

### Contract Requirements

- **Auth:** PKB adapter endpoint accepts a shared secret or internal Bearer token. External users always authenticate with MeetingAgent; MA proxies requests to PKB. PKB does not expose its API directly to end users.
- **Refusal/no-answer:** PKB returns `answer: null, refusal: "<reason>"` when the query is out of scope or guardrails block the response. MA passes this through to the caller unchanged.
- **Timeout:** MA sets an explicit HTTP timeout (recommended: `timeout_sec` from config, default 180 s). On timeout, MA returns 504 to the caller.
- **Errors:** PKB 5xx → MA returns 502. PKB 4xx → MA returns the status as-is if it is meaningful to the end user, otherwise 502.
- **corpus_id / meeting_id:** Either or both may be null. PKB uses corpus_id to select the active corpus, and meeting_id to scope retrieval. Null means global/default corpus.
- **Source refs:** Citation `chunk_id` values are stable PKB identifiers. MeetingAgent Core does not interpret them.

---

## F. Migration Phases

### Phase 0 — Documentation and Ownership Map *(this task)*

**Goal:** Record product boundaries, file ownership, adapter contract, and migration plan in a single authoritative document without any code changes.

**Allowed changes:**
- `docs/architecture/PRODUCT_BOUNDARIES.md` (this file)
- Minor cross-reference updates in `docs/context.md`, `docs/todo.md`, `README.md`

**Non-goals:** Any code move, rename, or route change.

**Risks:** Low. Docs-only. If ownership decisions turn out to be wrong, the document is updated — no code to roll back.

---

### Phase 1 — Extract Shared/Common Utilities

**Goal:** Move identified shared modules into `meeting_agent/shared` (or equivalent) so both products can import from a stable internal package without depending on each other.

**Allowed changes:**
- Create `src/meeting_agent/shared/` (or `meeting_agent/common/`)
- Move `config.py`, `jsonl.py`, `hashing.py`, `limits.py`, `llm/` into shared
- Move `auth/` (security contracts) into `meeting_agent/security/` or `meeting_agent/shared/auth/`
- Update all imports in `asu_june_bot/` to use the new paths
- Update `pyproject.toml` package discovery if needed

**Non-goals:** No route changes. No product-level split. No repo split. Do not move `asu_june_bot/` itself.

**Risks:**
- Import churn — many files import from `asu_june_bot.core.*` and `asu_june_bot.auth.*`. Use `sed`/`rope` for bulk rename, verify with `python -m compileall`.
- Hidden circular imports between `auth/` and `core/config.py` must be resolved before move.
- All tests must pass after migration.

---

### Phase 2 — Move MeetingAgent Routes and Services Out of Bot Package

**Goal:** Relocate MeetingAgent-owned API routes and services (`routes_meetings.py`, `routes_ingest.py`, `routes_jobs.py`, `routes_admin.py`, `routes_auth.py`, `meetings/service.py`, `jobs/runner.py`) into `meeting_agent/` sub-packages.

Do not move current `asu_june_bot/ingestion/` in Phase 2; it is PKB corpus/document ingestion and will move with PKB in Phase 4. Future MeetingAgent meeting-ingest domain lives in `meeting_agent/ingest/`.

**Allowed changes:**
- Create `src/meeting_agent/api/routes_*.py` for MA-owned routes
- Create `src/meeting_agent/meetings/`, `src/meeting_agent/jobs/`, `src/meeting_agent/ingest/`
- Move MA route and service modules
- Keep PKB-owned routes in `asu_june_bot/api/`
- Update `api/app.py` (or split it) to include routes from both packages

**Non-goals:** Do not change any HTTP route paths. Do not move `asu_june_bot/auth/` yet (already targeted in Phase 1). No API behavior changes. No tests removed.

**Risks:**
- `api/app.py` / `api/dependencies.py` currently wire both MA and PKB services into a single `AppState`; this coupling must be untangled carefully.
- Route registration order matters in FastAPI (path matching). Preserve it.
- All existing tests must pass without modification to HTTP routes.

---

### Phase 3 — Define Bot Adapter and Optional Runtime Integration

**Goal:** Introduce a PKB adapter client in MeetingAgent Core that calls PKB over HTTP using the contract defined in Section E. Both in-process (current) and HTTP-proxy (future) modes are supported via a config flag.

**Allowed changes:**
- Create `src/meeting_agent/integrations/pkb_client.py` — HTTP adapter implementing the Section E contract
- Add `integration.mode: inprocess | http` to config schema
- In the combined single-process deployment, `/search` and `/chat` continue to be served by PKB code directly; compatibility/proxy routes in the combined app call the PKB adapter in `http` mode when `integration.mode: http`
- MeetingAgent internal workflows (e.g., meeting-scoped search) call the PKB adapter, not PKB modules directly
- Tests stub the adapter; existing behavior preserved in `inprocess` mode

**Non-goals:** Do not actually split the process yet. Do not change PKB internal logic. Do not expose the PKB adapter API to end users directly.

**Risks:**
- `inprocess` mode must remain default to avoid breaking existing deployments.
- Latency increase if `http` mode is used on the same host — document the tradeoff.
- Adapter timeout/error handling must be tested explicitly.

---

### Phase 4 — Split Project Knowledge Bot Repo/Package

**Goal:** Extract `asu_june_bot/` (PKB-owned modules: search, chat, retrieval, guardrails, corpus, eval, Telegram, observability) into a separate repository with its own release cycle.

**Allowed changes:**
- Create new repository `project-knowledge-bot`
- Move PKB modules, scripts, and docs there
- PKB exposes its own FastAPI app with the adapter endpoints from Section E
- MeetingAgent configures `integration.mode: http` and points to the PKB deployment

**Non-goals:** Do not break existing single-process deployments before this phase is complete and validated.

**Risks:**
- Network latency between MA and PKB processes (mitigate with co-deployment on same host using localhost HTTP)
- Config management across two repos; consider shared schema versioning
- CI/CD pipelines must be duplicated or split carefully
- Dependency versions may diverge; pin shared dependencies explicitly

---

### Phase 5 — Compatibility Cleanup

**Goal:** Remove bridge/compatibility shims introduced during earlier phases.

**Allowed changes:**
- Remove `inprocess` mode from the PKB adapter
- Remove deprecated import aliases
- Remove `asu_june_bot/` from the MeetingAgent repo entirely (replaced by PKB repo)
- Rename `meeting_agent/` to the final canonical package name if desired
- Clean up `scripts/`: rename `asu_june_bot_*.py` scripts into the PKB repo

**Non-goals:** No new features. No route changes.

**Risks:** Low if Phases 1–4 were executed cleanly. Main risk is undocumented internal cross-dependencies missed during earlier phases.

---

## G. Constraints

The following constraints are firm for all phases unless explicitly overridden by a separate architecture decision:

- **No immediate repo split** — both products remain in this repository until Phase 4.
- **No large file moves during Phase 0** — this document is the only change in the current task.
- **No route path changes** — all HTTP paths (`/meetings/*`, `/auth/*`, `/admin/*`, `/search`, `/chat`) remain stable across all phases.
- **No rename of `asu_june_bot` to `project_knowledge_bot`** — deferred to Phase 4 or later.
- **Auth/admin/security are not bot-only** — `auth/`, `api/routes_admin.py`, `api/routes_auth.py`, and `api/bootstrap_policy.py` are shared security infrastructure, not PKB product code. They belong in the shared layer or MeetingAgent Core, not in the bot package.
- **Ingest/jobs/meetings are MeetingAgent Core** — `routes_ingest.py`, `routes_jobs.py`, `routes_meetings.py`, `meetings/service.py`, `jobs/runner.py` belong to MA. Current `asu_june_bot/ingestion/` is PKB corpus/document ingestion, not meeting ingest; future MeetingAgent meeting-ingest domain lives at `meeting_agent/ingest/` (placeholder).
- **`/search` and `/chat` path stability** — these HTTP paths remain unchanged across all phases. During and after migration they are served by PKB code (directly in `inprocess` mode, or via compatibility/proxy routes in `http` mode); no user-visible path change occurs.
- **Search/chat/retrieval/guardrails/Telegram/corpus are Project Knowledge Bot** — `routes_search.py`, `routes_chat.py`, `chat/`, `search/`, `retrieval/`, `guardrails/`, `telegram_bot.py`, `core/corpus.py`.
- **Shared layer must not be named `platform`** — use `meeting_agent/shared`, `meeting_agent/common`, or `meeting_agent/security`.
- **Config and LLM client are shared** — `core/config.py` and `llm/` must not be owned by either product; they are shared infrastructure.
