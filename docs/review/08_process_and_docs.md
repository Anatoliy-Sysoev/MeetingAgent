# Процесс И Документация

Артефакт №8 серии полного ревью. Разбирает **как репозиторий поддерживается между сессиями** через документацию: какие документы образуют рабочий цикл, какие гарантии даёт schema-валидация, где документация уже разошлась с кодом.

## Содержание

1. [Каталог docs/ (49 файлов)](#1-каталог-docs-49-файлов)
2. [Трёхфайловый цикл: decisions ↔ context ↔ todo](#2-трёхфайловый-цикл-decisions--context--todo)
3. [`AGENTS.md` как governance contract](#3-agentsmd-как-governance-contract)
4. [Schema как gating contract: positive example](#4-schema-как-gating-contract-positive-example)
5. [Где цикл сломался](#5-где-цикл-сломался)
6. [Свежесть документации (date stamps)](#6-свежесть-документации-date-stamps)
7. [Сводка drift'ов из артефактов №3-7](#7-сводка-driftов-из-артефактов-3-7)
8. [Что не было проверено](#8-что-не-было-проверено)

## 1. Каталог Docs/ (49 Файлов)

### 1.1 Корневые файлы

| Файл | Назначение | Кем читается |
|---|---|---|
| `README.md` | Обзор продукта + команды запуска | Пользователь + AI-агент |
| `AGENTS.md` | Инструкции для AI-агентов (44 строки) | AI-агент (включая Claude Code) |
| `RAG_AUTOMATION_INSTRUCTION.md` | Инструкция по локальной RAG-автоматизации | Пользователь |

**Важно:** `CLAUDE.md` **не существует** в репозитории. Аналогичную роль играет `AGENTS.md` — он явно адресован AI-агентам (любым, не только Claude).

### 1.2 Уровень docs/ (3 файла) — ядро процесса

| Файл | Назначение |
|---|---|
| `docs/context.md` | Текущее состояние проекта + «Что изменилось недавно» + «Что осталось» |
| `docs/decisions.md` | Журнал архитектурных решений в хронологическом порядке (с обоснованием) |
| `docs/todo.md` | Список задач: «Сейчас», «Далее», «Когда вернуться» |
| `docs/glossary.md` | Словарь терминов проекта (ФТТ, ЦТА, ПР, Паспорт ИС, СоИ и т.п.) |

Это **главный цикл обновления** — см. раздел 2.

### 1.3 Подкаталоги docs/

| Подкаталог | Файлов | Содержание |
|---|---|---|
| `docs/architecture/` | 3 | `ARCHITECTURE.md`, `FOLDER_STRUCTURE.md`, `MEETING_ARTIFACTS_PIPELINE.md` |
| `docs/operations/` | 4 | `RAG_PIPELINE.md`, `MEETING_PIPELINE.md`, `BACKUP_AND_RETENTION.md`, `WATCHDOG.md` |
| `docs/product/` | 8 | `PRODUCT_VISION_AND_PLAN.md`, `PRODUCT_APPROACH.md`, `ROADMAP.md`, `BACKLOG.md`, `PROJECT_STAGES_AND_FTT.md`, `PROJECT_TAXONOMY.md`, `PROJECT_ONLY_CHATBOT_MVP.md`, `PARALLEL_WORK_WHILE_RAG_BUILDS.md` |
| `docs/quality/` | 7 | `EVALUATION_PLAN.md`, `QUERY_FEEDBACK_LOOP.md`, `rag_eval_*.md`, `project_only_chatbot_smoke_questions.md` |
| `docs/references/` | 3 | `SPEAKR_REFERENCE.md`, `WHISPERDESK_EXPERIMENT.md`, `WHISPERX_EXPERIMENT.md` |
| `docs/security/` | 1 | `PRIVACY_AND_DATA.md` |
| `docs/templates/` | 2 | `MEETING_CARD.md`, `DOCUMENT_GENERATION_BRIEF.md` |
| `docs/subprojects/asu-june-bot/` | 11 | Полный док-набор подпроекта (`README/context/decisions/architecture/mvp/roadmap/todo/eval_questions/chunking_strategy/RUNBOOK_V2/runbook_v2`) |
| `docs/review/` | 7 текущих + план | Этот серия артефактов |

### 1.4 Один абзац на каждый главный документ

| Файл | Что описывает |
|---|---|
| `docs/architecture/ARCHITECTURE.md` | Общая архитектурная карта: модули, потоки данных. |
| `docs/architecture/FOLDER_STRUCTURE.md` | Объясняет назначение каждой папки на верхнем уровне. |
| `docs/architecture/MEETING_ARTIFACTS_PIPELINE.md` | Целевая архитектура pipeline артефактов встречи. |
| `docs/operations/RAG_PIPELINE.md` | Эксплуатация полного RAG-build: 01→02→03→05. |
| `docs/operations/MEETING_PIPELINE.md` | Эксплуатация обработки встреч: 06/07/08. |
| `docs/operations/BACKUP_AND_RETENTION.md` | Что бэкапить, что удалять; политика хранения медиа. |
| `docs/operations/WATCHDOG.md` | `monitor_rag.ps1` поведение, инварианты. |
| `docs/product/PRODUCT_VISION_AND_PLAN.md` | Long-term vision + module breakdown. |
| `docs/product/PRODUCT_APPROACH.md` | Принципы продуктовой работы: local-first, citations, refusal-on-empty. |
| `docs/product/ROADMAP.md` | High-level roadmap. |
| `docs/product/BACKLOG.md` | Backlog продуктовых задач. |
| `docs/product/PROJECT_STAGES_AND_FTT.md` | **Рабочий чек-лист**: MA-00..MA-11, FTT-MA-01..21, статусы. |
| `docs/product/PROJECT_TAXONOMY.md` | Реестр этапов проекта АСУ (PRJ-01..N) и типов документов. |
| `docs/product/PROJECT_ONLY_CHATBOT_MVP.md` | Дорожная карта project-only чата (MVP `09_chat.py`). |
| `docs/product/PARALLEL_WORK_WHILE_RAG_BUILDS.md` | План работ, которые можно вести пока идёт сборка RAG. |
| `docs/quality/EVALUATION_PLAN.md` | Метаплан оценки качества. |
| `docs/quality/QUERY_FEEDBACK_LOOP.md` | Процесс логирования→разметки→коррекции первых 100 запросов. |
| `docs/quality/rag_eval_questions.md` | Стартовый набор контрольных вопросов с ожидаемыми источниками. |
| `docs/quality/rag_eval_baseline_clean_2026-05-07.md` | Текущий baseline (5153 chunks, чистый корпус). |
| `docs/quality/rag_eval_baseline_2026-05-07.md` | Исторический baseline до чистки. |
| `docs/quality/rag_eval_report_template.md` | Шаблон отчёта по eval-прогону. |
| `docs/quality/project_only_chatbot_smoke_questions.md` | Smoke-вопросы для 09_chat (проектные + внепроектные). |
| `docs/references/SPEAKR_REFERENCE.md` | Идеи UI/UX из Speakr (см. артефакт №7). |
| `docs/references/WHISPERDESK_EXPERIMENT.md` | Эксперимент live-ASR (см. артефакт №7). |
| `docs/references/WHISPERX_EXPERIMENT.md` | Эксперимент word-level ASR (см. артефакт №7). |
| `docs/security/PRIVACY_AND_DATA.md` | Что не уходит в Git, локальность данных. |
| `docs/templates/MEETING_CARD.md` | Человекочитаемый шаблон папки встречи (соответствие с `meeting.schema.json`). |
| `docs/templates/DOCUMENT_GENERATION_BRIEF.md` | Шаблон brief'а для генерации документа (Паспорт ИС, ПМИ и т.п.). |

### 1.5 docs/examples/

В корневом `AGENTS.md` нет упоминаний `docs/examples/`, но он существует и содержит `meeting.new.example.json` — пример валидной карточки встречи. Это **эталон**, по которому пользователь создаёт новые `meeting.json`.

## 2. Трёхфайловый Цикл: Decisions ↔ Context ↔ Todo

### 2.1 Декларированный workflow

Из `AGENTS.md`:

> **Восстановление контекста:**
> - Перед изменениями прочитай `README.md`, `AGENTS.md`, `docs/context.md` и `docs/todo.md`.
> - В новом треде дополнительно посмотри `git log --oneline -10`.
>
> **Ритуал завершения дня:**
> 1. Обнови `docs/context.md`.
> 2. Обнови `docs/todo.md`.
> 3. Выполни `git status --short`.
> 4. Если изменения готовы и безопасны, сделай commit и push.

И отдельно:

> Перед завершением рабочей сессии обновляй `docs/context.md`: что изменилось и что осталось.
> Поддерживай `docs/todo.md` в актуальном состоянии.

### 2.2 Реальные роли трёх файлов

| Файл | Тон | Структура | Когда обновляется |
|---|---|---|---|
| `decisions.md` | Решения с обоснованием («Решение: X. Почему: …») | Хронологический список, секции по датам `## YYYY-MM-DD - Title` | При **принятии** архитектурного решения |
| `context.md` | Снимок текущего состояния | «Текущее состояние», «Что изменилось недавно», «Что осталось», «Восстановление контекста в новом треде» | **Каждую сессию** (в идеале) |
| `todo.md` | Список задач | «Сейчас», «Далее», «Когда вернуться», «Продуктовые следующие шаги» | По мере выполнения / изменения планов |

### 2.3 Как фактически работает цикл

**Поток обновлений (по таймстампам и содержанию):**

1. Принимается решение → запись в `decisions.md` с датой (например, `2026-05-12 - Быстрый профиль Project-Only Chatbot CLI`).
2. Реализация попадает в код.
3. `context.md::Что изменилось недавно` пополняется кратким описанием.
4. `todo.md::Сейчас` обновляется (выполненные пункты убираются, новые добавляются).
5. Связанные подробные документы (`PROJECT_STAGES_AND_FTT.md`, `PRODUCT_VISION_AND_PLAN.md`) обновляются точечно.

**Что хорошо:**
- `decisions.md` — самый строгий из трёх: 24 датированных решения, каждое имеет шаблон `Решение: X. Почему: bullet list`. Никаких удалений старых решений; уточнения добавляются датированными подзаписями («Уточнение от 2026-05-07: …»).
- `context.md::Важные файлы` — поддерживается актуальным; содержит one-line per file для всех ключевых docs/scripts/configs.
- `context.md::Что изменилось недавно` — добавочный append-only журнал; ничего не теряется.
- `todo.md` структурирован по горизонтам (Сейчас/Далее/Когда вернуться).

**Что хуже:**
- `decisions.md` ссылается на состояния кода, которые с тех пор изменились (см. артефакт №6) — но **без уточнения**, что код разошёлся. Например, decision `2026-05-07 Live-Транскрибация Хранит Раздельные Дорожки` остаётся без пометки, что live pipeline так и не реализован.
- `context.md::Что осталось` — частично пересекается с `todo.md::Далее`, дублирование.
- `todo.md::Сейчас` накапливает пункты-долгожители («Принять порог приемки FTT-MA-07 на основе baseline 9/5/1»), которые там 5+ недель — это не «сейчас», а stale (см. раздел 6).

### 2.4 Промпт восстановления контекста

В `context.md` явно прописан текст для нового треда:

```text
Прочитай README.md, AGENTS.md, docs/context.md, docs/todo.md и
git log --oneline -10. Восстанови контекст проекта и предложи
следующий шаг.
```

И отдельный для подпроекта:

```text
Прочитай README.md, AGENTS.md, docs/context.md, docs/todo.md и
все файлы docs/subprojects/asu-june-bot/. Восстанови контекст
подпроекта Asu June Bot и предложи следующий практический шаг.
```

Это **позитивная практика** — формализованный onboarding для AI-сессии.

## 3. `AGENTS.md` Как Governance Contract

Полный документ — 44 строки. Три блока правил:

### 3.1 Восстановление контекста (3 пункта)

Уже разобрано в 2.4.

### 3.2 Работа с Git (8 пунктов)

| Правило | Что enforces |
|---|---|
| Фиксируй значимые изменения | Регулярные коммиты |
| Небольшие коммиты с понятными сообщениями | Хорошая история |
| Проверяй `git status --short` перед изменениями | Чтобы не потерять чужую работу |
| Не перезаписывай изменения пользователя без просьбы | Защита от агрессивных rebase |
| Не коммить секреты, `.env`, локальные конфиги, build-артефакты, медиа | Гигиена репозитория |
| Перед завершением сессии — обновляй `context.md` | Цикл 2.3 |
| Поддерживай `todo.md` | Цикл 2.3 |
| В конце сессии — показывай `git status` | Прозрачность |

### 3.3 Правила MeetingAgent (8 пунктов)

| Правило | Что enforces |
|---|---|
| Локальность по умолчанию | Local-first архитектура |
| Не коммить `config.yaml`, `data/`, `logs/`, `vector_db/`, `watched_folder/`, `.venv/` | Гигиена + privacy |
| `options.num_ctx=8192` в каждом Ollama embedding | Соответствие `decisions.md 2026-05-06 bge-m3 С num_ctx 8192` |
| Не менять `embedding_model="bge-m3"` в cache без миграции | Сохранение валидного cache |
| Сохранять resumability, не удалять `embeddings_cache.jsonl` | `decisions.md 2026-05-06 Сохранять Embedding Cache` |
| Watchdog перезапускает Ollama, не build_index.py | `decisions.md 2026-05-06 Мониторинг Перезапускает Ollama` |
| Предпочитай продуктовые документы и небольшие шаги большим переписываниям | Эпистемическая дисциплина |

### 3.4 Что в AGENTS.md отсутствует

- Никаких правил для подпроекта `asu_june_bot`.
- Никаких правил для встреч (06/07/08), включая schema validation.
- Никаких правил для тестирования (потому что тестов нет — см. артефакт №6).
- Никакого hook'а / git hook'а / CI, который реально enforce'ит правила. Всё на честности агента.

## 4. Schema Как Gating Contract: Positive Example

В отличие от документации, **JSON-схемы реально enforced кодом**. Это **единственный** механизм валидации контрактов в репозитории.

### 4.1 Пять JSON-схем

```
configs/schemas/
├── meeting.schema.json                  # карточка встречи
├── meeting.decisions.schema.json        # решения встречи
├── meeting.tasks.schema.json            # задачи
├── meeting.risks.schema.json            # риски
└── meeting.open_questions.schema.json   # открытые вопросы
```

Все используют Draft 2020-12 (`https://json-schema.org/draft/2020-12/schema`).

### 4.2 Где валидация enforced

| Скрипт | Где валидирует |
|---|---|
| `06_transcribe_meeting.py:53,56` | `validate_schema` (через `jsonschema.Draft202012Validator`); вызывается **3 раза**: на входе (`:337`), после перехода `processing_status=transcribing` (`:360`), на выходе (`:393`). |
| `07_generate_meeting_artifacts.py:110-113` | То же. Валидирует `meeting.json` + **каждый артефакт** (`decisions.json`, `tasks.json`, `risks.json`, `open_questions.json`) против соответствующей схемы (`:1006`). |
| `08_process_meeting_pipeline.py` | Использует `validate_schema` через импорт из `07_generate_meeting_artifacts` (артефакты валидируются на финальной записи). |

### 4.3 State machine через `processing_status`

`06_transcribe_meeting.py:77 ensure_status_allows_run`:

```python
if status == STATUS_NEW:
    return
if force and status in {TRANSCRIBED, FAILED, TRANSCRIBING}:
    return
if status == STATUS_TRANSCRIBED:
    # отказ без --force
if status in {STATUS_FAILED, STATUS_TRANSCRIBING}:
    # отказ без --force
```

`08_process_meeting_pipeline.py:203 ensure_status_allows_run`:

```python
if status == STATUS_SUMMARIZED and not force:
    return refuse
if status == STATUS_PROCESSING and not force:
    return refuse  # уже идёт другая обработка
```

Это **работающий state machine**:
- `new → transcribing → transcribed → processing → summarized` (или `failed` на любом шаге).
- Возврат назад **только через `--force`**.
- Schema-валидация **до** мутации гарантирует, что невалидный объект не попадёт в файл.

### 4.4 Что схема НЕ enforces

(Уже разобрано в артефактах №3 и №6.)

- **Семантическая консистентность** между `memo.md`/`protocol.md` и JSON-артефактами. Decisions.md декларирует «MD = представление JSON», но это **не enforced** кодом.
- **Соответствие `source_refs[].segment_index`** реальному `segments.jsonl`. **Enforced только в 08** (через `collect_source_ref_pool`), не в 07.
- **Уникальность `meeting_id`** при создании.
- **Глобальная уникальность** `decision_id`/`task_id`/`risk_id`/`question_id` (они только локально уникальны).

### 4.5 Schema versioning

Из `decisions.md 2026-05-07`:

> `schema_version` в `meeting.json` фиксируется как `1` до появления осознанной несовместимой схемы. Новая версия схемы выпускается только вместе с описанием изменений и будущим upgrade-скриптом для старых карточек.

Текущее состояние: все 5 схем имеют `"schema_version": {"const": 1}`. Никаких миграций ещё не было.

**Upgrade-скрипт не существует** — это контракт на будущее. Если когда-то понадобится bump до v2, потребуется отдельный migration script (его нет ни в roadmap, ни в todo).

## 5. Где Цикл Сломался

### 5.1 Decisions без обновления статуса реализации

Decisions.md описывает **решения**, не **состояние**. Некоторые решения требуют функциональности, которая не была реализована — но decision остался без пометки.

| Решение | Дата | Что декларировано | Реальность |
|---|---|---|---|
| Live-транскрибация хранит раздельные дорожки MIC и SYS | 2026-05-07 | `MIC`/`SYS` источники истины, `MIX` производный | Live pipeline не существует; `segments.jsonl::source` всегда `MIX` |
| В RAG индексируются артефакты встречи | 2026-05-07 | memo, protocol, decisions, tasks, risks, open_questions + transcript | Incremental indexer не существует |
| Markdown-карточка = представление JSON-артефактов | 2026-05-07 | MD производный от JSON | `07/08` рендерят MD отдельным LLM-вызовом, без валидации соответствия |
| Retention с `protected`-политикой | 2026-05-07 | `default`/`protected` хранение | Ротация медиа не реализована |

**Это не баги** — это решения, которые **обогнали реализацию**. Decisions.md как историческая запись работает; как **state-of-truth** для текущей системы — нет.

### 5.2 Todo.md::Сейчас как «long-term backlog»

Пункты из `todo.md::Сейчас`, которые не выполнены 5+ недель (по сравнению с датой `Обновлено: 2026-05-12`):

| Пункт | Сколько висит |
|---|---|
| Принять порог приёмки FTT-MA-07 на основе `9 hit / 5 partial / 1 miss` | с 2026-05-07 → 5+ недель |
| Разобрать слабые вопросы baseline: ПМИ, инфраструктурные ограничения, архитектурная записка | с 2026-05-07 |
| Проверить полноту индексации ПМИ | с 2026-05-07 |
| Прогнать `09_chat.py` локально на быстром профиле | с 2026-05-12 |
| Подобрать `--score-threshold` для project-only отказов | с 2026-05-12 |

Семантически они должны быть в «Далее» или в отдельной секции «Stale» — фактически «Сейчас» превратился в «Текущий бэклог».

### 5.3 Дублирование между context.md::Что осталось и todo.md

Прямые дубликаты:

| context.md «Что осталось» | todo.md «Сейчас» / «Далее» |
|---|---|
| «Принять порог приёмки FTT-MA-07» | То же |
| «Ввести метаданные source_type» | То же |
| «Проверить ПМИ индексацию» | То же |
| «Прогнать 100 реальных запросов» | То же |

Это не критично, но создаёт два места, где надо синхронно обновлять одну запись.

### 5.4 Roadmap дублируется в трёх местах

| Документ | Что описывает |
|---|---|
| `docs/product/ROADMAP.md` | (краткий roadmap, не разворачивал) |
| `docs/product/PROJECT_STAGES_AND_FTT.md` | MA-00..MA-11 + FTT-MA-01..21 (наиболее подробный) |
| `docs/product/PRODUCT_VISION_AND_PLAN.md` | Видение + module breakdown + roadmap |
| `docs/subprojects/asu-june-bot/roadmap.md` | Roadmap подпроекта (этапы 0..6) |
| `docs/todo.md::Продуктовые следующие шаги` | Поэтапный план продукта |

5 мест для roadmap'а — потенциальный источник расхождений.

### 5.5 Документация для несуществующего кода

Подробно разобрано в артефакте №6:
- `scripts/00_healthcheck.py`, `scripts/05_process_meeting.py`, `scripts/asu_june_bot_chat.py`, `scripts/asu_june_bot_build_index_v2.py` — упомянуты в docs, не существуют.
- `configs/schemas/classification.schema.json` — упомянута, не существует.

**Все эти упоминания — в форме «Добавить», «Создать», «-> future:»**, что синтаксически корректно (roadmap), но конкретный пример из `mvp.md:299` — `python scripts\asu_june_bot_chat.py "Какие интеграции..."` — создаёт **иллюзию готовности**.

## 6. Свежесть Документации (Date Stamps)

`AGENTS.md` явно требует поддерживать `context.md` и `todo.md`. Косвенно — все docs должны эволюционировать. Посмотрим на актуальные timestamps:

### 6.1 Самые свежие (2026-05-12)

- `docs/context.md`
- `docs/todo.md`
- `docs/product/PROJECT_ONLY_CHATBOT_MVP.md`
- `docs/product/PROJECT_STAGES_AND_FTT.md`
- `docs/quality/project_only_chatbot_smoke_questions.md`
- Все 11 файлов `docs/subprojects/asu-june-bot/*` (включая RUNBOOK_V2.md от 2026-05-13)

### 6.2 От 2026-05-07 (потенциально устаревшие)

| Файл | Возможные расхождения |
|---|---|
| `docs/glossary.md` | Если добавились новые термины — не отражены |
| `docs/product/PROJECT_TAXONOMY.md` | Реестр этапов проекта может быть неактуален |
| `docs/product/PARALLEL_WORK_WHILE_RAG_BUILDS.md` | Содержит ссылки на несуществующие `00_healthcheck.py`, `05_process_meeting.py`, `classification.schema.json` (см. артефакт №6) |
| `docs/product/PRODUCT_VISION_AND_PLAN.md` | Roadmap может расходиться с PROJECT_STAGES_AND_FTT.md (2026-05-12) |
| `docs/operations/BACKUP_AND_RETENTION.md` | Retention-политика декларирована, но ротация медиа не реализована (см. артефакт №6) |
| `docs/references/WHISPERDESK_EXPERIMENT.md` | Зафиксировал live-профиль, но live pipeline не реализован |
| `docs/quality/rag_eval_questions.md` | Стартовый набор вопросов; неизвестно, прогонялся ли заново |
| `docs/quality/rag_eval_report_template.md` | Шаблон отчёта |
| `docs/quality/rag_eval_baseline_*.md` | Исторические снимки — корректно остаются на старой дате |

### 6.3 Без timestamp

| Файл | Заметка |
|---|---|
| `README.md` | Нет «Обновлено:» |
| `AGENTS.md` | Нет |
| `RAG_AUTOMATION_INSTRUCTION.md` | Есть `Обновлено: 2026-05-07.` |
| `docs/architecture/*.md` | Не проверял timestamp'ы — `[?]` |
| `docs/operations/{RAG_PIPELINE,MEETING_PIPELINE,WATCHDOG}.md` | Не проверял — `[?]` |
| `docs/product/{BACKLOG,PRODUCT_APPROACH,ROADMAP}.md` | Не проверял — `[?]` |
| `docs/security/PRIVACY_AND_DATA.md` | Не проверял — `[?]` |
| `docs/templates/*.md` | Не проверял — `[?]` |
| `docs/subprojects/asu-june-bot/{RUNBOOK_V2,runbook_v2}.md` | **Дубликат?** Имя отличается только регистром; 2026-05-13 vs 2026-05-12 — `[?]` |
| `docs/quality/EVALUATION_PLAN.md`, `QUERY_FEEDBACK_LOOP.md` | Не проверял — `[?]` |

### 6.4 Аномалия: дублирующиеся файлы

`docs/subprojects/asu-june-bot/` содержит **оба**:
- `RUNBOOK_V2.md` (2026-05-13)
- `runbook_v2.md` (2026-05-12)

На case-sensitive файловой системе это два разных файла. На case-insensitive (Windows / macOS default) это **коллизия** при клонировании. Один из них, вероятно, остался от переименования и не удалён.

## 7. Сводка Drift'ов Из Артефактов №3-7

Концентрирую все обнаруженные расхождения «доки vs код» в одной таблице:

| Расхождение | Декларация | Реальность | Артефакт |
|---|---|---|---|
| `processing_status` enum 8 значений | meeting.schema.json | 5 реально пишутся (no `classified`, `indexed`) | №3, №6 |
| `meeting.json::classification` | meeting.schema.json + PROJECT_TAXONOMY | Никем не пишется | №3, №6 |
| `meeting.json::links` | meeting.schema.json | Никем не пишется | №3 |
| `meeting.json::rag.indexed_artifacts[]` | meeting.schema.json + decisions.md 2026-05-07 | Никем не пишется | №3, №6 |
| `meeting.json::artifacts.classification_report` | meeting.schema.json | Никем не пишется | №3 |
| `segments.jsonl::source` enum `MIC`/`SYS` | meeting.schema.json + decisions.md 2026-05-07 | Всегда `MIX` | №3, №6 |
| `audio_tracks=[MIC,SYS]` live MVP | decisions.md 2026-05-07 | Live pipeline не существует | №6 |
| Markdown = представление JSON | decisions.md 2026-05-07 | Render отдельным LLM-вызовом, без валидации | №6 |
| Retention `protected` ротация | decisions.md 2026-05-07 + BACKUP_AND_RETENTION.md | Ротация не реализована | №6 |
| `config.yaml::transcription:` / `live_transcription:` | config.example.yaml | Никем не читается | №6 |
| `config.yaml::rag.search_backend` | config.example.yaml | Никем не читается, backend hardcoded | №6 |
| `paths.vector_db` | config.example.yaml | Рудимент ChromaDB | №6 |
| `paths.watched_folder` | config.example.yaml + MEETING_PIPELINE.md | Watcher не существует | №6 |
| `scripts/00_healthcheck.py` | PARALLEL_WORK.md «Добавить» | Не существует | №6 |
| `scripts/05_process_meeting.py` | PARALLEL_WORK.md «Создать» | Не существует (заменён 08) | №6 |
| `scripts/asu_june_bot_chat.py` | mvp.md / todo.md / roadmap.md | Не существует | №6 |
| `scripts/asu_june_bot_build_index_v2.py` | context.md / chunking_strategy.md | Не существует | №6 |
| `configs/schemas/classification.schema.json` | PARALLEL_WORK.md «Создать» | Не существует | №6 |
| asu_june_bot v2 retrieval | артефакты №3, №4 | Не существует — search читает main corpus | №7 |
| `src/meeting_agent/` 14 пустых stub | FOLDER_STRUCTURE.md «будущая структура» | Только `.gitkeep` | №6 |
| `tests/` | — | Не существует | №6 |
| Dual sensitive-filter | rag_common + 09_chat | Разные паттерны, разная семантика блокировки | №3, №6 |

**22 точечных drift'а.** Не критичных багов, но архитектурный мисалигнмент между декларациями и кодом.

## 8. Что Не Было Проверено

- **Timestamp'ы части документов** в `docs/architecture/`, `docs/operations/{RAG,MEETING}_PIPELINE.md`, `docs/security/`, `docs/templates/` — не сверял с датой соответствующих изменений в коде. `[?]`
- **Содержание `docs/product/ROADMAP.md`** — упомянуто, но не разворачивал. Не проверял конфликты с PROJECT_STAGES_AND_FTT.md. `[?]`
- **`docs/product/BACKLOG.md`** — не разворачивал. `[?]`
- **`docs/product/PRODUCT_APPROACH.md`** — не разворачивал. `[?]`
- **`docs/quality/EVALUATION_PLAN.md` vs реальный harness** — eval-harness не реализован (артефакт №6), но не проверял подробно, что именно описывает EVALUATION_PLAN. `[?]`
- **`docs/operations/WATCHDOG.md`** — поведение `monitor_rag.ps1` не сверял с этим документом. Артефакт №5 описывал поведение из PowerShell-источника. `[?]`
- **`docs/templates/DOCUMENT_GENERATION_BRIEF.md`** — какой контракт описывает; есть ли у него реализация. Учитывая, что FTT-MA-14 «Генерация документов» — Запланировано, скорее всего контракт без кода, но не проверял. `[?]`
- **`docs/subprojects/asu-june-bot/{RUNBOOK_V2.md, runbook_v2.md}`** — содержимое и причина дубликата имени с разным регистром. `[?]`
- **Все ли relative-ссылки в docs/ работают** (т.е. ведут на существующие файлы) — не запускал doc-link checker. `[?]`
- **README.md timestamp** — есть ли политика обновления самого README. `[?]`
- **`.env.example`** — упомянут в `context.md::Важные файлы`, не проверял состав. `[?]`
- **`config.example.yaml::ollama.chat_model`** — упомянут как `qwen3:8b`, но конкретные значения в подпроекте `qwen3:4b` (артефакт №7). Не сверял, как пользователь должен переключать модели. `[?]`
