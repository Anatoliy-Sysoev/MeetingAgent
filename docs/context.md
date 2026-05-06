# Контекст Проекта

Обновлено: 2026-05-06.

## Текущее Состояние

MeetingAgent - приватный GitHub-backed пет-проект и локальный продуктовый репозиторий.

Репозиторий:

- Локальный путь: `%USERPROFILE%\Desktop\AI\MeetingAgent`
- Remote: `https://github.com/Anatoliy-Sysoev/MeetingAgent`
- Видимость: private
- Ветка: `main`

Продуктовое направление: local-first агент памяти проекта.

Основные сценарии:

- RAG по проектной документации;
- транскрибация встреч;
- генерация memo и протоколов;
- классификация по этапу проекта, ФТТ, задаче и документу;
- генерация документов на основе цитируемых проектных источников.

## Runtime-Статус

Долгая сборка RAG идет локально. Без причины ее не прерывать.

Важные runtime-факты:

- `run_full_rag.ps1` запускает полную сборку.
- `scripts/03_build_index.py` - долгий шаг embeddings/indexing.
- `data/embeddings_cache.jsonl` - resumable cache embeddings.
- `monitor_rag.ps1` - watchdog tick.
- Runtime-папки игнорируются Git.

## Важные Файлы

- `README.md`: обзор продукта и запуск.
- `AGENTS.md`: инструкции для Codex/AI.
- `docs/context.md`: текущее состояние проекта.
- `docs/decisions.md`: почему приняты ключевые решения.
- `docs/todo.md`: следующие шаги.
- `.env.example`: безопасный пример переменных окружения.
- `config.example.yaml`: безопасный пример локальной конфигурации.
- `scripts/03_build_index.py`: worker для embeddings/indexing.
- `monitor_rag.ps1`: watchdog долгой RAG-сборки.

## Что Изменилось Недавно

- Создана продуктовая структура репозитория.
- Создан и запушен приватный GitHub-репозиторий.
- Runtime-данные исключены из Git.
- Watchdog усилен для работы с Ollama и живым Python build-процессом.
- В `scripts/03_build_index.py` разделены reusable `chunk_id` и Chroma `db_id`, чтобы одинаковые backup-документы не конфликтовали в ChromaDB, а embeddings cache оставался переиспользуемым.
- Добавлены стандартные файлы пет-проекта: `AGENTS.md`, `docs/context.md`, `docs/decisions.md`, `docs/todo.md` и `.env.example`.
- Основная документация переведена на русский язык как основной язык проекта.
- Добавлен подробный продуктовый документ `docs/product/PRODUCT_VISION_AND_PLAN.md`: видение, модули, сценарии, roadmap и адаптация идей Speakr.
- Добавлен план параллельных работ `docs/product/PARALLEL_WORK_WHILE_RAG_BUILDS.md`, чтобы развивать продукт, пока текущая RAG-сборка продолжается.

## Что Осталось

- Дождаться завершения текущей RAG-сборки.
- Параллельно делать задачи, не зависящие от готовой vector DB: prompt-шаблоны, JSON-схемы, healthcheck/status, проектирование meeting processor.
- Проверить количество записей в коллекции ChromaDB и smoke-запросы.
- Улучшить вывод query: добавить компактные ссылки на источники.
- Добавить инкрементальное обновление RAG.
- Собрать первый pipeline обработки встреч.

## Восстановление Контекста В Новом Треде

Используй prompt:

```text
Прочитай README.md, AGENTS.md, docs/context.md, docs/todo.md и git log --oneline -10. Восстанови контекст проекта и предложи следующий шаг.
```
