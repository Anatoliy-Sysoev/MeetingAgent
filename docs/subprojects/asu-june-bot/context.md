# Контекст Подпроекта Asu June Bot

Обновлено: 2026-05-12.

## Назначение

Asu June Bot — отдельный подпроект внутри MeetingAgent для разработки локального AI-агента по проекту ЦП УПКС.

Бот должен отвечать не как универсальный ChatGPT, а как проектный ассистент системного аналитика:

- искать факты в проектной документации;
- давать структурированные ответы;
- ссылаться на документы, разделы, пункты и фрагменты;
- явно отделять подтвержденные факты от вывода;
- отказывать на вопросы вне проекта или без источников.

## Почему выделен отдельный подпроект

Попытка развивать project-only чат в `scripts/09_chat.py` показала архитектурный риск: один скрипт начал смешивать CLI, guard, retrieval, query expansion, document expansion, LLM-вызов, fallback и форматирование ответа.

Решение: не продолжать раздувать `09_chat.py`, а выделить Asu June Bot в отдельный подпроект с собственной архитектурой, документацией, API-контрактом и eval-набором.

`09_chat.py` допускается оставить как prototype, но новая реализация должна идти модульно.

## Что уже реализовано

### 1. Search MVP

Начат первый технический слой Asu June Bot: search MVP.

Добавлено:

```text
src/asu_june_bot/
  __init__.py
  core/config.py
  retrieval/models.py
  retrieval/metadata.py
  retrieval/source_policy.py
  retrieval/bm25.py
  retrieval/vector.py
  retrieval/hybrid.py
  retrieval/chunks.py
  retrieval/query_expansion.py
scripts/asu_june_bot_search.py
configs/asu_june_bot/retrieval.yaml
configs/asu_june_bot/source_policy.yaml
configs/asu_june_bot/query_expansion.yaml
configs/asu_june_bot/llm.yaml
configs/asu_june_bot/guardrails.yaml
```

Что умеет текущий слой:

- загружать основной `config.yaml` и конфиги Asu June Bot;
- читать текущий `data/chunks.jsonl` MeetingAgent;
- использовать существующий `data/numpy_index` через adapter;
- строить BM25 in-memory без внешних зависимостей;
- объединять vector и BM25 выдачу в `HybridRetriever`;
- расширять запрос через `query_expansion.yaml`;
- вычислять `source_type`, `document_type`, `module`, `stage`, `section`, `sections` эвристически по пути и тексту chunk;
- применять `SourcePolicy`, чтобы по умолчанию отдавать приоритет проектным документам и не тащить `system_export` без явного запроса;
- запускать CLI-поиск через `scripts/asu_june_bot_search.py`.

Проверочная команда после `git pull`:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_search.py "Какие интеграции заявлены в проекте?" --top-k 10 --json
```

Для точного поиска по пункту:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_search.py "ФТТ 4.2.5 НОВАДОК ЭЦП" --mode bm25 --top-k 10 --json
```

### 2. Chunking v2

Зафиксирована стратегия структурного chunking v2:

```text
docs/subprojects/asu-june-bot/chunking_strategy.md
```

Добавлен безопасный сборщик v2:

```text
scripts/asu_june_bot_build_chunks_v2.py
run_asu_june_bot_chunks_v2.ps1
```

Что делает v2-сборщик:

- читает уже готовый `data/extracted_text/_metadata.jsonl`;
- читает извлеченный текст из `extracted_path`;
- строит parent/child chunks;
- превращает строки таблиц в child chunks;
- пытается заполнить `requirement_id`, `sections`, `document_type`, `source_type`, `integration`, `protocol`;
- пишет результат в `data/asu_june_bot/chunks_v2.jsonl`;
- пишет отчеты `chunking_v2_report.json` и `chunking_v2_report.md`;
- не трогает `data/chunks.jsonl`, `data/embeddings_cache.jsonl`, `data/numpy_index` и `run_full_rag.ps1`.

