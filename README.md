# MeetingAgent

MeetingAgent — локальный продукт для превращения проектных документов и записей встреч в поисковую память проекта.

Цель продукта: каждый документ, встреча, решение, требование и задача должны стать находимыми, проверяемыми и пригодными для подготовки проектной и сдачной документации.

## Что делает

- Строит RAG-индекс по проектной документации.
- Поддерживает отдельный project-only бот по документации с API `/search` и `/chat`.
- Даёт локальный Web UI для запросов к `/chat`.
- Даёт Telegram adapter поверх локального `/chat`.
- Следит за появлением новых записей встреч.
- Транскрибирует аудио и видео через Whisper-совместимые модели.
- Формирует memo, протокол, решения, риски и задачи.
- Классифицирует материалы по этапу проекта, документу, результату и задаче.
- Генерирует черновики проектных документов на основе существующих источников.

## Подпроекты

### Project Knowledge Bot

`Project Knowledge Bot` — отдельный подпроект для локального AI-агента по проектной документации информационной системы.

Историческое рабочее имя в коде и путях:

```text
asu_june_bot
```

Назначение:

```text
принимать вопросы по проектному корпусу
отвечать только по источникам
возвращать citations
отказывать на внепроектные и смешанные запросы
логировать chat-запуски
измерять качество через baseline eval
давать локальный UI и Telegram-вход
```

Документация подпроекта:

```text
docs/subprojects/asu-june-bot/README.md
```

Ключевые документы подпроекта:

```text
docs/subprojects/asu-june-bot/TOMORROW_START.md
docs/subprojects/asu-june-bot/context.md
docs/subprojects/asu-june-bot/decisions.md
docs/subprojects/asu-june-bot/architecture.md
docs/subprojects/asu-june-bot/mvp.md
docs/subprojects/asu-june-bot/roadmap.md
docs/subprojects/asu-june-bot/todo.md
docs/subprojects/asu-june-bot/RUNBOOK_V2.md
docs/subprojects/asu-june-bot/telegram.md
docs/subprojects/asu-june-bot/eval_questions.md
docs/subprojects/asu-june-bot/product/README.md
```

Текущий статус:

```text
API Search MVP: готов
API Chat MVP: готов с ограничениями
Local Web UI: готов для отладки
Telegram adapter: готов для отладки
QH-1 Observability + Eval Baseline: реализован, baseline требует анализа
```

## Текущий локальный режим работы

В репозитории есть два контура.

### 1. Базовый MeetingAgent v1/baseline

Это старый общий RAG/meeting pipeline:

```text
run_full_rag.ps1
monitor_rag.ps1
scripts/01_inventory.py
scripts/02_extract_text.py
scripts/03_build_index.py
scripts/05_build_numpy_index.py
scripts/04_query.py
scripts/09_chat.py
scripts/06_transcribe_meeting.py
scripts/07_generate_meeting_artifacts.py
```

`scripts/09_chat.py` считается legacy/prototype для project-only чата. Целевой bot runtime дальше развивается не там.

### 2. Project Knowledge Bot v2.1/v2.2

Целевой контур бота:

```text
scripts/asu_june_bot_apply_config_v2_1.py
scripts/asu_june_bot_extract_text_v2.py
scripts/asu_june_bot_build_chunks_v2.py
scripts/asu_june_bot_audit_sources_v2.py
scripts/asu_june_bot_build_index_v2.py
scripts/asu_june_bot_health_v2.py
scripts/asu_june_bot_search_v2.py
scripts/asu_june_bot_guard_v2_eval.py
scripts/asu_june_bot_api.py
scripts/asu_june_bot_chat.py
scripts/asu_june_bot_chat_eval.py
scripts/asu_june_bot_telegram.py
src/asu_june_bot/
eval/cases/base.jsonl
```

Реализованные endpoints:

```text
GET /
GET /ui
GET /health
POST /search
POST /chat
```

Ключевое разделение:

```text
/search = evidence/context endpoint
/chat = answer with citations endpoint
/ui = локальная HTML-страница поверх /chat
Telegram adapter = внешний вход поверх локального /chat
```

`/search` не должен генерировать осмысленный ответ. Он возвращает sources/context/diagnostics. Осмысленный ответ формирует `/chat` через `ChatService`.

## Project Knowledge Bot: быстрые команды

### Завтрашнее восстановление

```text
docs/subprojects/asu-june-bot/TOMORROW_START.md
```

### Health

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_health_v2.py
```

### API + UI

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_api.py --host 127.0.0.1 --port 8000
```

Открыть:

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/ui
```

### Chat CLI

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_chat.py "Как происходит авторизация пользователей?" --mode hybrid --top-k 5 --model qwen2.5:7b-instruct --max-tokens 500 --timeout-sec 300 --json --output data\asu_june_bot\smoke_chat_ad.json
```

### Telegram adapter

```powershell
$env:ASU_JUNE_BOT_TELEGRAM_TOKEN='PASTE_TOKEN_HERE'
$env:ASU_JUNE_BOT_CHAT_API_URL='http://127.0.0.1:8000/chat'
.\.venv\Scripts\python.exe scripts\asu_june_bot_telegram.py
```

Подробно:

```text
docs/subprojects/asu-june-bot/telegram.md
```

