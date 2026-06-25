# Todo

Обновлено: 2026-06-25.

## Done

- [x] MA-API-MEETINGS-RESTORE (#30): read-only Meeting API restored — GET /meetings, /{id}, /{id}/transcript, /{id}/artifacts, /{id}/artifacts/{name}
- [x] MA-JOB-API (#35): concurrency=1 job runner, 4 endpoints
- [x] MA-INGEST-DEDUP (#34): POST /meetings/ingest, sha256 dedup, auth guard
- [x] MA-ARTIFACT-SIZE-LIMITS (#52): bounded transcript/artifact text reads, configurable meetings.max_text_artifact_bytes (10 MiB default), 413 on oversize, TOCTOU-safe bounded read
- [x] DOC-API-AUTH-SETUP (#53): docs/en/API_AUTH_SETUP.md + docs/ru/API_AUTH_SETUP.md, .env.example, README auth section — original issue appears satisfied; can be closed manually after docs cleanup review

## Epic #44 MA-AUTH-FOUNDATION-MVP

- [x] MA-AUTH-CORE-1: auth domain model + SQLite persistence
- [x] MA-AUTH-LOCAL-SESSIONS (#48): Argon2id, local login, server-side sessions, /auth/me, logout
- [x] MA-AUTH-RBAC-INTEGRATION (#50): session principals, RBAC на роутах, CSRF
- [x] MA-AUTH-LOGIN-THROTTLE (#51): in-memory brute-force protection, 429+Retry-After, trusted proxy CIDR
- [x] MA-AUTH-BOOTSTRAP-ADMIN (#58): first-admin bootstrap + admin user API
- [x] MA-AUTH-DEPLOYMENT-SAFETY-V2 (#82): deployment mode (local/self_hosted), safety validator, machine token validation, cookie safety, CORS/host boundary, /admin/security/status

## Done (Meeting Workspace)

- [x] MA-MEETING-WORKSPACE (#68): workspace page, media streaming, normalized transcript segments, artifact viewer
- [x] MA-WORKSPACE-JOB-CONTROLS (#70): pipeline controls panel (start/cancel/refresh + polling), GET /auth/csrf, GET /meetings/{id}/jobs/stages
- [x] MA-MEETING-SCOPED-QA (#74): POST /meetings/{id}/search + POST /meetings/{id}/chat, MeetingQAService (lexical MVP), workspace Q&A panel
- [x] MA-PIPELINE-STAGES-EXPANSION (#76): expand runner — extract_audio/chunk/enrich/index/analyze; stage catalog sorted by order; index stage populates meeting_chunks.jsonl
- [x] MA-POST-PIPELINE-HARDENING (#78): pin product ASR model (--model large-v3-turbo); remove remaining inline on* handlers from Workspace; chat citations filtered to actually-cited [S#] with citations_basis

## Done (E2E Smoke)

- [x] MA-PIPELINE-E2E-SMOKE (#80): deterministic E2E smoke suite — chunk/enrich/index/analyze in-process; Workspace API; meeting-scoped search/chat; ASR model pin regression; DOM/CSP checks; path-safety assertions

## Done (Security & Hardening #84–#91)

- [x] MA-REPO-HARDENING-BUGFIX-PACK: validation redaction (#84) + search path leakage fix (#85) — PR #93
  - RequestValidationError sanitization: strips input, redacts sensitive field values
  - Search diagnostics no longer expose runtime fs paths; include_diagnostics defaults to False
- [x] MA-AUTH-SECRET-STRENGTH-AND-TRUSTED-PROXY (#86, #91) — PR #94
  - validate_secret_strength(): entropy check (single-char repeat, block repeat, placeholder words)
  - Trusted proxy CIDR policy: load_trusted_proxy_cidrs(), is_trusted_proxy()
  - X-Forwarded-Proto ignored from untrusted clients for cookie_secure=auto
  - Deployment safety warns on missing proxy policy; env threaded through all sub-checks
- [x] MA-MEETING-ARTIFACTS-UTF8-SUBTITLE-HARDENING (#87, #88, #89) — PR #95
  - #87: explicit encoding="utf-8" on all read_text() calls in pipeline/stage tests
  - #88: _artifact_map() with isinstance(artifacts, dict) guard — handles null/list/string/missing
  - #89: SRT/VTT cue end clamped to max(end_ms, start_ms + 1) — no zero-duration cues
- [x] MA-CHAT-PROMPT-SOURCE-BOUNDARY (#90) — PR #96
  - Retrieved sources wrapped in [BEGIN UNTRUSTED SOURCE Sn] / [END UNTRUSTED SOURCE Sn]
  - _SOURCE_BOUNDARY_INSTRUCTION added before sources in both project chat and meeting QA
  - [S#] citation format and _cited_source_indices() parsing unchanged; 23 injection regression tests

## Done (Runtime Hardening & Docs)

- [x] MA-RUNTIME-HARDENING-BUGFIX-PACK-2 (#99, PR #100): `_artifact_map()`/`_runner_media_files()` guards in runner preflights; `_source_map()`/`_media_files()` guards in MeetingsService; `_path_variants()` + re.IGNORECASE in path redaction
- [x] DOC-REPO-CLEANUP (#59, PR #97 + PR #98): context.md/todo.md compacted; code_review_2026-06-17.md added; API_AUTH_SETUP docs updated for entropy and trusted proxy findings

## Done (Review Queue & Cases Export)

- [x] MA-REVIEW-QUEUE (#36, PR #101): `ReviewQueue` + review routes + "Разметка" tab; `review.manage` permission; comment field; XSS-safe DOM; CSRF via `/auth/csrf`
- [x] MA-GUARD-V2-CASES-EXPORT (#102): `GuardCaseExporter` + `scripts/40_export_guard_v2_cases.py`; label→case mapping; no prompt_sources / no source paths; 22 tests

## Active

- [ ] (none — awaiting review of #102)

## Backlog (приоритет сверху вниз)

- run `scripts/40_export_guard_v2_cases.py` after labeling to produce guard_v2_cases.jsonl
- Meeting-scoped Q&A v2: vector retrieval over meeting chunks, transcript-segment-level citations (segment_id)
- #39/#40 auth evolution: per-user tokens или OIDC

## Dev Roadmap

- MA-PIPELINE-STAGES-EXPANSION (#76) + MA-POST-PIPELINE-HARDENING (#78) + MA-PIPELINE-E2E-SMOKE (#80) together close the loop: chunk → enrich → index → workspace search/chat confirmed in-process E2E
- Security hardening pack #84–#91 closes auth entropy, path leakage, validation redaction, UTF-8 portability, artifact type guard, subtitle duration, and prompt injection boundary
- After Epic #44 + hardening: multi-user / public deploy without sharing a single token
