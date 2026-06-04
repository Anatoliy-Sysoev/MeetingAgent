# Политика Безопасности

[English](SECURITY.md) | [Русский](SECURITY.ru.md)

MeetingAgent — local-first инструмент для проектной памяти и обработки встреч. Он может работать с приватными проектными документами, транскриптами, локальными индексами, артефактами, API-ключами и настройками model providers. Любые вопросы безопасности и приватности считаются приоритетными.

## Как Сообщать Об Уязвимости

Не открывайте публичный GitHub issue для уязвимостей, утечек секретов или приватных данных.

Сообщайте maintainer напрямую через приватный канал. Если приватного канала нет, откройте минимальный публичный issue без технических деталей, токенов, содержимого файлов, транскриптов и customer-specific данных.

Укажите:

- версию или commit;
- затронутую команду, API route, script или workflow;
- шаги воспроизведения на синтетических данных;
- ожидаемый impact;
- возможное исправление, если известно.

## Security-Sensitive Зоны

Эти изменения требуют дополнительной проверки:

- ingestion локальных файлов и path handling;
- parsing транскриптов и генерация meeting artifacts;
- RAG chunking, indexing, retrieval и source citation logic;
- API keys, `.env`, credentials и model endpoints;
- экспорт Markdown, DOCX, JSON, JSONL, SRT и VTT;
- Telegram, Web UI, FastAPI, Docker и внешние model integrations;
- prompt/tool boundaries, guardrails и out-of-scope request handling;
- runtime data в `data/`, `logs/`, `meetings/`, `vector_db/`, `watched_folder/`.

## Local-First Обработка Данных

Архитектура по умолчанию local-first:

- проектные документы и записи встреч остаются на машине пользователя;
- runtime outputs не коммитятся в Git;
- customer-specific corpora и приватные transcripts не публикуются;
- `.env`, `config.yaml`, logs, vector indexes, local caches и media files считаются локальными данными.

Перед публикацией bug report, test artifact или pull request удалите или анонимизируйте приватные имена, пути, содержимое встреч, URL, credentials и внутренние identifiers.

## Риски Зависимостей И Model Providers

MeetingAgent может использовать локальные и внешние model providers:

- никогда не коммитьте API keys и access tokens;
- используйте environment variables или локальные `.env` files;
- явно документируйте workflow, если он отправляет текст внешнему provider;
- не отправляйте приватные transcripts или customer documents в hosted models без явного выбора пользователя.

## Checklist Для Maintainer

Перед merge security-sensitive изменений:

- запустить релевантные tests и smoke checks;
- проверить новые file reads/writes и path handling;
- убедиться, что secrets и runtime data не staged;
- обновить documentation, если меняется data handling;
- держать guardrails консервативными для unsafe, mixed-scope и out-of-project requests.
