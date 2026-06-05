# Todo

Обновлено: 2026-06-05.

## Сейчас

- Проверить публичное дерево на приватные строки перед следующим push.
- При каждом новом публичном артефакте сверяться с `AGENTS.md`: Git хранит только public-safe код/docs/examples/tests, приватные corpus/runtime/eval остаются локально.
- Разметить generated `manual_review` файл из ignored `data/diagnostics/` и затем пересчитать pivot через `scripts/diagnostics/pivot_manual_review.py`.
- Расширить локальный `gold.jsonl` точными `expected_answer_facts` / `negative_facts` для табличных и конфликтных вопросов.
- Следующий retrieval bucket: table expansion для запросов вида "перечисли требования Этапа 3" без изменения persisted chunks и без реэмбеддинга.
- `integration_ftt` required-anchor source selection закрыт на targeted Q040-Q044 для локального qwen3.5:4b.
- Следующий quality bucket: ручная проверка ответов Q040-Q044 после source selection и затем пересчет pivot по 100 вопросам.
- Если Q040-Q044 ручная проверка подтвердит качество, следующий retrieval bucket выбирать по обновленному pivot, а не по старой сводке.
- Все новые chat/eval прогоны запускать на `qwen3.5:4b`; старые model-comparison артефакты считать historical baseline.
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
