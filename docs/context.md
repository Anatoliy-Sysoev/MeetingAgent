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

## Последнее Изменение

Выполнен cleanup публичного дерева:

- ужесточены `.gitignore` правила для private/eval/runtime данных;
- приватные quality reports и docs подпроекта сняты с индекса через `git rm --cached`;
- публичные `docs/context.md`, `docs/todo.md`, `docs/decisions.md` заменены на безопасные версии;
- публичный README больше не ведет на локальные private setup документы.

История Git пока не переписывалась. Если нужно убрать уже опубликованные приватные файлы из истории GitHub, нужен отдельный проход через `git filter-repo` или BFG с force-push.
