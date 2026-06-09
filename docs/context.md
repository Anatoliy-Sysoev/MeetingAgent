# Текущий Контекст

Обновлено: 2026-06-09.

## Now

- last commit: MA-FIX-GUARD-CASES — pytest.skip(allow_module_level=True) на отсутствующий guard_v2_cases.jsonl
- in progress: none

## Done latest

- MA-FIX-GUARD-CASES (#32): pytest.skip(allow_module_level=True) в load_cases() — FileNotFoundError при collection устранён
- MA-ADR-AUTH (#33): ADR 0001 MVP access control — shared/per-user token; OIDC и public links out of scope; LAN не доверенный
- MA-ASR-HOTWORDS: configs/asr_hotwords.yaml (committed), hotwords loader/normalizer, faster-whisper >= 1.0 hotwords= param, CLI --hotwords/--hotwords-config
- MA-API-MEETINGS: read-only Meeting API, MeetingCardError → 422 на всех 4 роутах, allowlist суффиксов, ISO-8601 modified_at

## Next

- MA-INGEST-DEDUP (enforce token check)
- MA-JOB-API (enforce token check)
- MA-REVIEW-QUEUE

## Open decisions / blockers

- guard_v2_cases.jsonl отсутствует (pre-existing) → regenerate via MA-REVIEW-QUEUE (collection теперь не падает)
- Hotwords: Vosk/live path NOT SUPPORTED (grammar = restrictive whitelist, не additive boosting)
- Hotwords: GigaAM NOT SUPPORTED (subprocess, нет prompt API)
- 33_live_transcribe_meeting.py не существует — live-путь hotwords out of scope
