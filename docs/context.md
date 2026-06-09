# Текущий Контекст

Обновлено: 2026-06-09.

## Now

- last commit: MA-INGEST-DEDUP — POST /meetings/ingest, sha256 dedup, require_token
- in progress: none

## Done latest

- MA-INGEST-DEDUP (#34): POST /meetings/ingest — file upload, incremental sha256, dedup → 409, token guard via Depends(require_token), meeting.json creation + schema validation + rollback
- MA-FIX-GUARD-CASES (#32): pytest.skip(allow_module_level=True) в load_cases()
- MA-ADR-AUTH (#33): ADR 0001 MVP access control — shared/per-user token; OIDC и public links out of scope; LAN не доверенный
- MA-ASR-HOTWORDS: configs/asr_hotwords.yaml, hotwords loader/normalizer, faster-whisper >= 1.0 hotwords= param, CLI --hotwords/--hotwords-config
- MA-API-MEETINGS: read-only Meeting API, MeetingCardError → 422 на всех 4 роутах, allowlist суффиксов, ISO-8601 modified_at

## Next

- MA-JOB-API (enforce token check, Depends(require_token) из auth.py)
- MA-REVIEW-QUEUE

## Open decisions / blockers

- guard_v2_cases.jsonl отсутствует (pre-existing) → regenerate via MA-REVIEW-QUEUE (collection не падает)
- Hotwords: Vosk/live path NOT SUPPORTED
- Hotwords: GigaAM NOT SUPPORTED
- require_token экспортирован из api/auth.py — переиспользовать в MA-JOB-API
