# Текущий Контекст

Обновлено: 2026-06-11.

## Now

- last commit: Add auth domain and SQLite persistence (MA-AUTH-CORE-1)
- in progress: none

## Done latest

- MA-AUTH-CORE-1 (#44): provider-independent auth domain — Principal/User/LocalCredential/ExternalIdentity, central RBAC (viewer/editor/admin, unknown role grants nothing), provider registry (local+machine, yandex/google/oidc/trusted_proxy reserved), SQLite repository (idempotent schema, FK on, parameterized SQL, audit events); 40 tests; no API behavior changed
- MA-API-MEETINGS-RESTORE (#30): GET /meetings, GET /meetings/{id}, GET /meetings/{id}/transcript, GET /meetings/{id}/artifacts, GET /meetings/{id}/artifacts/{name}; read-side helpers ported into MeetingsService; 56 new tests; ingest and job API regressions pass
- MA-JOB-API (#35): POST /meetings/{id}/jobs/{stage} → 202, GET status, POST cancel, GET /jobs/active; concurrency=1 via asyncio.Lock; subprocess dry-run preflight; merge preflight without dry-run; 17 tests pass
- MA-INGEST-DEDUP (#34): POST /meetings/ingest — file upload, incremental sha256, dedup → 409, token guard via Depends(require_write_access), meeting.json creation + schema validation + rollback; hardening: path-traversal-safe filename, secrets.compare_digest, date.fromisoformat, zero-byte guard
- MA-FIX-GUARD-CASES (#32): pytest.skip(allow_module_level=True) в load_cases()
- MA-ADR-AUTH (#33): ADR 0001 MVP access control — shared/per-user token; OIDC и public links out of scope; LAN не доверенный
- MA-ASR-HOTWORDS: configs/asr_hotwords.yaml, hotwords loader/normalizer, faster-whisper >= 1.0 hotwords= param, CLI --hotwords/--hotwords-config

## Actual API surface (main)

- GET  /meetings                                  — list (offset, limit)
- GET  /meetings/{id}                             — card
- GET  /meetings/{id}/transcript                  — transcript or available:false
- GET  /meetings/{id}/artifacts                   — artifact metadata list
- GET  /meetings/{id}/artifacts/{name}            — text artifact content
- POST /meetings/ingest                           — upload + sha256 dedup [auth]
- POST /meetings/{id}/jobs/{stage}                — start pipeline job [auth]
- GET  /meetings/{id}/jobs/{job_id}               — job status [auth]
- POST /meetings/{id}/jobs/{job_id}/cancel        — cancel job [auth]
- GET  /jobs/active                               — active job or {} [auth]
- GET  /search, POST /chat, GET /health           — pre-existing

## Next

- MA-AUTH-LOCAL-SESSIONS (#44 AUTH-2): Argon2id, local login, server-side sessions, cookie, logout, /auth/me
- MA-REVIEW-QUEUE
- Meeting Workspace UI
- #39/#40 (auth evolution): require_write_access — стабильный контракт на роутах; менять backing-механизм только внутри auth.py, роуты не трогать

## Open decisions / blockers

- guard_v2_cases.jsonl отсутствует (pre-existing) → regenerate via MA-REVIEW-QUEUE (collection не падает)
- Hotwords: Vosk/live path NOT SUPPORTED
- Hotwords: GigaAM NOT SUPPORTED
- auth: require_write_access() (контракт роутов) делегирует в require_machine_token() (MVP); #39/#40 меняют только реализацию внутри auth.py