### Eval baseline

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_chat_eval.py --cases eval\cases\base.jsonl --label baseline --model qwen2.5:7b-instruct --top-k 5
```

## Ограничения ввода

Для `/search`, `/chat`, Web UI и Telegram adapter установлен единый лимит:

```text
MAX_QUERY_CHARS = 2000
```

Слишком длинные запросы отсекаются до запуска retrieval/LLM.

## Runtime-данные

Локальные рабочие данные исключены из Git:

```text
data/
logs/
vector_db/
watched_folder/
meetings/**/source/
meetings/**/transcript/
meetings/**/artifacts/
meetings/**/exports/
meetings/**/meeting.json
.venv/
eval/reports/
```

Для Project Knowledge Bot runtime хранится в:

```text
data/asu_june_bot/chunks_v2.jsonl
data/asu_june_bot/embeddings_cache_v2.jsonl
data/asu_june_bot/numpy_index_v2/
data/asu_june_bot/chat_runs.jsonl
```

Используй `config.example.yaml` как шаблон для локального `config.yaml`.

## Работа с Codex

В этом репозитории действует правило: одна папка — один Git-репозиторий, значимые изменения записываются в Git.

Перед изменениями прочитай:

```text
AGENTS.md
docs/context.md
docs/decisions.md
docs/todo.md
```

Для Project Knowledge Bot дополнительно прочитай:

```text
docs/subprojects/asu-june-bot/README.md
docs/subprojects/asu-june-bot/TOMORROW_START.md
docs/subprojects/asu-june-bot/context.md
docs/subprojects/asu-june-bot/decisions.md
docs/subprojects/asu-june-bot/todo.md
docs/subprojects/asu-june-bot/RUNBOOK_V2.md
```

Перед завершением рабочей сессии обнови:

```text
docs/context.md
docs/todo.md
docs/subprojects/asu-june-bot/context.md
docs/subprojects/asu-june-bot/todo.md
```

Если работа меняла продуктовый статус бота, проверь также:

```text
docs/subprojects/asu-june-bot/README.md
docs/subprojects/asu-june-bot/architecture.md
docs/subprojects/asu-june-bot/mvp.md
docs/subprojects/asu-june-bot/roadmap.md
docs/subprojects/asu-june-bot/product/README.md
```

## Структура продукта

```text
MeetingAgent/
  apps/                    Продуктовые интерфейсы: CLI, локальный API, desktop/web UI
  src/asu_june_bot/         Целевой runtime Project Knowledge Bot
  src/meeting_agent/        Будущий общий Python-пакет MeetingAgent
  scripts/                  Рабочие скрипты v1 и bot v2
  templates/                Шаблоны prompt и документов
  docs/                     Продукт, архитектура, эксплуатация, безопасность
  docs/subprojects/         Документация подпроектов
  tests/                    Unit, integration и evaluation-тесты
  eval/                     Eval cases / golden answers / runtime reports
  data/                     Локальные сгенерированные данные, игнорируются Git
  logs/                     Локальные логи, игнорируются Git
  vector_db/                Устаревшая локальная папка ChromaDB, игнорируется Git
  watched_folder/           Входящие медиа/документы, игнорируются Git
```

## Принципы продукта

- **Локальная обработка по умолчанию**: проектные данные остаются на машине пользователя.
- **Опора на источники**: каждый ответ или документ должен ссылаться на исходные файлы и фрагменты встреч.
- **Продолжение после сбоев**: долгие задачи должны продолжаться из cache.
- **Прозрачность**: пользователь должен видеть, что обработано, пропущено, классифицировано и создано.
- **Project-only дисциплина**: отказ лучше неподтвержденного ответа.
- **Измеримость качества**: изменения search/chat/context должны проверяться через smoke/eval.

## Ближайшие вехи

1. Завтра выполнить `docs/subprojects/asu-june-bot/TOMORROW_START.md`.
2. Проверить API, UI и Telegram adapter.
3. Зафиксировать результаты демонстрационного smoke.
4. Проанализировать QH-1 baseline failures.
5. Реализовать QH-2 Source Quality Filter.
6. Сравнить baseline vs with_source_filter.
7. Реализовать QH-3 Parent Expansion только при необходимости.
8. Docker — только после QH-5 Release Stabilization.

## Навигация по документации

Подробное видение и полный план развития MeetingAgent:

```text
docs/product/PRODUCT_VISION_AND_PLAN.md
```

Рабочая карта этапов и требований:

```text
docs/product/PROJECT_STAGES_AND_FTT.md
```

Дорожная карта старого project-only chatbot baseline:

```text
docs/product/PROJECT_ONLY_CHATBOT_MVP.md
```

Документация текущего Project Knowledge Bot:

```text
docs/subprojects/asu-june-bot/README.md
```

Завтрашний чек-лист запуска:

```text
docs/subprojects/asu-june-bot/TOMORROW_START.md
```

Telegram adapter:

```text
docs/subprojects/asu-june-bot/telegram.md
```

Product package Project Knowledge Bot:

```text
docs/subprojects/asu-june-bot/product/README.md
```

Runbook Project Knowledge Bot:

```text
docs/subprojects/asu-june-bot/RUNBOOK_V2.md
```

Словарь терминов и заготовка `initial_prompt` для транскрибации:

```text
docs/glossary.md
```

Резервное копирование и хранение данных:

```text
docs/operations/BACKUP_AND_RETENTION.md
```

Контрольные вопросы для RAG baseline:

```text
docs/quality/rag_eval_questions.md
```

Схема карточки встречи:

```text
configs/schemas/meeting.schema.json
```

Шаблон карточки встречи:

```text
docs/templates/MEETING_CARD.md
```
