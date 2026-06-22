# Текущий Контекст

Обновлено: 2026-06-19.

## Now

- active task: DOC-REPO-CLEANUP-AFTER-AUTH-AND-MEETING-HARDENING (#59) — clean up stale docs and roadmap drift after #84–#91 hardening work
- branch: 59-doc-repo-cleanup

## Done latest (last 4 PRs)

- MA-CHAT-PROMPT-SOURCE-BOUNDARY (#90, PR #96): retrieved sources wrapped in `[BEGIN UNTRUSTED SOURCE Sn]` / `[END UNTRUSTED SOURCE Sn]` delimiters in both project chat and meeting QA prompt builders; `_SOURCE_BOUNDARY_INSTRUCTION` added before sources; `[S#]` citation format and `_cited_source_indices()` parsing unchanged; 23 injection regression tests.
- MA-MEETING-ARTIFACTS-UTF8-SUBTITLE-HARDENING (#87/#88/#89, PR #95): (87) all `.read_text()` calls in pipeline/stage tests now use `encoding="utf-8"` (Windows portability); (88) `_artifact_map()` helper with `isinstance(artifacts, dict)` guard replaces `data.get("artifacts") or {}` in MeetingsService — safely handles null/list/string/missing values; (89) SRT/VTT subtitle cue timestamps computed once as integer ms via `_seconds_to_ms()`, end clamped to `max(end_ms, start_ms + 1)` — prevents zero-duration cues.
- MA-AUTH-SECRET-STRENGTH-AND-TRUSTED-PROXY (#86/#91, PR #94): entropy-based `validate_secret_strength()` (rejects single-char repeat, block repeat, placeholder words); `load_trusted_proxy_cidrs()` + `is_trusted_proxy()` for cookie_secure=auto; X-Forwarded-Proto ignored from untrusted proxy CIDRs; deployment safety warnings for missing proxy policy; `validate_deployment_safety(config, env)` — env threaded through all sub-checks.
- MA-REPO-HARDENING-BUGFIX-PACK (#84/#85, PR #93): (84) `RequestValidationError` sanitization strips `input` field, redacts msg for sensitive locs (substring match on password/token/secret/api_key etc.); (85) search response diagnostics no longer expose `chunks_path` or other runtime fs paths; `include_diagnostics` defaults to False.

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
- citation format `[S1]`, `[S2]` … stable; `citations_basis` field = `cited` / `retrieved` / `null`

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
```

## Next

- MA-REVIEW-QUEUE: разметка chat_runs.jsonl для eval, генерация guard_v2_cases.jsonl
- Meeting-scoped Q&A v2: vector retrieval over meeting chunks (current MVP is lexical), transcript-segment-level citations
- #39/#40 auth evolution: per-user tokens or OIDC

## Open decisions / blockers

- guard_v2_cases.jsonl отсутствует (pre-existing) → regenerate via MA-REVIEW-QUEUE
- Hotwords: Vosk/live path NOT SUPPORTED; GigaAM NOT SUPPORTED
- Web UI chat sends requests without credentials → returns 401 after RBAC; use Bearer token directly until UI auth integration
- Prompt source delimiter escaping not implemented: adversarial sources could include fake delimiter strings (tracked as future improvement)
