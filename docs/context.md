# Текущий Контекст

Обновлено: 2026-06-09.

## Now

- last commit: e3a7b0c — docs: sync last-commit SHA and MA-ASR-HOTWORDS fix-commit reference
- in progress: none

## Done latest

- MA-ADR-AUTH (#33): ADR 0001 MVP access control — shared/per-user token; OIDC и public links out of scope; LAN не доверенный
- MA-ASR-HOTWORDS: configs/asr_hotwords.yaml (committed), hotwords loader/normalizer, faster-whisper >= 1.0 hotwords= param, CLI --hotwords/--hotwords-config
- MA-API-MEETINGS: read-only Meeting API, MeetingCardError → 422 на всех 4 роутах, allowlist суффиксов, ISO-8601 modified_at

## Next

- MA-INGEST-DEDUP (enforce token check)
- MA-JOB-API (enforce token check)
- MA-REVIEW-QUEUE

## Open decisions / blockers

- guard_v2_cases.jsonl отсутствует (pre-existing) → MA-FIX-GUARD-CASES, не блокирует
- Hotwords: Vosk/live path NOT SUPPORTED (grammar = restrictive whitelist, не additive boosting)
- Hotwords: GigaAM NOT SUPPORTED (subprocess, нет prompt API)
- 33_live_transcribe_meeting.py не существует — live-путь hotwords out of scope
