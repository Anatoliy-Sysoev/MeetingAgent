# Текущий Контекст

Обновлено: 2026-06-09.

## Now

- last commit: 8646252 — Add custom vocabulary hotwords for ASR
- in progress: none

## Done latest

- MA-API-MEETINGS: read-only Meeting API (GET /meetings + /transcript + /artifacts), MeetingCardError → 422 на всех 4 роутах, allowlist суффиксов, ISO-8601 modified_at
- MA-ASR-HOTWORDS: configs/asr_hotwords.yaml (committed), hotwords loader/normalizer, faster-whisper >= 1.0 hotwords= param, CLI --hotwords/--hotwords-config в 22_transcribe_meeting.py

## Next

- MA-ADR-AUTH
- MA-INGEST-DEDUP
- MA-JOB-API

## Open decisions / blockers

- guard_v2_cases.jsonl отсутствует (pre-existing) → MA-FIX-GUARD-CASES, не блокирует
- Hotwords: Vosk/live path NOT SUPPORTED (grammar = restrictive whitelist, не additive boosting)
- Hotwords: GigaAM NOT SUPPORTED (subprocess, нет prompt API)
- 33_live_transcribe_meeting.py не существует — live-путь hotwords out of scope
