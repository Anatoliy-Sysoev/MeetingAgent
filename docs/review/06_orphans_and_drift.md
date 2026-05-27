# Каталог Орфанов И Расхождений

Артефакт №6 серии полного ревью. Сводит **всё, что декларировано, но не реализовано** (или наоборот: реализовано, но не задокументировано).

Цель: один файл, по которому можно сразу понять, какие части документации, схемы, конфига и кода являются «тенями» — упоминают сущности, которых нет, или живут в противоречии с реальностью.

Полнота: артефакт фиксирует **обнаруженные** расхождения. Не претендует на исчерпывающий audit; следующий проход с инструментами (pyright, vulture, doc-link checker) поднимет больше.

## Содержание

1. [Сводка по категориям](#1-сводка-по-категориям)
2. [Орфаны конфига: dead config keys](#2-орфаны-конфига-dead-config-keys)
3. [Орфаны кода: dead functions, дублирующие фильтры](#3-орфаны-кода-dead-functions-дублирующие-фильтры)
4. [Орфаны схем: RESERVED-секции без продьюсеров](#4-орфаны-схем-reserved-секции-без-продьюсеров)
5. [Орфаны документации: ссылки на несуществующие файлы](#5-орфаны-документации-ссылки-на-несуществующие-файлы)
6. [Орфаны структуры: пустые папки и стабы](#6-орфаны-структуры-пустые-папки-и-стабы)
7. [Legacy-упоминания: ChromaDB, FAISS, Qdrant](#7-legacy-упоминания-chromadb-faiss-qdrant)
8. [Code-vs-decisions противоречия](#8-code-vs-decisions-противоречия)
9. [Mention-vs-implementation: что обещано в README/CLAUDE.md](#9-mention-vs-implementation-что-обещано-в-readmeclaudemd)
10. [Самоошибки серии ревью](#10-самоошибки-серии-ревью)
11. [Что не было проверено](#11-что-не-было-проверено)

## 1. Сводка По Категориям

| Категория | Найдено | Серьёзность |
|---|---|---|
| Dead config keys | 9 ключей в `config.example.yaml` (включая целые секции `transcription:`, `live_transcription:`) | средняя — путают новых разработчиков |
| Dead code | 1 helper-функция, фактически используется только внутри своего модуля | низкая |
| Дублирующие подсистемы | 2 sensitive-фильтра с разными паттернами | средняя — поведение зависит от точки входа |
| Reserved-секции схем | 9 контрактов в `meeting.schema.json` без продьюсера | средняя — описывают будущее, но без маркировки «pending» |
| Несуществующие скрипты в docs | 4 имени | низкая — все помечены как «future/добавить» |
| Несуществующие схемы в docs | 1 (`classification.schema.json`) | низкая — roadmap |
| Пустые папки-стабы | 14 поддиректорий `src/meeting_agent/` + `watched_folder/` | низкая, но загромождает структуру |
| Legacy ChromaDB | 17 упоминаний в 12 файлах | средняя — явно помечены как deprecated, но `vector_db` ещё в `paths` |
| Legacy FAISS | 7 упоминаний, всегда как «future option» | низкая |
| Decisions.md противоречия с кодом | 3 решения, требующие функциональности, которой нет | высокая — пользователь ожидает поведения, которого нет |
| Самоошибки артефакта №5 (defaults 09_chat) | 5 неверных default'ов | средняя — нужно поправить |

## 2. Орфаны Конфига: Dead Config Keys

Сверка `config.example.yaml` ↔ реально читаемые `cfg["…"]` в Python.

| Ключ конфига | Декларация | Реально читается? | Что используется вместо |
|---|---|---|---|
| `rag.search_backend: "numpy"` | "Бэкенд поиска: numpy / faiss / hybrid" | **Нет**, ни в одном скрипте. | Backend hardcoded — `04_query.py`/`09_chat.py` всегда пытаются `NumpyRagIndex.load`, fallback на JSONL. |
| `rag.query_top_k` (если задан) | Не задан в example, но упоминается в `04_query.py:242` | `04_query.py:242` читает `cfg["rag"]["top_k"]`, не `query_top_k`. | Только `rag.top_k`. |
| `rag.top_k` | Default `12` | **Да**, `04_query.py:242`. | — |
| `rag.max_context_chars` | Default `24000` | **Да**, `04_query.py:243`. | В `09_chat.py` используется свой CLI default 6000, не из конфига. |
| `generation.temperature` | `0.2` | **Да**, `04_query.py:237`. | В `07/08` свои default'ы (`0.1`-`0.2`), читают через `--temperature` или config. |
| `generation.top_p` | `0.9` | **Да**, `04_query.py:238`. | Аналогично. |
| `transcription.*` (вся секция: model, language, compute_type, device, beam_size, vad_filter) | Профиль ASR offline | **Нет, ни одной строки не читается**. | `06_transcribe_meeting.py` и `08_process_meeting_pipeline.py` берут все ASR-параметры из CLI args (`--asr-model`, `--asr-compute-type`, `--asr-language`) и **хардкодят** `beam_size=3, vad_filter=False`. |
| `live_transcription.*` (вся секция) | Профиль live ASR | **Нет**, live pipeline не существует в коде. | — |
| `paths.vector_db: "vector_db"` | Путь устаревшей папки ChromaDB | **Нет**, не используется ни одним скриптом. | Только косвенно упоминается в комментариях. |
| `paths.watched_folder: "watched_folder"` | Inbox для новых записей | Только `rag_common.ensure_runtime_dirs:39` `mkdir`-ает. **Watcher не реализован.** | — |
| `paths.source_links` | Не задан в example | `09_chat.py:252` читает с default `"data/source_links.json"`. | — |
| `ollama.embedding_num_ctx` | `8192` | **Да** (03, 04, 09). | — |
| `ollama.keep_alive` | `"24h"` | **Да** (03, 04, 09). | — |

**Вывод:** примерно **40-50%** ключей `config.example.yaml` не читаются. Главные орфаны — `transcription:` и `live_transcription:` (целые секции).

### 2.1 Рекомендация (для будущего, не действие)

1. Удалить `transcription:` и `live_transcription:` из примера; добавить комментарий «ASR-параметры задаются через CLI скриптов 06/08, см. их `--help`».
2. Удалить `rag.search_backend` или начать его реально использовать (выбирать backend по значению).
3. Удалить `paths.vector_db` или комментарий — это рудимент.
4. Решить судьбу `watched_folder/` — либо реализовать watcher, либо удалить.

## 3. Орфаны Кода: Dead Functions, Дублирующие Фильтры

### 3.1 `rag_common.is_sensitive_query`

Определена в `scripts/rag_common.py:81`. **Не импортируется ни одним другим скриптом.** Используется только внутри `rag_common.append_query_log:89` (модульно).

Это **не настоящий орфан** — функция работает; но никто за пределами модуля её не зовёт. Архитектурно это значит: единственный gate sensitive-фильтра в общем коде — это `append_query_log`. Все остальные точки (`09_chat`) реализуют свой фильтр.

### 3.2 Дублирующий sensitive-фильтр в `09_chat.py`

| Локация | Константа | Содержимое | Когда срабатывает |
|---|---|---|---|
| `rag_common.py:65` | `SENSITIVE_QUERY_PATTERNS` (12 паттернов) | `.env`, `config.yaml`, `пароль`, `password`, `token`, `токен`, `secret`, `секрет`, `system prompt`, `системный промпт`, `api key`, `ключ api` | В `append_query_log` — блокирует **запись в лог**. Не блокирует ответ. |
| `09_chat.py:38` | `SENSITIVE_PATTERNS` (≈ 20+ паттернов, включая всё из rag_common + extra: `developer message`, `инструкции модели`, `developer prompt`…) | расширенный | В `09_chat` блокирует **ответ** на этапе `is_sensitive_request` (отказ с `refusal_reason=sensitive_or_system_request`). При отказе запись в лог тоже подавляется (`09:634` проверяет `refusal_reason != REFUSAL_SENSITIVE`). |

**Проблема:** запросы через `04_query.py` (не через `09_chat`) проходят только узкий фильтр (`rag_common`). Если sensitive-запрос содержит `developer message`, он **залогируется** через `04`, но **не** через `09`.

Это не критический баг, но архитектурное расхождение: одна точка зрения на «sensitive» должна быть единственной. См. артефакт №2 (data flow) и №3 (схемы).

### 3.3 Другие функции `rag_common` — нет dead helpers

Проверка по `grep -wn <name> scripts/ --exclude rag_common.py`:

| Функция | Внешних вызовов |
|---|---|
| `sha256_file` | 4 |
| `normalize_text` | 18 |
| `safe_rel_id` | 2 |
| `is_under_excluded_dir` | 2 |
| `is_excluded_by_path_patterns` | 8 |
| `path_rel_to_project` | 2 |
| `read_text_guess` | 6 |
| `chunk_text` | 2 |
| `print_summary` | 4 |

Все используются как минимум двумя точками входа.

## 4. Орфаны Схем: RESERVED-Секции Без Продьюсеров

Дублируется со сводкой в артефактах №3 и №4; здесь собрано в одном месте для quick reference.

| Контракт | Где задан | Кто **должен** заполнять | Кто реально заполняет |
|---|---|---|---|
| `meeting.json::classification` (вся секция) | `meeting.schema.json:164-202` | Будущий классификатор | **Никто** |
| `meeting.json::classification.project_stage` (`PRJ-\d{2}`) | то же | то же | — |
| `meeting.json::classification.ftt_candidates[]` | то же | то же | — |
| `meeting.json::classification.document_candidates[]` | то же | то же | — |
| `meeting.json::classification.task_candidates[]` | то же | то же | — |
| `meeting.json::links` (related_documents/meetings/decisions) | `meeting.schema.json:204-226` | Будущий linker | **Никто** |
| `meeting.json::rag.indexed_artifacts[]` | `meeting.schema.json:269-274` | Будущий incremental RAG-indexer для встреч | **Никто** |
| `meeting.json::rag.no_index_artifacts[]` | то же | то же | **Никто** |
| `meeting.json::rag.last_indexed_at` | `meeting.schema.json:283-286` | то же | **Никто** |
| `meeting.json::artifacts.classification_report` | `meeting.schema.json:159-161` | Будущий classifier output | **Никто** |
| `meeting.json::processing_status` значения `classified`, `indexed` | `meeting.schema.json:114-125` | Классификатор + incremental RAG | **Никто** (только 5 из 8 значений реально пишутся) |
| `segments.jsonl::source` значения `MIC`/`SYS` | `meeting.schema.json::audio_tracks` | live-pipeline | `06`/`08` **всегда** пишут `MIX` |

**Итог:** в `meeting.schema.json` около 30% полей зарезервированы под несуществующие фичи. Schema validation проходит, потому что эти поля все `optional`, но архитектурно это смешивает «контракт текущей системы» с «roadmap».

## 5. Орфаны Документации: Ссылки На Несуществующие Файлы

### 5.1 Скрипты

| Имя | Где упомянуто | Контекст | Что есть в реальности |
|---|---|---|---|
| `scripts/00_healthcheck.py` | `docs/product/PARALLEL_WORK_WHILE_RAG_BUILDS.md:162` | "Добавить" | Не существует. |
| `scripts/05_process_meeting.py` | `docs/product/PARALLEL_WORK_WHILE_RAG_BUILDS.md:213, 390` | "Создать" / "Спроектировать" | Не существует. Заменён `08_process_meeting_pipeline.py` с другим именем. |
| `scripts/asu_june_bot_build_index_v2.py` | `docs/subprojects/asu-june-bot/chunking_strategy.md:31`, `context.md:37` | "-> future:" | Не существует. Hybrid retriever строится in-memory в `asu_june_bot_search.py`. |
| `scripts/asu_june_bot_chat.py` | `docs/subprojects/asu-june-bot/{roadmap.md:72, todo.md:248, mvp.md:111, mvp.md:299}` | "CLI" / пример команды | Не существует. Есть только `asu_june_bot_search.py`, который тестирует retrieval, но не чат. |

Все четыре упомянуты в roadmap-секциях («future», «добавить», «создать»). Это не «битые ссылки» в строгом смысле — пользователь не пытается их открыть как существующие. Но в `mvp.md:299` приведён конкретный пример команды `python scripts\asu_june_bot_chat.py "..."` — это создаёт **иллюзию готовности**. См. артефакт №7 (подпроект).

### 5.2 Схемы

| Имя | Где упомянуто | Контекст | Реальность |
|---|---|---|---|
| `configs/schemas/classification.schema.json` | `docs/product/PARALLEL_WORK_WHILE_RAG_BUILDS.md:96, 239` | "Создать" | Не существует. (Существуют только 5 meeting-*.schema.json.) |

### 5.3 Папки / артефакты

Текстовые упоминания папок/файлов, которые либо не существуют, либо существуют как stub:

| Имя | Где | Состояние |
|---|---|---|
| `vector_db/` | 17 мест (README, decisions, context, ARCHITECTURE, FOLDER_STRUCTURE, RAG_PIPELINE, todo, PARALLEL_WORK, PRIVACY) | **Может существовать или нет**; явно помечен как deprecated, но не удалён из `config.example.yaml`. |
| `watched_folder/` | docs/operations/MEETING_PIPELINE.md, docs/architecture/FOLDER_STRUCTURE.md, docs/todo.md, MEETING_CARD.md, decisions.md | Существует как **stub** (`.gitkeep` + README), watcher не реализован. |
| `data/source_links.json` | docs/operations/RAG_PIPELINE.md (упоминается как опциональный) | Существует только как читатель в `09_chat`; producer'а нет (см. артефакт №3). |

## 6. Орфаны Структуры: Пустые Папки И Стабы

### 6.1 `src/meeting_agent/`

```
src/meeting_agent/
  __init__.py
  api/.gitkeep
  classification/.gitkeep
  config/.gitkeep
  core/.gitkeep
  document_generation/.gitkeep
  extraction/.gitkeep
  ingest/.gitkeep
  integrations/.gitkeep
  meetings/.gitkeep
  observability/.gitkeep
  rag/.gitkeep
  storage/.gitkeep
  transcription/.gitkeep
```

**14 пустых поддиректорий**, только `__init__.py` имеет какой-то контент. Декларация: `docs/architecture/FOLDER_STRUCTURE.md:57` "будущая структура Python-пакета". Никаких импортов из `meeting_agent` ни в `scripts/`, ни внутри `src/` нет.

Контраст с `src/asu_june_bot/`, где есть рабочий код (`core/config.py`, `ingestion/models.py`, `retrieval/hybrid.py` и т.д.) и импорты в `scripts/asu_june_bot_*`.

**Резюме:** `src/meeting_agent/` — это **архитектурный плейсхолдер**. Можно оставить как roadmap-маркер, можно удалить до момента реального использования. Поведенчески не влияет ни на что.

### 6.2 `watched_folder/`

Только `.gitkeep` (1 байт) и `README.md` (195 байт). Watcher не реализован (FTT-MA-08 в roadmap).

### 6.3 `tests/`

Отсутствует. В корне репозитория **нет директории `tests/`** и **нет ни одного `test_*.py`**. Контраст с `pyproject.toml` или `requirements*.txt`, где могло бы быть `pytest`. Проверки качества — только ручные через `04_query.py --raw` и baseline-Markdown в `docs/quality/`.

## 7. Legacy-Упоминания: ChromaDB, FAISS, Qdrant

### 7.1 ChromaDB

**17 упоминаний в 12 файлах:**

| Файл | Строк | Тон |
|---|---|---|
| `README.md` | 2 | «без зависимости от ChromaDB», «устаревшая локальная папка» |
| `RAG_AUTOMATION_INSTRUCTION.md` | 3 | Явно описывает миграцию прочь от ChromaDB |
| `config.example.yaml` | 1 (комментарий) | «Устаревшая папка ChromaDB» |
| `docs/decisions.md` | 5 | 3 решения (`2026-05-06 chunk_id/db_id`, `2026-05-07 Numpy вместо Chroma`, `2026-05-07 vector_db не в Git`) |
| `docs/context.md` | 5 | История миграции |
| `docs/todo.md` | 1 | Заметка об нестабильности |
| `docs/architecture/{ARCHITECTURE,FOLDER_STRUCTURE}.md` | 2 | Папка `vector_db/` помечена устаревшей |
| `docs/operations/RAG_PIPELINE.md` | 1 | Явно: «не пересоздаёт ChromaDB» |
| `docs/product/PARALLEL_WORK_WHILE_RAG_BUILDS.md` | 1 | Правило «не трогать vector_db» помечено неактуальным |
| `docs/security/PRIVACY_AND_DATA.md` | 1 | Перечислено в исключениях |

**Код:** **0 импортов** ChromaDB. **0 вызовов** `chromadb.*`. `requirements.txt` (или `pyproject.toml`) **не должен** содержать `chromadb`. Не проверял прямо — но если есть, это тоже орфан.

**Состояние:** документация **корректно** описывает deprecation; единственная активная утечка — `paths.vector_db` в `config.example.yaml` и `chunks.jsonl::db_id` как «совместимое служебное поле».

### 7.2 FAISS

7 упоминаний, **все** как «future option»: `docs/todo.md:49`, `docs/decisions.md:123`, `docs/context.md:208`, `docs/quality/rag_eval_report_template.md:15`, `docs/subprojects/asu-june-bot/README.md:79`, `docs/product/PRODUCT_VISION_AND_PLAN.md:459`, `docs/product/PROJECT_STAGES_AND_FTT.md:33`.

**Код:** 0 импортов. Не используется.

### 7.3 Qdrant

3 упоминания, **все** в `docs/subprojects/asu-june-bot/{README.md:79, todo.md:253-263}` как «future option после numpy index v2».

**Код:** 0 импортов.

### 7.4 Прочие vector store

| Имя | Упоминаний |
|---|---|
| Pinecone | 0 |
| Weaviate | 0 |
| Milvus | 0 |
| MeetingAgentGPT | 0 |

## 8. Code-Vs-Decisions Противоречия

### 8.1 «Live-транскрибация хранит раздельные дорожки MIC и SYS» (decisions.md 2026-05-07)

> Для live MVP основные данные должны храниться как отдельные дорожки `MIC` и `SYS`, а `MIX` считается производным потоком.

**Реальность кода:**
- Live pipeline **не существует** в коде вообще.
- `06_transcribe_meeting.py` и `08_process_meeting_pipeline.py` всегда читают **один** медиафайл (через `get_source_media`) и пишут `source="MIX"` в `segments.jsonl::source` (`06:299`, `08:300+`).
- `meeting.schema.json::audio_tracks` enum `[MIC, SYS]` — никто не пишет.

**Серьёзность:** высокая, если пользователь ожидает функции live с раздельными дорожками. Низкая, если воспринимается как roadmap.

### 8.2 «В RAG индексируются артефакты встречи» (decisions.md 2026-05-07)

> Исходные медиа не индексируются; в RAG попадают memo, протокол, решения, задачи, риски, открытые вопросы и финальный transcript с metadata.

**Реальность кода:**
- Никакой incremental indexer для артефактов встречи **не реализован**.
- `meeting.json::rag.indexed_artifacts[]`, `rag.last_indexed_at`, `processing_status="indexed"` — **никем не пишутся**.
- `03_build_index.py` и `05_build_numpy_index.py` собирают индекс по `project_root` (через `manifest.jsonl`), но `meetings/<id>/` не включается, если только не лежит внутри `project_root`. По умолчанию (`config.example.yaml::project_root: "%USERPROFILE%/Desktop/PROJECT_DOCUMENTS"`) встречи **не входят** в путь.

**Серьёзность:** высокая для product expectations. Пользователь, который читает decisions.md, ожидает, что финальные артефакты встречи будут отвечать на запросы из чата — они не отвечают.

### 8.3 «processing_status: …classified, indexed» (meeting.schema.json)

Эти два значения enum'а **ни один скрипт не выставляет**. Только 5 из 8:
- `new` (вручную при создании карточки)
- `processing` (08:834)
- `transcribing` (06:356)
- `transcribed` (06:389)
- `summarized` (07/08)
- `failed` (06/07/08)

`classified` и `indexed` зарезервированы. Если пользователь фильтрует встречи по `processing_status=indexed`, всегда получит пустой набор.

### 8.4 «Markdown-карточка является представлением JSON-артефактов» (decisions.md 2026-05-07)

> Markdown являются представлением `artifacts/decisions.json`, `artifacts/tasks.json`, ...

**Реальность кода:**
- `07/08` генерируют `memo.md` и `protocol.md` через **отдельный LLM render-шаг** (`meeting_render_documents.md`), а не как механический рендер JSON.
- LLM может породить Markdown, который **расходится** с JSON. Никакой пост-валидации соответствия нет.

**Серьёзность:** средняя. Решение декларирует инвариант, который не enforced кодом.

## 9. Mention-Vs-Implementation: Что Обещано В README/CLAUDE.md

### 9.1 README.md

Список текущих скриптов в README.md соответствует реальности (`01-09 + asu_june_bot_*`). Не обнаружено упоминаний несуществующих скриптов в README.

### 9.2 CLAUDE.md

Не проверял подробно в этом артефакте; запланировано в №2 (data flow) и №8 (process & docs).

### 9.3 PROJECT_STAGES_AND_FTT.md статусы

Таблица FTT-MA-01..21 содержит статусы:
- «Готово» — MA-00 (основание).
- «Работает» — MA-01 (RAG-фундамент).
- «Следующий этап» — MA-02 (качество), MA-09 (project-only chatbot).
- «Начато» — MA-03 (карточка встречи), MA-04 (offline-транскрибация).
- «Запланировано» — MA-05/06/07/08/10.
- «Скаффолд» — MA-06 (memo/protocol generator).
- «Частично готово» — MA-11 (operations).

Эти статусы **выглядят корректными** относительно реального состояния кода, хотя «работает» / «начато» / «скаффолд» — субъективные категории.

## 10. Самоошибки Серии Ревью

### 10.1 Артефакт №5: неверные default'ы `09_chat.py`

В таблице 4.2 «Назначение / Default» для `09_chat.py` указаны:

| Флаг | Указано в №5 | Реально в коде | Источник |
|---|---|---|---|
| `--top-k` | 12 | **4** | `scripts/09_chat.py:24` `DEFAULT_TOP_K = 4` |
| `--max-context-chars` | 14000 | **6000** | `:25` `DEFAULT_MAX_CONTEXT_CHARS = 6000` |
| `--num-predict` | 1024 | **700** | `:26` `DEFAULT_NUM_PREDICT = 700` |
| `--timeout-sec` | 240 | **180** | `:27` `DEFAULT_TIMEOUT_SEC = 180` |
| `--expand-top-documents` | 2 | **1** | `:29` `DEFAULT_EXPAND_TOP_DOCUMENTS = 1` |

**Эти значения соответствуют решению `decisions.md 2026-05-12 Быстрый профиль Project-Only Chatbot CLI`** (`top_k=4, max_context_chars=6000, num_predict=700, timeout_sec=180`). Артефакт №5 описывал то, что я ожидал по умолчанию, не сверившись с `DEFAULT_*` константами.

**Действие:** правка артефакта №5 — отдельным коммитом после завершения №6.

### 10.2 Артефакт №3: общий заголовок описания `_metadata.jsonl`

Описано как «extracted_text/_metadata.jsonl»; путь корректный. Расхождений не найдено.

## 11. Что Не Было Проверено

- **`requirements.txt` / `pyproject.toml`** — есть ли там зависимости на ChromaDB / FAISS / Qdrant / другие vector store, которые не используются. `[?]`
- **Полная проверка docs-link integrity** — все ли relative-ссылки внутри `docs/**.md` ведут на существующие файлы. Не проверял через doc-link checker. `[?]`
- **`tools/` директория** — упомянута ли где-то. Беглый grep не нашёл ни упоминаний, ни самой папки. `[?]`
- **Прочие dead-code** — не запускал `vulture` или аналогичный статический анализатор; helper-функции проверены только в `rag_common`. В `asu_june_bot/*` и в больших скриптах (07, 08, 09) могут быть локальные dead functions. `[?]`
- **CLAUDE.md** — полное содержимое не разбиралось; запланировано в №8. `[?]`
- **Прошлые `data/` файлы / orphan binaries** — отсутствует, потому что `data/` исключена из Git. Если у пользователя на машине лежит `vector_db/<old>/chroma.sqlite3` — это локальный артефакт, не репозиторный. `[?]`
- **decisions.md vs PROJECT_STAGES_AND_FTT** — пересечение FTT-MA-XX упомянуто, не сверял каждое FTT с реальным кодом (только агрегатно через статусы). `[?]`
