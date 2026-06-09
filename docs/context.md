# Текущий Контекст

Обновлено: 2026-06-09.

## Now

- last commit: fix — security and validation hardening (MA-INGEST-DEDUP)
- in progress: none

## Done latest

- MA-INGEST-DEDUP (#34): POST /meetings/ingest — file upload, incremental sha256, dedup → 409, token guard via Depends(require_write_access), meeting.json creation + schema validation + rollback; hardening: path-traversal-safe filename, secrets.compare_digest, date.fromisoformat, zero-byte guard
- MA-FIX-GUARD-CASES (#32): pytest.skip(allow_module_level=True) в load_cases()
- MA-ADR-AUTH (#33): ADR 0001 MVP access control — shared/per-user token; OIDC и public links out of scope; LAN не доверенный
- MA-ASR-HOTWORDS: configs/asr_hotwords.yaml, hotwords loader/normalizer, faster-whisper >= 1.0 hotwords= param, CLI --hotwords/--hotwords-config
- MA-API-MEETINGS: read-only Meeting API, MeetingCardError → 422 на всех 4 роутах, allowlist суффиксов, ISO-8601 modified_at

## Next

- MA-JOB-API (#35): enforce token check через Depends(require_write_access) из api/auth.py
- MA-REVIEW-QUEUE
- #39/#40 (auth evolution): require_write_access — стабильный контракт на роутах; менять backing-механизм только внутри auth.py, роуты не трогать

## Open decisions / blockers

- guard_v2_cases.jsonl отсутствует (pre-existing) → regenerate via MA-REVIEW-QUEUE (collection не падает)
- Hotwords: Vosk/live path NOT SUPPORTED
- Hotwords: GigaAM NOT SUPPORTED
- auth: require_write_access() (контракт роутов) делегирует в require_machine_token() (MVP); #39/#40 меняют только реализацию внутри auth.py
