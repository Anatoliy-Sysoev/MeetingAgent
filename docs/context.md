# Текущий Контекст

Обновлено: 2026-06-11.

## Now

- last commit: fix CI — add python-multipart to requirements.txt
- in progress: none

## Done latest

- MA-JOB-API (#35): POST /meetings/{id}/jobs/{stage} → 202, GET status, POST cancel, GET /jobs/active; concurrency=1 via asyncio.Lock; subprocess dry-run preflight; merge preflight without dry-run; 17 tests pass
- MA-INGEST-DEDUP (#34): POST /meetings/ingest — file upload, incremental sha256, dedup → 409, token guard via Depends(require_write_access), meeting.json creation + schema validation + rollback; hardening: path-traversal-safe filename, secrets.compare_digest, date.fromisoformat, zero-byte guard
- MA-FIX-GUARD-CASES (#32): pytest.skip(allow_module_level=True) в load_cases()
- MA-ADR-AUTH (#33): ADR 0001 MVP access control — shared/per-user token; OIDC и public links out of scope; LAN не доверенный
- MA-ASR-HOTWORDS: configs/asr_hotwords.yaml, hotwords loader/normalizer, faster-whisper >= 1.0 hotwords= param, CLI --hotwords/--hotwords-config

## Actual API surface (main)

- POST /meetings/ingest
- POST /meetings/{id}/jobs/{stage}
- GET  /meetings/{id}/jobs/{job_id}
- POST /meetings/{id}/jobs/{job_id}/cancel
- GET  /jobs/active
- GET  /search, POST /chat, GET /health (pre-existing)

## Next

- MA-API-MEETINGS: read-only Meeting API (GET /meetings, GET /meetings/{id}, GET /meetings/{id}/transcript) — не смержен, код не существует
- MA-REVIEW-QUEUE
- #39/#40 (auth evolution): require_write_access — стабильный контракт на роутах; менять backing-механизм только внутри auth.py, роуты не трогать

## Open decisions / blockers

- guard_v2_cases.jsonl отсутствует (pre-existing) → regenerate via MA-REVIEW-QUEUE (collection не падает)
- Hotwords: Vosk/live path NOT SUPPORTED
- Hotwords: GigaAM NOT SUPPORTED
- auth: require_write_access() (контракт роутов) делегирует в require_machine_token() (MVP); #39/#40 меняют только реализацию внутри auth.py
