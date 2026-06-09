# Текущий Контекст

Обновлено: 2026-06-04.

MeetingAgent публикуется как local-first OSS проект для обработки встреч, транскрибации, проектной памяти, RAG-поиска и генерации рабочих артефактов.

## Текущее Состояние

- Основной публичный README оформлен как OSS landing page.
- Русская версия README сохранена в `README.ru.md`.
- Добавлены MIT license, security policy, contributing guide, code of conduct, changelog, issue templates и PR template.
- Добавлены безопасные синтетические examples в `examples/`.
- Runtime-папки `data/`, `logs/`, `vector_db/`, `watched_folder/`, `meetings/` закрыты через `.gitignore`.
- Приватные eval-отчеты, runtime-датасеты и локальные документы подпроектов сняты с индекса Git и остаются только локально.

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

## Meeting API (добавлено 2026-06-09)

Добавлен read-only Meeting API поверх существующих `meeting.json` и артефактов.

**Эндпоинты:**
- `GET /meetings` — список встреч (пагинация offset/limit), пустой корень = пустой список
- `GET /meetings/{meeting_id}` — полная карточка из meeting.json
- `GET /meetings/{meeting_id}/transcript` — содержимое транскрипта (segments.jsonl / txt / json)
- `GET /meetings/{meeting_id}/artifacts` — список артефактов с exists/size/modified_at
- `GET /meetings/{meeting_id}/artifacts/{artifact_name}` — содержимое текстового артефакта

**Гарантии:**
- API не запускает pipeline scripts и не мутирует meeting.json
- Path traversal заблокирован на уровне service и router
- Бинарные артефакты (.mp4, .wav и др.) не отдаются — 415
- Битая карточка в списке = warning, не 500

**Модули:**
- `src/asu_june_bot/meetings/service.py` — MeetingsService
- `src/asu_june_bot/api/routes_meetings.py` — router /meetings
- `tests/asu_june_bot/meetings/test_meetings_service.py` — 30 unit tests
- `tests/asu_june_bot/api/test_meetings_api.py` — 14 API tests

## Последнее Изменение

Выполнен cleanup публичного дерева:

- ужесточены `.gitignore` правила для private/eval/runtime данных;
- приватные quality reports и docs подпроекта сняты с индекса через `git rm --cached`;
- публичные `docs/context.md`, `docs/todo.md`, `docs/decisions.md` заменены на безопасные версии;
- публичный README больше не ведет на локальные private setup документы.

История Git пока не переписывалась. Если нужно убрать уже опубликованные приватные файлы из истории GitHub, нужен отдельный проход через `git filter-repo` или BFG с force-push.
