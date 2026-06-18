# Todo

Обновлено: 2026-06-16 (E2E smoke).

## Done

- [x] MA-API-MEETINGS-RESTORE (#30): read-only Meeting API restored — GET /meetings, /{id}, /{id}/transcript, /{id}/artifacts, /{id}/artifacts/{name} — `9de28301`
- [x] MA-JOB-API (#35): concurrency=1 job runner, 4 endpoints
- [x] MA-INGEST-DEDUP (#34): POST /meetings/ingest, sha256 dedup, auth guard
- [x] MA-ARTIFACT-SIZE-LIMITS (#52): bounded transcript/artifact text reads, configurable meetings.max_text_artifact_bytes (10 MiB default), 413 on oversize, TOCTOU-safe bounded read
- [x] DOC-API-AUTH-SETUP (#53): docs/en/API_AUTH_SETUP.md + docs/ru/API_AUTH_SETUP.md, .env.example обновлён, README.md + README.ru.md — раздел Authentication

## Epic #44 MA-AUTH-FOUNDATION-MVP

- [x] MA-AUTH-CORE-1: auth domain model + SQLite persistence (no API changes)
- [x] MA-AUTH-LOCAL-SESSIONS (#48): Argon2id, local login, server-side sessions, /auth/me, logout
- [x] MA-AUTH-RBAC-INTEGRATION (#50): session principals, RBAC на роутах, CSRF
- [x] MA-AUTH-LOGIN-THROTTLE (#51): in-memory brute-force protection, 429+Retry-After, trusted proxy CIDR — merged `567f043a`
- [x] MA-AUTH-BOOTSTRAP-ADMIN (#58): first-admin bootstrap + admin user API — `04b7af4`
- [x] MA-AUTH-DEPLOYMENT-SAFETY-V2 (#82): deployment mode (local/self_hosted), safety validator, machine token validation, cookie safety checks, CORS/host boundary, admin `/admin/security/status`, docs

## Done (Meeting Workspace)

- [x] MA-MEETING-WORKSPACE (#68, PR #69): workspace page, media streaming, normalized transcript segments, artifact viewer, read-only status
- [x] MA-WORKSPACE-JOB-CONTROLS (#70): pipeline controls panel (start/cancel/refresh + polling), `GET /auth/csrf`, `GET /meetings/{id}/jobs/stages`, CSRF-safe browser actions
- [x] MA-MEETING-SCOPED-QA (#74, PR #75): `POST /meetings/{id}/search` + `POST /meetings/{id}/chat`, self-contained `MeetingQAService` (lexical MVP over meeting_chunks.jsonl, strict meeting scoping, no project/global leakage), workspace Q&A panel (answer/citations/search, seek-on-click)
- [x] MA-PIPELINE-STAGES-EXPANSION (#76): expand runner beyond transcribe/diarize/merge — add extract_audio, chunk, enrich, index, analyze; stage catalog sorted by order; static preflight checks per stage; `index` stage populates data/meeting_chunks.jsonl enabling workspace Q&A
- [x] MA-POST-PIPELINE-HARDENING (#78): pin product ASR model (`--model large-v3-turbo`) for UI-launched transcribe (no silent `small` fallback); remove remaining inline `on*` handlers from Workspace (header refresh, transcript filter, close-artifact, transcript segment seek → `dataset`+`addEventListener`); chat citations filtered to actually-cited `[S#]` with `citations_basis` (`cited`/`retrieved`/`null`)

## Done (E2E Smoke)

- [x] MA-PIPELINE-E2E-SMOKE (#80): deterministic E2E smoke suite — chunk → enrich → index → analyze in-process; Workspace API; meeting-scoped search/chat; ASR model pin regression; DOM/CSP checks; path-safety assertions

- [x] MA-AUTH-SECRET-STRENGTH-AND-TRUSTED-PROXY (#86, #91): entropy-based secret validation (single-char repeat, block repeat, placeholder); trusted proxy CIDR policy for cookie_secure=auto; X-Forwarded-Proto ignored from untrusted clients; deployment safety warnings for missing proxy policy; /admin/security/status trusted_proxy_policy field

## Backlog (приоритет сверху вниз)
- MA-REVIEW-QUEUE: разметка chat_runs.jsonl для eval, генерация guard_v2_cases.jsonl
- Meeting-scoped Q&A v2: vector retrieval over meeting chunks (current MVP is lexical), transcript-segment-level citations (`segment_id`)
- #39/#40 auth evolution: per-user tokens или OIDC; require_write_access() — стабильный контракт роутов, менять только внутри auth.py

## Dev Roadmap

- MA-PIPELINE-STAGES-EXPANSION (#76) + MA-POST-PIPELINE-HARDENING (#78) + MA-PIPELINE-E2E-SMOKE (#80) вместе замыкают цикл: chunk → enrich → index → workspace search/chat подтверждён in-process E2E тестами
- После Epic #44: multi-user / публичный деплой без шаринга одного токена
