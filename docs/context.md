# Текущий Контекст

Обновлено: 2026-06-25.

## Now

- active task: MA-GUARD-V2-REGRESSION-TESTS (#104) — loader + regression harness for guard_v2_cases.jsonl
- branch: 104-guard-v2-regression-tests

## Done latest (last 4 PRs)

- MA-GUARD-V2-REGRESSION-TESTS (#104, PR #TBD): `guard_case_loader.py` with `GuardRegressionCase` + `load_guard_cases()` + `case_contains_forbidden_keys()`; committed sample fixture (7 labels, no private data); fixture + runtime regression tests (41 tests, 6 skipped when runtime file absent).
- MA-GUARD-V2-CASES-EXPORT (#102, PR #103): `GuardCaseExporter`; `scripts/40_export_guard_v2_cases.py`; atomic write; accurate `skipped_unlabeled`; 24 tests.
- MA-REVIEW-QUEUE (#36, PR #101): `ReviewQueue` + `routes_review.py`; review.manage permission; "Разметка" tab UI; set_label API with CSRF; comment field; XSS-safe DOM rendering; bounded reads.
- MA-RUNTIME-HARDENING-BUGFIX-PACK-2 (#99, PR #100): `_artifact_map()` + `_runner_media_files()` guards in all 6 runner preflights; `_source_map()` + `_media_files()` guards in MeetingsService (_summary/list_media/get_media_path/find_by_sha256); `_path_variants()` + `re.IGNORECASE` in `_redact_paths()` — covers native/posix/backslash/case variants; 16 new tests.
- DOC-CODE-REVIEW-REPORT (PR #98, closes #59 partial): `docs/architecture/code_review_2026-06-17.md` created — historical review snapshot, resolution table (H1/H2 + M findings mapped to #84–#91), 4 remaining open LOW findings listed.
- DOC-REPO-CLEANUP (PR #97, #59): compact context.md/todo.md; TECHNICAL_FILE_RELATIONSHIPS.md updated (06→22_transcribe_meeting.py); API_AUTH_SETUP docs updated (machine_token_weak entropy, trusted_proxy rows).
- MA-CHAT-PROMPT-SOURCE-BOUNDARY (#90, PR #96): retrieved sources wrapped in `[BEGIN UNTRUSTED SOURCE Sn]` / `[END UNTRUSTED SOURCE Sn]` in both project chat and meeting QA; 23 injection regression tests.

## Current main state

### Auth / security
- machine Bearer token (`MEETINGAGENT_API_TOKEN`) is primary for script/service access; invalid Bearer raises 401 with no cookie fallback
- local cookie sessions for browser (Argon2id, HttpOnly SameSite=Lax, server-side SQLite sessions)
- CSRF required for cookie callers on all state-changing routes; Bearer callers exempt
- RBAC: viewer / editor / admin; unknown role grants nothing
- `POST /admin/bootstrap` — first-admin creation, loopback-only by default; `MEETINGAGENT_BOOTSTRAP_ALLOW_REMOTE` + strong `MEETINGAGENT_BOOTSTRAP_SECRET` to opt in
- deployment safety validator runs on startup in self_hosted mode
- `MEETINGAGENT_API_TOKEN` must be high-entropy (≥ 32 chars, not a placeholder/repeated pattern)
- `MEETINGAGENT_TRUSTED_PROXY_CIDRS` — CIDRs trusted for X-Forwarded-Proto; proto forwarded from other clients is ignored for cookie_secure=auto
- validation errors are sanitized (no raw input, sensitive field values redacted)
- search responses do not expose runtime filesystem paths

### Chat / retrieval
- `POST /search` protected by `search.use`
- `POST /chat` protected by `chat.use` + CSRF for cookie callers
- project chat and meeting QA prompts wrap retrieved sources in explicit untrusted source delimiters
- fake delimiter strings inside retrieved content are neutralized (#108): `core/prompt_safety.neutralize_source_delimiters()` rewrites case/whitespace/newline-obfuscated `[BEGIN|END UNTRUSTED SOURCE ...]` to an inert marker before wrapping
- citation format `[S1]`, `[S2]` … stable; `citations_basis` field = `cited` / `retrieved` / `null`
- Web UI chat auth integrated (#107): login panel (`POST /auth/local/login`), auth badge (`GET /auth/me`), CSRF via `GET /auth/csrf` + `X-CSRF-Token` on `POST /chat`; friendly 401/403 message; no web storage, no inline handlers

### Meeting pipeline
- canonical offline ASR: `scripts/22_transcribe_meeting.py` with `--engine faster-whisper --model large-v3-turbo`
- `scripts/06_transcribe_meeting.py` is a compatibility wrapper only
- full pipeline stages available via job runner: extract_audio → transcribe → diarize → merge → chunk → enrich → index → analyze
- meeting artifacts field in meeting.json tolerates null/list/string/missing — normalized to `{}`
- SRT/VTT exports enforce positive cue duration (≥ 1 ms)
- Meeting Workspace UI at `GET /meetings/{id}/workspace`
- `POST /meetings/{id}/search` (search.use) and `POST /meetings/{id}/chat` (chat.use + CSRF) — meeting-scoped lexical retrieval + grounded Q&A

## API surface (main)

```text
GET  /meetings                         list meetings
GET  /meetings/{id}                    meeting card
GET  /meetings/{id}/transcript         transcript or available:false
GET  /meetings/{id}/artifacts          artifact metadata list
GET  /meetings/{id}/artifacts/{name}   text artifact content (bounded read)
GET  /meetings/{id}/transcript/segments normalized segments [transcripts.read]
GET  /meetings/{id}/media              media metadata [meetings.read]
GET  /meetings/{id}/media/{media_id}   stream media Range [meetings.read]
GET  /meetings/{id}/workspace          Meeting Workspace UI
POST /meetings/{id}/search             meeting-scoped search [search.use]
POST /meetings/{id}/chat               meeting-scoped Q&A [chat.use + CSRF cookie]
GET  /meetings/{id}/jobs/stages        runnable stages [jobs.read]
POST /meetings/{id}/jobs/{stage}       start job [jobs.start + CSRF cookie]
GET  /meetings/{id}/jobs/{job_id}      job status [jobs.read]
POST /meetings/{id}/jobs/{job_id}/cancel cancel job [jobs.cancel + CSRF cookie]
GET  /jobs/active                      active job or {} [jobs.read]
POST /meetings/ingest                  upload + sha256 dedup [write]
POST /search                           project corpus search [search.use]
POST /chat                             project grounded Q&A [chat.use + CSRF cookie]
GET  /health                           health check
POST /auth/local/login                 login → session cookie
GET  /auth/me                          identity + roles [cookie]
GET  /auth/csrf                        CSRF token for current session [cookie]
POST /auth/logout                      revoke session [CSRF cookie]
POST /admin/bootstrap                  create first admin [no auth, loopback only]
GET  /admin/users                      list users [users.manage]
GET  /admin/users/{id}                 get user [users.manage]
POST /admin/users                      create user [users.manage + CSRF]
PATCH /admin/users/{id}                update user [users.manage + CSRF]
POST /admin/users/{id}/disable         disable user [users.manage + CSRF]
POST /admin/users/{id}/enable          enable user [users.manage + CSRF]
GET  /admin/security/status            deployment safety status [admin]
GET  /admin/review/chat-runs           list chat runs with labels [review.manage]
POST /admin/review/chat-runs/{id}/label set label for run [review.manage + CSRF]
GET  /admin/review/chat-runs/export    export joined runs+labels [review.manage]
```

### Review queue
- `data/asu_june_bot/chat_runs.jsonl` — original log, never modified
- `data/asu_june_bot/chat_run_labels.jsonl` — append-only sidecar; latest record per run_id wins
- valid labels: `correct`, `false_refuse`, `false_clarify`, `bad_source`, `needs_case`, `off_topic_ok`, `needs_review`
- `prompt_sources` and source `.path` fields are stripped from all API responses (no prompt internals or filesystem paths)
- `review.manage` permission assigned to admin role; machine tokens blocked on review routes
- UI "Разметка" tab at `GET /` or `GET /ui` (admin session required)

### Guard v2 cases export
- `src/asu_june_bot/evals/guard_cases.py` — `GuardCaseExporter`; reads `chat_runs.jsonl` + sidecar; never mutates either file
- `scripts/40_export_guard_v2_cases.py` — CLI: `--runs`, `--labels`, `--out`, `--include-correct`, `--limit N`, `--label LABEL`, `--dry-run`
- Label mapping: `false_refuse`/`false_clarify` → `expected_guard_decision=allow`; `bad_source`/`correct` → observed decision; `needs_case`/`needs_review`/`off_topic_ok` → null + `needs_manual_expected=True`
- `correct` excluded by default; opt in with `--include-correct`
- No `prompt_sources`, no source `.path` in output; bounded reads (10 MiB) on both input files

### Guard v2 regression harness
- `src/asu_june_bot/evals/guard_case_loader.py` — `GuardRegressionCase` dataclass; `load_guard_cases(path, *, strict=True)`; `validate_guard_case_payload()`; `case_contains_forbidden_keys()`
- `tests/fixtures/evals/guard_v2_cases.sample.jsonl` — committed sample: 7 rows, all labels, no private data, no filesystem paths
- `tests/asu_june_bot/evals/test_guard_case_loader.py` — unit tests for loader
- `tests/asu_june_bot/evals/test_guard_v2_regression_cases.py` — fixture regression always runs; runtime `data/asu_june_bot/guard_v2_cases.jsonl` tests skip if file absent
- guard v2 runtime behavior is NOT implemented; no LLM/network calls in tests

## Next

- run `scripts/40_export_guard_v2_cases.py` after labeling; runtime tests pick it up automatically
- deterministic guard assertion layer (requires pure guard API — tracked as future task)
- Meeting-scoped Q&A v2: vector retrieval over meeting chunks (current MVP is lexical), transcript-segment-level citations
- #39/#40 auth evolution: per-user tokens or OIDC

## Open decisions / blockers

- guard_v2_cases.jsonl отсутствует — generate via `scripts/40_export_guard_v2_cases.py` after labeling
- Hotwords: Vosk/live path NOT SUPPORTED; GigaAM NOT SUPPORTED
