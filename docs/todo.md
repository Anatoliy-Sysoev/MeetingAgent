# Todo

Обновлено: 2026-06-04.

## Сейчас

- Проверить публичное дерево на приватные строки перед следующим push.
- Дождаться завершения локального comparison run и вручную разметить generated `manual_review` файл из ignored `data/diagnostics/`.
- Поддерживать tracked quality/docs только в синтетическом или обезличенном виде.
- Не коммитить runtime outputs из `data/`, `logs/`, `vector_db/`, `watched_folder/`, `meetings/`.
- Если потребуется полная очистка GitHub history, выполнить отдельную согласованную history purge процедуру.

## OSS Packaging

- Сохранять открытыми текущие GitHub issues как публичный backlog.
- Добавить маленький public sample dataset без реальных документов и транскриптов.
- Добавить короткий transcript-to-protocol CLI quickstart на синтетическом примере.
- Настроить release workflow и changelog automation.
- Улучшить parity между English/Russian docs.
- Рассмотреть GitHub Pages для публичной документации.
- Подготовить `v0.1.1` release после documentation cleanup.

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
