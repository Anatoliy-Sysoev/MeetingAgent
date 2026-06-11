# Todo

Обновлено: 2026-06-11.

## Backlog (приоритет сверху вниз)

- MA-API-MEETINGS: read-only Meeting API — GET /meetings (list), GET /meetings/{id} (card), GET /meetings/{id}/transcript; routes_meetings.py не существует, нужно реализовать
- MA-REVIEW-QUEUE: разметка chat_runs.jsonl для eval, генерация guard_v2_cases.jsonl
- Meeting Workspace UI: страница встречи с кнопками запуска pipeline-стадий, статус job-а в реальном времени
- #39/#40 auth evolution: per-user tokens или OIDC; require_write_access() — стабильный контракт роутов, менять только внутри auth.py

## Dev Roadmap

- После MA-API-MEETINGS: UI может читать список встреч и карточку
- После Meeting Workspace UI: замкнутый цикл ingest → transcribe → diarize → merge через браузер
- После #39/#40: multi-user / публичный деплой без шаринга одного токена
