# Todo

Обновлено: 2026-06-09.

## Dev Roadmap

- [x] MA-API-MEETINGS — read-only Meeting API — c4938cc + fix-commit
- [ ] MA-ASR-HOTWORDS — кастомный словарь для ASR (не требует auth)
- [ ] MA-ADR-AUTH — ADR по access control (до INGEST-DEDUP и JOB-API)
- [ ] MA-INGEST-DEDUP — upload + sha256 дедупликация при ingest
- [ ] MA-JOB-API — очередь задач concurrency=1 поверх pipeline scripts
- [ ] MA-REVIEW-QUEUE — разметка chat_runs для eval (sidecar labels.jsonl)
- [ ] MA-FIX-GUARD-CASES — восстановить guard_v2_cases.jsonl или xfail с причиной (known-failing, не блокирует; пересекается с MA-REVIEW-QUEUE)
- [ ] Meeting Workspace UI — web-интерфейс карточки с аудио-синхронизацией

## Сейчас

- Проверить публичное дерево на приватные строки перед следующим push.
- Поддерживать tracked quality/docs только в синтетическом или обезличенном виде.
- Не коммитить runtime outputs из `data/`, `logs/`, `vector_db/`, `watched_folder/`, `meetings/`.

## OSS Packaging

- Сохранять открытыми текущие GitHub issues как публичный backlog.
- Добавить маленький public sample dataset без реальных документов и транскриптов.
- Добавить короткий transcript-to-protocol CLI quickstart на синтетическом примере.
- Настроить release workflow и changelog automation.
- Улучшить parity между English/Russian docs.
- Рассмотреть GitHub Pages для публичной документации.

## Product Backlog

- UI для запуска транскрибации локального видео.
- Speaker diarization как отдельный backend с явным opt-in.
- DOCX export для протокола встречи.
- Quality eval для meeting artifacts на синтетических наборах.
- API/Telegram integration для meeting search без обхода source-grounding.

## Security / Privacy

- Добавить anonymization pipeline для приватных transcripts.
- Добавить pre-commit или CI check на запрещенные пути, секреты и приватные corpus names.
- Если требуется полная очистка GitHub history, выполнить отдельный согласованный `git filter-repo`/BFG проход и пересоздать release/tag.
