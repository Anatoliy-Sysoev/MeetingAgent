# Текущий Контекст

Обновлено: 2026-06-05.

MeetingAgent публикуется как local-first OSS проект для обработки встреч, транскрибации, проектной памяти, RAG-поиска и генерации рабочих артефактов.

## Текущее Состояние

- Основной публичный README оформлен как OSS landing page.
- Русская версия README сохранена в `README.ru.md`.
- Добавлены MIT license, security policy, contributing guide, code of conduct, changelog, issue templates и PR template.
- Добавлены безопасные синтетические examples в `examples/`.
- Runtime-папки `data/`, `logs/`, `vector_db/`, `watched_folder/`, `meetings/` закрыты через `.gitignore`.
- Приватные eval-отчеты, runtime-датасеты и локальные документы подпроектов сняты с индекса Git и остаются только локально.
- Публичные ссылки на удаленные private docs заменены на `docs/project_knowledge_bot.md`.
- Версия FastAPI Project Knowledge Bot берется из package `__version__`.
- `scripts/README.md` разделяет current runtime и legacy baseline.

## Важные Файлы

- `README.md` - публичное описание и quickstart.
- `README.ru.md` - русская версия описания.
- `docs/decisions.md` - публичные архитектурные решения.
- `docs/todo.md` - публичный backlog.
- `docs/quality/README.md` - политика публикации quality/eval артефактов.
- `.gitignore` - защита runtime outputs, приватных корпусов и локальных отчетов.
- `.env.example` - пример переменных без секретов.

## Что Не Публикуется

- реальные проектные документы;
- реальные транскрипты и аудио/видео;
- локальные meeting cards с содержимым встреч;
- embeddings cache, индексы и vector databases;
- eval runtime reports и private review datasets;
- локальные `.env`, `config.yaml`, токены и machine-specific paths.

Локальные подробные рабочие заметки сохранены в ignored-папке `docs/private/` и не должны попадать в Git.

## Последнее Изменение

В `AGENTS.md` закреплены правила после cleanup публичного Git:

- что ведется в репозитории: код, public-safe docs, synthetic examples, safe config examples и тесты без приватных данных;
- что остается только локально: `.env`, `config.yaml`, runtime outputs, реальные документы/транскрипты, индексы, cache, private eval/manual-review и `docs/private/`;
- перед commit нужно проверять подозрительные пути через `git check-ignore -v` и не использовать `git add -f` для ignored файлов без отдельного решения.

Добавлен локальный диагностический runner для последовательного сравнения Ollama-моделей на пользовательском наборе вопросов:

- runner сохраняет исходный вопрос, фактический `run_query`, ответ, источники, статус и время ответа;
- результаты пишутся в ignored runtime-папки `data/diagnostics/` и `logs/`;
- JSONL/summary/manual-review outputs не публикуются в Git.

Добавлены публично безопасные диагностические утилиты для локальных quality runs:

- `scripts/diagnostics/check_index_coverage.py` проверяет, покрывает ли JSONL индекс ожидаемые gold anchors;
- `scripts/diagnostics/pivot_manual_review.py` строит status/verdict pivots по локальному manual-review JSONL;
- приватные `gold.jsonl`, coverage reports и pivots остаются в ignored `data/diagnostics/`.

Добавлена runtime-семантика заголовков ФТТ Table 8 в `ContextBuilder`:

- карта заголовков хранится в public-safe `configs/asu_june_bot/table_header_maps.yaml`;
- строки таблицы с `Входит в объём проекта_3: Х` получают нормализованный факт `Этап 3 (ФТ3)` только в built context;
- persisted chunks, `chunk_id`, embeddings cache и numpy index не меняются;
- targeted retrieval/context check для вопросов по требованиям `1.1` и `1.3` подтверждает `Этап 3 (ФТ3)` без `Этап 1 (ФТ1)`.

Добавлен diagnostic-only аудит answer gate:

- `scripts/diagnostics/audit_answer_gate.py` проверяет наличие required anchors в corpus, built context и prompt после обрезки;
- локальная проверка `integration_ftt` показала: нужный anchor есть в corpus, но для проблемного вопроса не попадает в context/prompt;
- значит текущий дефект относится к required-anchor source selection, а не к validator и не к отсутствию документа в корпусе;
- JSONL/summary outputs остаются в ignored `data/diagnostics/`.

Добавлен required-anchor source selection для ФТТ-интеграций:

- `SearchService` определяет intent для вопросов `integration_ftt`: протокол, формат сообщения, размер сообщения, тип аутентификации, идентификация объектов;
- до rerank в raw candidates подмешивается или продвигается ФТТ chunk с нужным anchor (`https`, `JSON/XML`, `100Мб`, `Basic-аутентификация`, `тэг в заголовке вызова`);
- diagnostics stage: `integration_ftt_required_anchor_selection`;
- targeted проверка Q040-Q044 на локальном qwen3.5:4b: все 5 ответили, required anchors есть в corpus/context/prompt, `no_answer=0`, `validation_failed=0`;
- Q043 подтверждает `Basic-аутентификация` как ФТТ-источник без подмены Blitz/OIDC как общего типа аутентификации.

Штатная chat-модель переведена на `qwen3.5:4b`:

- обновлены runtime fallbacks для CLI/API/Telegram и локальный ignored `config.yaml`;
- обновлены public config examples, `.env.example`, quickstarts и UI model selector;
- `OllamaOpenAIClient` добавляет `/no_think` для `qwen3.5:*`;
- embeddings model не менялась: `bge-m3`.

Ранее выполнен cleanup публичного дерева:

- ужесточены `.gitignore` правила для private/eval/runtime данных;
- приватные quality reports и docs подпроекта сняты с индекса через `git rm --cached`;
- публичные `docs/context.md`, `docs/todo.md`, `docs/decisions.md` заменены на безопасные версии;
- публичный README больше не ведет на локальные private setup документы.
- `src/meeting_agent/` явно описан как planned scaffold, кроме реализованного `transcription` слоя.

История Git пока не переписывалась. Если нужно убрать уже опубликованные приватные файлы из истории GitHub, нужен отдельный проход через `git filter-repo` или BFG с force-push.
