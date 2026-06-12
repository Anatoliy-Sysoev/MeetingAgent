# Текущий Контекст

Обновлено: 2026-06-12.

## Now

- last commit: Document API and auth setup (DOC-API-AUTH-SETUP #53)
- in progress: DOC-API-AUTH-SETUP (#53)
- #52 merged at ef5a2a44

## Done latest

- DOC-API-AUTH-SETUP (#53): docs/en/API_AUTH_SETUP.md + docs/ru/API_AUTH_SETUP.md — полный справочник API и auth: MEETINGAGENT_API_TOKEN, machine/browser principals, cookie-сессия, RBAC viewer/editor/admin, CSRF, все эндпоинты (meetings, ingest, jobs, search, chat), HTTP-коды (401/403/409/413/415/422/429), лимит 10 МиБ, login throttle, HTTPS/reverse proxy, безопасное хранение. .env.example обновлён (MEETINGAGENT_API_TOKEN). README.md и README.ru.md — добавлен раздел Authentication и ссылки. Явно задокументированы отсутствующие функции: bootstrap admin, admin API/UI, Yandex/Google/OIDC, публичная регистрация.
- MA-ARTIFACT-SIZE-LIMITS (#52): text transcript/artifact reads bounded by configurable bytes (meetings.max_text_artifact_bytes, default 10 MiB). parse_max_text_artifact_bytes() strict startup validation (positive int only; reject bool/zero/negative/float/string/non-mapping meetings; no silent default fallback). MeetingsService gains immutable max_text_artifact_bytes; single _read_text_bounded() helper used by get_transcript + get_artifact_content: stat() pre-check then bounded binary read of max+1 bytes (closes TOCTOU/stale-stat), decode only after, never partial. No Path.read_text() for content endpoints. ArtifactTooLargeError(artifact, size_bytes, max_bytes) — no path/content in public fields. Routes map it to 413 with structured detail {error, artifact, size_bytes, max_bytes}; no path/content/traceback. Oversized canonical transcript candidate raises immediately (not skipped for smaller fallback); size error wins over JSON/JSONL parse error. Preserved: 404, 415 binary, RBAC (auth before content), traversal + suffix allowlist. Streaming/pagination/range remain out of scope. 32 new tests
- MA-AUTH-LOGIN-THROTTLE (#51): bounded in-memory brute-force protection — LoginThrottle (LRU + stale-purge, threading.Lock, injectable monotonic clock), key=sha256(email)+client_ip; threshold-reaching failure itself returns 429 + Retry-After (not the next request); body "Too many login attempts"; block cleared on success; safe X-Forwarded-For resolved right-to-left skipping trusted_proxy_cidrs, returns canonical IP, never trusts client-prepended hops; auth.login.throttled audit event (email only, no password/session/CSRF); LoginRequest bounded (email 1..320, password 1..1024); disabled mode via NoOpLoginThrottle; strict startup validation (bool enabled, positive ints, no bool-as-int, max_entries>=max_failures, invalid CIDR→ValueError). Config: auth.login_throttle.{enabled, max_failures, window_seconds, block_seconds=900, max_entries=10000, trusted_proxy_cidrs}; 37 tests
- MA-AUTH-RBAC-INTEGRATION (#50): provider-independent auth deps in api/auth.py — get_optional_principal (Bearer→machine / cookie→user, invalid Bearer raises 401 no fallback), require_user, require_permission(perm), require_role(role), require_write_access (machine+editor+admin, viewer 403, no auth 401, CSRF guard for cookie requests); CSRF per-session hash in auth_sessions (idempotent ALTER); raw token returned in login response + non-HttpOnly cookie; X-CSRF-Token header required for browser write requests, exempt for Bearer; MACHINE_PERMISSIONS centrally defined (no users/roles/settings/delete); read routes (meetings, search, chat) require permission; job status routes use jobs.read (добавлен в viewer, наследуется editor/admin); write routes use require_write_access returning Principal; /chat — action route через require_action_permission (permission + CSRF для cookie, Bearer exempt); malformed/non-Bearer Authorization → 401 без fallback; logout требует session-bound CSRF; all existing tests adapted, 35 RBAC/CSRF tests; 403 pass
- MA-AUTH-LOCAL-SESSIONS (#48): Argon2id password hashing (argon2-cffi), auth_sessions в SQLite (хранится sha256 токена, не сам токен), opaque HttpOnly SameSite=Lax cookie `ma_session` (Secure при https), POST /auth/local/login, GET /auth/me, POST /auth/logout; generic 401 (email не раскрывается), disabled user отклоняется, expiration/revocation, audit login/logout/failure, dummy_verify против timing-атак; AuthRepository+LocalAuthService в AppState; require_write_access не тронут
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
- POST /auth/local/login                          — login → session cookie
- GET  /auth/me                                   — identity + roles [cookie]
- POST /auth/logout                               — revoke session + clear cookie
- POST /meetings/ingest                           — upload + sha256 dedup [auth]
- POST /meetings/{id}/jobs/{stage}                — start pipeline job [auth]
- GET  /meetings/{id}/jobs/{job_id}               — job status [auth]
- POST /meetings/{id}/jobs/{job_id}/cancel        — cancel job [auth]
- GET  /jobs/active                               — active job or {} [auth]
- GET  /search, POST /chat, GET /health           — pre-existing

## Next

- MA-AUTH-BOOTSTRAP-ADMIN: first-admin bootstrap + admin user API
- MA-REVIEW-QUEUE
- Meeting Workspace UI
- #39/#40 (auth evolution): require_write_access — стабильный контракт на роутах; менять backing-механизм только внутри auth.py, роуты не трогать

## Open decisions / blockers

- guard_v2_cases.jsonl отсутствует (pre-existing) → regenerate via MA-REVIEW-QUEUE (collection не падает)
- Hotwords: Vosk/live path NOT SUPPORTED
- Hotwords: GigaAM NOT SUPPORTED
- auth: require_write_access() принимает Bearer machine token и cookie+CSRF browser principal; контракт стабилен; #39/#40 меняют только реализацию внутри auth.py