Проверочные команды:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_build_chunks_v2.py --dry-run --limit 5
.\.venv\Scripts\python.exe scripts\asu_june_bot_build_chunks_v2.py --path-contains "ФТТ"
.\run_asu_june_bot_chunks_v2.ps1
```

## Проектная область знаний

Основная предметная область — проект ЦП УПКС: «Цифровая платформа управления проектами капитального строительства».

Ключевые документы и источники:

- ФТТ;
- ЦТА;
- проектные решения по модулям;
- соглашения об интеграции;
- Паспорт ИС;
- ПМИ и сценарии испытаний;
- руководства администратора ИС и ИБ;
- протоколы встреч;
- решения, задачи, риски и открытые вопросы;
- маппинги НСИ / СоИ / MDR.

## Базовое проектное понимание

Бот должен понимать верхнеуровневую модель ЦП УПКС:

- ЦП УПКС — цифровая платформа управления проектами капитального строительства.
- Система автоматизирует проектные процессы от проектирования до ввода в эксплуатацию, а также капитальные ремонты и демонтаж объектов.
- В проекте есть функциональные направления: ПИР, МТО, СМР, Строительный контроль, Исполнительная документация, ПНР, КСП, Контроль стоимости и прогресса.
- Этап 1 сфокусирован на части функционала ПИР, СМР/Строительный контроль, исполнительной документации, справочниках, авторизации, уведомлениях и базовой архитектуре.
- Архитектурно система строится как микросервисная платформа с Front, Core, Disk, Building, Approvals, Notifications, Ed, CC, Catalog, Help, Mdr и инфраструктурными компонентами.
- Интеграции включают AD/LDAPS, Blitz IDP, MDR/КШД/СОИ, Exchange/SMTP, Minio S3, PostgreSQL, SIEM/логирование и другие взаимодействия, если они подтверждены документами.

## Целевой режим ответа

Бот должен отвечать так:

```text
Краткий ответ:
...

Обоснование:
1. [Документ, раздел/пункт] ...
2. [Документ, таблица/поток] ...

Вывод:
...

Ограничения:
- ...

Источники:
- SRC-001: документ, раздел/пункт, chunk, ссылка
```

Запрещенный стиль:

```text
Обычно в таких системах...
Вероятно...
Я думаю...
В проекте точно есть..., если источник не найден.
```

## Локальный режим

На первом этапе Asu June Bot должен работать локально:

- Ollama как LLM runtime;
- Qwen3 4B как стартовая модель;
- qwen3:8b / qwen2.5:7b-instruct / mistral как модели для сравнения;
- текущие chunks MeetingAgent как источник данных;
- локальный индекс: сначала numpy/FAISS, затем Qdrant;
- локальный FastAPI API;
- Open WebUI позже как UI-поверхность.

## Будущая миграция на GPU

Вся LLM-интеграция должна строиться через OpenAI-compatible API.

Сейчас:

```text
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=qwen3:4b
```

Позже:

```text
LLM_BASE_URL=http://gpu-server:8000/v1
LLM_MODEL=Qwen/Qwen3-14B или Qwen/Qwen3-32B
```

Это позволит перейти с Ollama на vLLM без переписывания бизнес-логики агента.

## Текущие ограничения

- Текущий RAG MeetingAgent уже умеет строить chunks и numpy index, но source typing, hybrid search и точные ссылки на разделы/пункты требуют проверки на реальном корпусе.
- Текущий `scripts/09_chat.py` является prototype, а не целевой архитектурой Asu June Bot.
- Search MVP уже прошел первый локальный smoke, но после новых правок требуется повторный прогон.
- Chunking v2 создан как отдельный безопасный pipeline, но еще не прогнан локально и не сравнен с v1.
- Source type inference пока эвристический и должен быть заменен/усилен metadata extraction на этапе индексации.
- Пока нет стабильного answer validator, который проверяет, что все утверждения подтверждены источниками.
- Пока нет единого mapping-файла для ссылок на Яндекс.Диск / источники.

## Ближайшая цель

Сначала проверить chunking v2 и search MVP локально.

Ожидаемый следующий шаг:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_build_chunks_v2.py --dry-run --limit 5
.\.venv\Scripts\python.exe scripts\asu_june_bot_build_chunks_v2.py --path-contains "ФТТ"
.\.venv\Scripts\python.exe scripts\asu_june_bot_search.py "ФТТ 4.2.5 НОВАДОК ЭЦП" --mode bm25 --top-k 10 --json
.\.venv\Scripts\python.exe scripts\asu_june_bot_search.py "Какие интеграции заявлены в проекте?" --top-k 10 --json
.\.venv\Scripts\python.exe scripts\asu_june_bot_search.py "Что входит в Паспорт ИС?" --top-k 10 --json
```

После проверки:

- исправить import/runtime ошибки;
- оценить качество `chunks_v2.jsonl`;
- сравнить v1 и v2 на baseline;
- только потом проектировать v2 index и подключение к `/search`.
