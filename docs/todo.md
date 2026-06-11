# Todo

Обновлено: 2026-06-11.

## Done

- [x] MA-API-MEETINGS-RESTORE (#30): read-only Meeting API restored — GET /meetings, /{id}, /{id}/transcript, /{id}/artifacts, /{id}/artifacts/{name}
- [x] MA-JOB-API (#35): concurrency=1 job runner, 4 endpoints
- [x] MA-INGEST-DEDUP (#34): POST /meetings/ingest, sha256 dedup, auth guard

## Backlog (приоритет сверху вниз)

- MA-REVIEW-QUEUE: разметка chat_runs.jsonl для eval, генерация guard_v2_cases.jsonl
- Meeting Workspace UI: страница встречи с кнопками запуска pipeline-стадий, статус job-а в реальном времени
- #39/#40 auth evolution: per-user tokens или OIDC; require_write_access() — стабильный контракт роутов, менять только внутри auth.py

## Dev Roadmap

- После Meeting Workspace UI: замкнутый цикл ingest → transcribe → diarize → merge через браузер
- После #39/#40: multi-user / публичный деплой без шаринга одного токена
