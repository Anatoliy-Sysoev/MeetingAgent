# Todo

Обновлено: 2026-06-13.

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
- [ ] MA-AUTH-DEPLOYMENT-SAFETY: safe defaults для self-hosted

## Backlog (приоритет сверху вниз)

- MA-REVIEW-QUEUE: разметка chat_runs.jsonl для eval, генерация guard_v2_cases.jsonl
- Meeting Workspace UI: страница встречи с кнопками запуска pipeline-стадий, статус job-а в реальном времени
- #39/#40 auth evolution: per-user tokens или OIDC; require_write_access() — стабильный контракт роутов, менять только внутри auth.py

## Dev Roadmap

- После Meeting Workspace UI: замкнутый цикл ingest → transcribe → diarize → merge через браузер
- После Epic #44: multi-user / публичный деплой без шаринга одного токена
