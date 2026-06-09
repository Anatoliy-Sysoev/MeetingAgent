# Todo

Обновлено: 2026-06-04.

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

## Dev Roadmap (активные карточки)

- [x] MA-API-MEETINGS — read-only Meeting API (GET /meetings + /transcript + /artifacts)
- [ ] MA-ASR-HOTWORDS — кастомный словарь для ASR (быстрая победа, не требует auth)
- [ ] MA-ADR-AUTH — ADR по access control до MA-INGEST-DEDUP и MA-JOB-API
- [ ] MA-INGEST-DEDUP — upload + sha256 дедупликация при создании карточки
- [ ] MA-JOB-API — очередь задач concurrency=1 поверх pipeline scripts
- [ ] MA-REVIEW-QUEUE — разметка chat_runs для eval (sidecar labels.jsonl)
- [ ] Meeting Workspace UI — web-интерфейс карточки с аудио-синхронизацией

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
