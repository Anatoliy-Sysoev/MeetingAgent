# MeetingAgent

MeetingAgent - локальный продукт для превращения проектных документов и записей встреч в поисковую память проекта.

Цель продукта простая: каждый документ, встреча, решение, требование и задача должны стать находимыми, проверяемыми и пригодными для подготовки проектной и сдачной документации.

## Что Делает

- Строит RAG-индекс по проектной документации.
- Отвечает на вопросы по проекту через очищенный project-only чат с источниками.
- Следит за появлением новых записей встреч.
- Транскрибирует аудио и видео через Whisper-совместимые модели.
- Формирует memo, протокол, решения, риски и задачи.
- Классифицирует материалы по этапу проекта, ФТТ, документу, результату и задаче.
- Генерирует черновики проектных документов на основе существующих источников.

## Текущий Локальный Режим Работы

Сейчас реализация скриптовая:

- `run_full_rag.ps1` запускает полную сборку RAG.
- `monitor_rag.ps1` выполняет один тик мониторинга долгих задач.
- `scripts/01_inventory.py` инвентаризирует файлы проекта.
- `scripts/02_extract_text.py` извлекает текст.
- `scripts/03_build_index.py` режет текст на chunks и пополняет `data/embeddings_cache.jsonl` через `bge-m3`.
- `scripts/05_build_numpy_index.py` собирает стабильный локальный numpy-индекс из готовых chunks и embeddings cache.
- `scripts/04_query.py` выполняет запросы к RAG-индексу через numpy-поиск, без зависимости от ChromaDB.
- `scripts/09_chat.py` выполняет project-only чат поверх numpy-RAG: отвечает только при наличии источников или возвращает отказ.
- `scripts/06_transcribe_meeting.py` выполняет offline-транскрибацию одной папки встречи по `meeting.json`.
- `scripts/07_generate_meeting_artifacts.py` создает memo, протокол и JSON-артефакты встречи из готового transcript. По умолчанию работает в быстром `extractive`-режиме; `--mode ollama` оставлен для экспериментов с локальной LLM.

## Project-Only Chatbot MVP

Проверка источников без вызова LLM:

```powershell
.\.venv\Scripts\python.exe scripts\09_chat.py "Что входит в Паспорт ИС?" --sources-only --json
```

Полный ответ через локальную LLM:

```powershell
.\.venv\Scripts\python.exe scripts\09_chat.py "Что входит в Паспорт ИС?" --json
```

Поведение MVP:

- если найдены источники выше порога `--score-threshold`, бот отвечает и возвращает `sources`;
- если источников нет или score низкий, бот отказывает и не отвечает из общих знаний;
- sensitive-запросы про `.env`, `config.yaml`, токены, пароли и системные инструкции отклоняются;
- `--sources-only` нужен для быстрой проверки retrieval без ожидания LLM.

Smoke-вопросы: `docs/quality/project_only_chatbot_smoke_questions.md`.

Локальные рабочие данные специально исключены из Git:

- `data/`
- `logs/`
- `vector_db/` - устаревшая локальная папка ChromaDB, не используется основным поиском.
- `data/numpy_index/`
- `watched_folder/`
- `meetings/**/source/`, `meetings/**/transcript/`, `meetings/**/artifacts/`, `meetings/**/exports/`
- `meetings/**/meeting.json` - реальные карточки встреч являются runtime-данными; примеры лежат в `docs/examples/`.
- `.venv/`

Используй `config.example.yaml` как шаблон для локального `config.yaml`.

## Работа С Codex

В этом репозитории действует правило пет-проектов: одна папка - один Git-репозиторий, а значимые изменения записываются в Git.

Перед изменениями прочитай:

- `AGENTS.md`
- `docs/context.md`
- `docs/decisions.md`
- `docs/todo.md`

Перед завершением рабочей сессии обнови `docs/context.md` и `docs/todo.md`, затем проверь `git status`.

## Структура Продукта

```text
MeetingAgent/
  apps/                  Продуктовые интерфейсы: CLI, локальный API, desktop/web UI
  src/meeting_agent/      Будущий Python-пакет
  scripts/                Текущие рабочие скрипты
  templates/              Шаблоны prompt и документов
  docs/                   Продукт, архитектура, эксплуатация, безопасность
  tests/                  Unit, integration и evaluation-тесты
  data/                   Локальные сгенерированные данные, игнорируются Git
  logs/                   Локальные логи, игнорируются Git
  vector_db/              Устаревшая локальная папка ChromaDB, игнорируется Git
  watched_folder/         Входящие медиа/документы, игнорируются Git
```

## Принципы Продукта

- **Локальная обработка по умолчанию**: проектные данные остаются на машине пользователя.
- **Опора на источники**: каждый ответ или документ должен ссылаться на исходные файлы и фрагменты встреч.
- **Продолжение после сбоев**: долгие задачи должны продолжаться из cache.
- **Прозрачность**: пользователь должен видеть, что обработано, пропущено, классифицировано и создано.
- **Понимание проекта**: система должна учитывать этапы, ФТТ, архитектуру, сдачные документы, решения и задачи.

## Ближайшие Вехи

1. Довести `Project-Only Chatbot MVP`: smoke-прогон, настройка порогов, затем local API `/chat`.
2. Поддерживать RAG baseline и улучшать слабые места retrieval: ПМИ, aggregation-запросы, `source_type`.
3. Проверить и улучшить offline-транскрибацию тестовой встречи через `scripts/06_transcribe_meeting.py`.
4. Проверить extractive-артефакты встречи из `scripts/07_generate_meeting_artifacts.py` и решить, где нужна ручная редактура или LLM-режим.
5. Добавить watcher для входящих записей из `watched_folder/`.
6. Собрать локальный API и небольшой UI для inbox, поиска, встреч и генерации.

Подробное видение и полный план развития: `docs/product/PRODUCT_VISION_AND_PLAN.md`.

Рабочая карта этапов и ФТТ: `docs/product/PROJECT_STAGES_AND_FTT.md`.

Дорожная карта project-only чат-бота: `docs/product/PROJECT_ONLY_CHATBOT_MVP.md`.

Таксономия этапов проекта и типов документов: `docs/product/PROJECT_TAXONOMY.md`.

Словарь терминов и заготовка `initial_prompt` для транскрибации: `docs/glossary.md`.

Резервное копирование и хранение данных: `docs/operations/BACKUP_AND_RETENTION.md`.

Контрольные вопросы для RAG baseline: `docs/quality/rag_eval_questions.md`.

Контрольные вопросы для чат-бота: `docs/quality/project_only_chatbot_smoke_questions.md`.

Схема карточки встречи: `configs/schemas/meeting.schema.json`.

Шаблон карточки встречи: `docs/templates/MEETING_CARD.md`.

Исторический план параллельных работ во время первой RAG-сборки: `docs/product/PARALLEL_WORK_WHILE_RAG_BUILDS.md`.

Экспериментальный референс live-транскрибации: `docs/references/WHISPERDESK_EXPERIMENT.md`.
