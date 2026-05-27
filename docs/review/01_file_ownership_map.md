# Карта Файлов И Владельцев

Артефакт №1 из серии полного ревью репозитория (см. план ревью в чате; остальные артефакты появятся в `docs/review/`).

Цель документа — для каждого отслеживаемого файла дать:

- назначение в одну строку;
- кто вызывает / импортирует / читает его;
- статус по принадлежности к актуальному рабочему пути.

Документ описывает только то, что **физически есть в Git** (`git ls-files`, всего 141 файл на момент составления, ветка `claude/model-training-guide-CAfwU`).

## Как Читать

- Колонка **Кто вызывает** — конкретные файлы. Если пусто или указано «manual» — значит вызов идёт только вручную из README/инструкций, ни один скрипт его не вызывает.
- Колонка **Статус** использует условные обозначения:

  | Метка | Значение |
  | --- | --- |
  | `active` | Используется в текущем рабочем потоке (RAG build, chat, meeting pipeline, subproject pipeline). |
  | `dormant` | Код существует и работает, но к продуктовому потоку не подключён. Запускается только вручную. |
  | `legacy` | Старая ветка реализации, заменена новой, но не удалена. Можно вызвать, но не следует. |
  | `stub` | Только `.gitkeep` или пустая папка. Архитектурный задел без реализации. |
  | `deprecated` | Объявлен устаревшим в `docs/decisions.md`, физически отсутствует или не используется. |
  | `doc` | Текстовая документация. |
  | `config` | Конфигурация (YAML/JSON), потребляется кодом или только людьми. |
  | `schema` | JSON-схема валидации. |
  | `template` | Шаблон prompt или документа. |
  | `runtime` | Папка для локальных данных. Содержимое не в Git. |
  | `entrypoint` | Точка входа: PowerShell-скрипт или CLI Python. |

- В колонке **Кто вызывает** для Python-скриптов и `.ps1` приведены только реальные потребители из репозитория. Документация, упоминающая файл текстом, считается потребителем только если документ задаёт способ запуска (например, README с примерной командой).

## Сводка По Областям

| Область | Файлов в git | Активных | Dormant/Legacy | Stub | Doc-only |
| --- | ---:| ---:| ---:| ---:| ---:|
| Корень репозитория | 7 | 6 | 0 | 0 | 1 |
| PowerShell entrypoints | 7 | 5 | 0 | 0 | 0 |
| `scripts/` Python | 15 | 12 | 2 | 0 | 0 |
| `src/asu_june_bot/` | 16 | 8 | 4 | 0 | 0 |
| `src/meeting_agent/` | 15 | 0 | 0 | 14 | 0 |
| `configs/asu_june_bot/` | 5 | 3 | 2 | 0 | 0 |
| `configs/prompts/` | 8 | 7 | 0 | 1 | 0 |
| `configs/schemas/` | 6 | 5 | 0 | 1 | 0 |
| `docs/` | 41 | n/a | n/a | 0 | 41 |
| `apps/` | 4 | 0 | 0 | 4 | 0 |
| `tests/` | 3 | 0 | 0 | 3 | 0 |
| `templates/` | 3 | 0 | 0 | 3 | 0 |
| `meetings/` (sample) | 4 | 0 | 0 | 4 | 0 |
| `data/` `logs/` `watched_folder/` | 6 | 0 | 0 | 0 | 2+4 stub |
| `.github/workflows/` | 1 | 0 | 0 | 1 | 0 |

Итого:

- ~28-30 реально работающих Python/PS1 файлов в актуальном потоке.
- ~6 файлов кода в состоянии `dormant` или `legacy`.
- ~35 stub-точек (только `.gitkeep` или пустая папка с README-заглушкой).
- 41 markdown-документ.

## 1. Корень Репозитория

| Файл | Назначение | Кто вызывает / читает | Статус |
| --- | --- | --- | --- |
| `README.md` | Обзор продукта, точки входа, ссылки на доки. | manual | `doc` |
| `AGENTS.md` | Инструкции для AI-ассистентов: что трогать, что нет. | manual | `doc` |
| `RAG_AUTOMATION_INSTRUCTION.md` | Актуальный поток локальной RAG-сборки. | `docs/context.md` | `doc` |
| `.gitignore` | Правила исключения. **Содержит `*.jsonl` глобально** — потенциальная ловушка для образцовых данных. | git | `config` |
| `.env.example` | Шаблон переменных окружения. **Использует `%USERPROFILE%`, Windows-only.** | manual | `config` |
| `config.example.yaml` | Шаблон `config.yaml`. Реальный `config.yaml` в Git исключён. | `scripts/rag_common.py:load_config` (при копировании в `config.yaml`) | `config` |
| `.github/workflows/.gitkeep` | Зарезервировано под GitHub Actions. CI отсутствует. | — | `stub` |

**Проблема, фиксируемая в этом артефакте:** ни один файл в корне не описывает, как запускать `09_chat.py`, `06_transcribe_meeting.py`, `07_generate_meeting_artifacts.py`, `08_process_meeting_pipeline.py`. Команды есть в `README.md`, но без отдельной runbook-таблицы для каждой точки входа.

## 2. PowerShell Entrypoints (Корень)

| Файл | Что запускает | Кто вызывает | Статус |
| --- | --- | --- | --- |
| `run_full_rag.ps1` | Полная сборка RAG: `01_inventory → 02_extract_text → 03_build_index → 05_build_numpy_index`. | manual (главный entrypoint) | `entrypoint active` |
| `monitor_rag.ps1` | Один «тик» мониторинга долгой RAG-сборки: lock-файлы, статус Ollama, восстановление. | manual / Task Scheduler | `entrypoint active` |
| `check_rag_status.ps1` | Чтение последнего `full_rag_*.log/done.txt/failed.txt` в `logs/`. | manual | `entrypoint active` |
| `run_asu_june_bot_rebuild_v2.ps1` | Полная пересборка подпроекта: `asu_june_bot_extract_text_v2 → asu_june_bot_build_chunks_v2`. | manual / `monitor_asu_june_bot_v2.ps1:155` | `entrypoint active` |
| `run_asu_june_bot_chunks_v2.ps1` | Перепрогон только chunking-этапа подпроекта (требует существующий `blocks.jsonl`). | manual | `entrypoint active` |
| `monitor_asu_june_bot_v2.ps1` | Watchdog подпроекта (запускает `run_asu_june_bot_rebuild_v2.ps1` при необходимости). | `register_asu_june_bot_v2_watchdog.ps1` (через Task Scheduler) | `entrypoint active` |
| `register_asu_june_bot_v2_watchdog.ps1` | Регистрация Windows Task Scheduler для `monitor_asu_june_bot_v2.ps1`. | manual | `entrypoint active` |

**Что НЕ покрыто PowerShell-обвязкой:**

- `scripts/04_query.py` — нет .ps1 wrapper, только manual.
- `scripts/09_chat.py` — нет .ps1 wrapper, только manual из README.
- `scripts/06_transcribe_meeting.py`, `07_generate_meeting_artifacts.py`, `08_process_meeting_pipeline.py` — нет .ps1 wrapper.
- `scripts/asu_june_bot_search.py`, `asu_june_bot_audit_sources_v2.py` — нет .ps1 wrapper.

Все три entrypoint-скрипта подпроекта запускают Python в `data\asu_june_bot\…` — то есть подпроект использует **собственное** runtime-расположение, отдельное от основного `data/chunks.jsonl`, `data/embeddings_cache.jsonl`, `data/numpy_index`.

## 3. `scripts/` — RAG Пайплайн (01..05 + Общая Инфраструктура)

| Файл | Назначение | Кто вызывает | Импортирует из репо | Статус |
| --- | --- | --- | --- | --- |
| `scripts/01_inventory.py` | Инвентаризация `project_root` в `data/manifest.jsonl`: путь, размер, sha256, mtime, расширение, exclude-правила. | `run_full_rag.ps1:50` | `rag_common` | `active` |
| `scripts/02_extract_text.py` | Извлечение нормализованного текста из всех собранных файлов в `data/extracted_text/`. Поддерживаемые форматы: docx, pdf (через `fitz`), pptx, xlsx/xlsb, md/txt/html/json/yaml/srt/py/js/ts/css. | `run_full_rag.ps1:51` | `rag_common` | `active` |
| `scripts/03_build_index.py` | Нарезка текста на chunks, вызов Ollama `bge-m3` с `num_ctx=8192`, пополнение `data/embeddings_cache.jsonl`. Использует FileLock. | `run_full_rag.ps1:52` | `rag_common` (`FileLock`, `chunk_text`, `ensure_runtime_dirs`, `jsonl_read`, `jsonl_write`, `load_config`, `resolve_work_path`, `stable_id`) | `active` |
| `scripts/05_build_numpy_index.py` | Сборка `data/numpy_index/` (embeddings.npy + metadata.jsonl + manifest.json) из `chunks.jsonl` и `embeddings_cache.jsonl`. | `run_full_rag.ps1:53` | `rag_common`, `rag_numpy_backend.build_index` | `active` |
| `scripts/04_query.py` | CLI-запрос к RAG-индексу. Три режима: LLM (`/api/generate`), `--compact`, `--raw`. Логирует через `append_query_log`. | manual (eval, baseline-отчёты) | `rag_common`, `rag_numpy_backend` (`index_exists`, `load_index`) | `active` |
| `scripts/rag_common.py` | Общая инфраструктура: `load_config`, `resolve_work_path`, `ensure_runtime_dirs`, `jsonl_read/write`, `sha256_file`, `stable_id`, `normalize_text`, `chunk_text`, `FileLock`, `is_sensitive_query`, `append_query_log`. | `01..05`, `07`, `09`, `rag_numpy_backend` | (только `pyyaml`) | `active` (узел всего основного пайплайна) |
| `scripts/rag_numpy_backend.py` | Сборка и загрузка локального numpy-индекса: `build_index`, `NumpyRagIndex.query`, `index_exists`, `load_index`. | `04`, `05`, `09`, `src/asu_june_bot/retrieval/vector.py:20` | `rag_common` | `active` |

**Заметные факты:**

- `04_query.py` **не входит в `run_full_rag.ps1`** — это диагностический и evaluation-инструмент, не часть продуктового пути.
- `04_query.py` и `09_chat.py` используют **разные эндпоинты Ollama** (`/api/generate` без system-сообщения vs `/api/chat` с system-сообщением). Baseline-отчёты в `docs/quality/rag_eval_baseline_*.md` сняты на `04_query.py` — то есть не на той модели обращения, которую видит конечный пользователь чата.
- `src/asu_june_bot/retrieval/vector.py` импортирует `rag_numpy_backend` через `sys.path`-хак (см. артефакт №5 ревью).

## 4. `scripts/` — Meeting Пайплайн (06..08)

| Файл | Назначение | Кто вызывает | Импортирует из репо | Статус |
| --- | --- | --- | --- | --- |
| `scripts/06_transcribe_meeting.py` | Offline-транскрибация одной встречи через `faster-whisper`. Читает `meeting.json`, валидирует по `configs/schemas/meeting.schema.json`, пишет `transcript/transcript.md` и `transcript/segments.jsonl`. | manual | — (только stdlib + faster-whisper + pyyaml внешний) | `active` |
| `scripts/07_generate_meeting_artifacts.py` | Генерация memo / protocol / decisions/tasks/risks/open_questions JSON по transcript. Содержит два режима: `extractive` (offline скаффолд) и LLM (`--mode ollama` или `--mode ollama-map-reduce`). | `scripts/08_process_meeting_pipeline.py` (импортирует как модуль `artifacts07`) | `rag_common.load_config` | `active` (map-reduce путь) + `legacy` (три-вызовный путь) |
| `scripts/08_process_meeting_pipeline.py` | Оконный pipeline `ASR → MAP → REDUCE → RENDER` для готовой записи. Использует helper-функции из `07_*` через `importlib.util.spec_from_file_location` (динамический импорт по пути). | manual | `scripts/07_generate_meeting_artifacts.py` (динамически) | `active` |

**Заметные факты:**

- `07` и `08` — **god-файлы** (1072 и 1038 LOC соответственно). Это место, под которое в `src/meeting_agent/` зарезервированы пустые stub-папки `meetings/`, `transcription/`, `document_generation/` — то есть архитектурный задел существует, но декомпозиция не выполнена.
- `08` импортирует `07` **динамически** (`spec_from_file_location` по `Path`) — не через стандартный `import`. Это разрывает статический анализ зависимостей: переименование `07_generate_meeting_artifacts.py` молча ломает `08`.
- Эти три скрипта **не вызываются ни одним `.ps1`**. Все запуски — только вручную из README.
- В `07_generate_meeting_artifacts.py` есть две прод-ветки: **map-reduce-render** (актуальный путь по `docs/decisions.md` 2026-05-08) и **три-вызовный** (legacy, `meeting_memo.md` + `meeting_protocol.md` + `meeting_artifacts_json.md`). Обе ветки выбираются флагом `--mode`. См. таблицу промптов ниже.

## 5. `scripts/` — Project-Only Chat (09)

| Файл | Назначение | Кто вызывает | Импортирует из репо | Статус |
| --- | --- | --- | --- | --- |
| `scripts/09_chat.py` | Project-only чат-бот поверх numpy-RAG. Embedding запроса → retrieval с фильтрацией по score → LLM-ответ через `/api/chat` или extractive fallback. Логирует через `append_query_log`. | manual | `rag_common`, `rag_numpy_backend` | `active` |

**Заметные факты:**

- **Не вызывается ни одним `.ps1` wrapper.** Все вызовы только из README.
- Использует `configs/prompts/project_only_chat.md` как prompt template (без него падает с `FileNotFoundError`).
- **Не использует hybrid retrieval** из `src/asu_june_bot/retrieval/hybrid.py`. Все hybrid-возможности доступны только через `scripts/asu_june_bot_search.py`.
- Дефолты `DEFAULT_TOP_K=4`, `DEFAULT_SCORE_THRESHOLD=0.35`, `DEFAULT_MAX_CONTEXT_CHARS=6000` зашиты в код и **не считываются из `cfg["rag"]`**. См. артефакт №5 ревью.

## 6. `scripts/` — Asu June Bot CLI (`asu_june_bot_*`)

| Файл | Назначение | Кто вызывает | Импортирует из репо | Статус |
| --- | --- | --- | --- | --- |
| `scripts/asu_june_bot_extract_text_v2.py` | Извлечение текста подпроекта: docx, pdf, pptx, xlsx, html, md. Пишет `data/asu_june_bot/extracted_v2/blocks.jsonl` и отчёт. | `run_asu_june_bot_rebuild_v2.ps1:50` | `asu_june_bot.core.config`, `asu_june_bot.ingestion.models`, `asu_june_bot.ingestion.utils` | `active` |
| `scripts/asu_june_bot_build_chunks_v2.py` | Сборка `data/asu_june_bot/chunks_v2.jsonl` из blocks.jsonl с обогащением метаданными (через `enrich_metadata`). | `run_asu_june_bot_chunks_v2.ps1:54`, `run_asu_june_bot_rebuild_v2.ps1:51` | `asu_june_bot.core.config`, `asu_june_bot.ingestion.utils`, `asu_june_bot.retrieval.metadata.enrich_metadata` | `active` |
| `scripts/asu_june_bot_audit_sources_v2.py` | Аудит покрытия источников: что попало в индекс, что отфильтровано, сводка по типам. | manual (из runbook подпроекта) | `asu_june_bot.core.config`, `asu_june_bot.ingestion.utils` | `dormant` (не в pipeline, но используется аналитиком вручную) |
| `scripts/asu_june_bot_search.py` | CLI hybrid-поиск: `--mode hybrid|vector|bm25`, через `build_hybrid_retriever`. | manual | `asu_june_bot.core.config`, `asu_june_bot.retrieval.chunks.load_chunks`, `asu_june_bot.retrieval.hybrid.build_hybrid_retriever` | `dormant` (единственная точка использования hybrid retrieval, не интегрирована в чат) |

**Заметные факты:**

- **Все четыре файла — CLI-обёртки над пакетом `src/asu_june_bot/`.** Реальная логика живёт в пакете, скрипты только парсят argparse и зовут функции.
- Подпроект имеет **собственный config-loader** (`asu_june_bot.core.config.load_config`), который читает и `config.yaml` основного проекта, и `configs/asu_june_bot/*.yaml`, и сливает их через deep-merge. Основной `rag_common.load_config` про это ничего не знает.
- Подпроект пишет в **отдельную ветку runtime-данных**: `data/asu_june_bot/extracted_v2/`, `data/asu_june_bot/chunks_v2.jsonl`. Numpy-индекс подпроект **не строит свой**, а использует основной `data/numpy_index` (через `src/asu_june_bot/retrieval/vector.py:20`).

## 7. `src/asu_june_bot/` — Пакет Подпроекта

| Файл | Назначение | Кто импортирует | Статус |
| --- | --- | --- | --- |
| `src/asu_june_bot/__init__.py` | Маркер пакета. | implicit | `active` |
| `src/asu_june_bot/core/__init__.py` | Маркер подпакета. | implicit | `active` |
| `src/asu_june_bot/core/config.py` | Подпроектный config-loader: `load_main_config`, `load_asu_config`, `load_config`, `resolve_work_path`. Читает `config.yaml` + 5 YAML из `configs/asu_june_bot/`. | `scripts/asu_june_bot_*.py`, `src/asu_june_bot/ingestion/utils.py`, `src/asu_june_bot/retrieval/{vector,chunks}.py` | `active` |
| `src/asu_june_bot/ingestion/__init__.py` | Маркер. | implicit | `active` |
| `src/asu_june_bot/ingestion/models.py` | Dataclasses `ExtractedBlock`, `SourceDocument`. | `scripts/asu_june_bot_extract_text_v2.py` | `active` |
| `src/asu_june_bot/ingestion/utils.py` | Утилиты ингести: `normalize_text`, `stable_id(length=32)`, `text_hash`, `jsonl_write`, `…`. **Дублирует** часть `scripts/rag_common.py` с разной сигнатурой `stable_id` (24 vs 32). | `scripts/asu_june_bot_{build_chunks_v2, extract_text_v2, audit_sources_v2}.py` | `active` (с дублированием) |
| `src/asu_june_bot/retrieval/__init__.py` | Маркер. | implicit | `active` |
| `src/asu_june_bot/retrieval/metadata.py` | `enrich_metadata`, `infer_sections`: классификация чанка по `relative_path` + контенту. | `src/asu_june_bot/ingestion/utils.py`, `src/asu_june_bot/retrieval/{bm25, vector}.py`, `scripts/asu_june_bot_build_chunks_v2.py` | `active` |
| `src/asu_june_bot/retrieval/models.py` | `SearchResult` dataclass. | `bm25.py`, `vector.py`, `hybrid.py` | `active` |
| `src/asu_june_bot/retrieval/source_policy.py` | `SourcePolicy`: boost/penalty по `source_type` и пути. | `bm25.py`, `vector.py`, `hybrid.py` | `active` |
| `src/asu_june_bot/retrieval/query_expansion.py` | `QueryExpander`: словарные синонимы и аббревиатуры. | `hybrid.py` | `active` |
| `src/asu_june_bot/retrieval/chunks.py` | `load_chunks`: чтение `data/asu_june_bot/chunks_v2.jsonl`. | `scripts/asu_june_bot_search.py` | `active` |
| `src/asu_june_bot/retrieval/vector.py` | `VectorSearchAdapter`: поверх `rag_numpy_backend`. **Импортирует через sys.path-хак.** | `hybrid.py` | `dormant` (нет потребителя кроме hybrid) |
| `src/asu_june_bot/retrieval/bm25.py` | `BM25SearchAdapter`: in-memory BM25 поверх `chunks_v2.jsonl`. | `hybrid.py` | `dormant` |
| `src/asu_june_bot/retrieval/hybrid.py` | `HybridRetriever`, `build_hybrid_retriever`: композиция vector + bm25 + source_policy + query_expansion. | `scripts/asu_june_bot_search.py` | `dormant` (единственный потребитель — CLI поиска, не основной чат) |

**Заметные факты:**

- **`src/asu_june_bot/retrieval/{vector,bm25,hybrid}.py` достижимы только через `scripts/asu_june_bot_search.py`**. Они НЕ используются ни в `09_chat.py`, ни в каком-либо другом продуктовом потоке. Это работающий, но изолированный механизм.
- **Дублирование с `scripts/rag_common.py`** в `ingestion/utils.py`: `stable_id`, `normalize_text`, `jsonl_write`. Разные сигнатуры. Подробнее см. артефакт №5 ревью.

## 8. `src/meeting_agent/` — Заглушка Пакета

| Путь | Содержимое | Статус |
| --- | --- | --- |
| `src/meeting_agent/__init__.py` | пустой маркер | `stub` |
| `src/meeting_agent/api/.gitkeep` | пусто | `stub` |
| `src/meeting_agent/classification/.gitkeep` | пусто | `stub` |
| `src/meeting_agent/config/.gitkeep` | пусто | `stub` |
| `src/meeting_agent/core/.gitkeep` | пусто | `stub` |
| `src/meeting_agent/document_generation/.gitkeep` | пусто | `stub` |
| `src/meeting_agent/extraction/.gitkeep` | пусто | `stub` |
| `src/meeting_agent/ingest/.gitkeep` | пусто | `stub` |
| `src/meeting_agent/integrations/.gitkeep` | пусто | `stub` |
| `src/meeting_agent/meetings/.gitkeep` | пусто | `stub` |
| `src/meeting_agent/observability/.gitkeep` | пусто | `stub` |
| `src/meeting_agent/rag/.gitkeep` | пусто | `stub` |
| `src/meeting_agent/storage/.gitkeep` | пусто | `stub` |
| `src/meeting_agent/transcription/.gitkeep` | пусто | `stub` |

**Заметные факты:**

- **Никто из 14 stub-папок не имеет файлов кроме `.gitkeep` и `__init__.py`.** Весь продуктовый код живёт в `scripts/`, а не в этом пакете.
- README.md описывает `src/meeting_agent/` как «Будущий Python-пакет». Это **архитектурный задел без реализации**, существующий ~1 год по `git log`.
- Под `meetings/`, `transcription/`, `document_generation/`, `extraction/`, `ingest/` логически ложились бы `scripts/06..08_*.py`. Декомпозиция не сделана.

## 9. `configs/asu_june_bot/` — YAML-Конфиг Подпроекта

| Файл | Назначение | Кто читает (код, не доки) | Статус |
| --- | --- | --- | --- |
| `configs/asu_june_bot/retrieval.yaml` | Веса hybrid retrieval (`vector_weight`, `bm25_weight`), top_k для подпроекта. | `src/asu_june_bot/retrieval/hybrid.py:137-141` через `cfg["asu_june_bot"]["retrieval"]` | `active` |
| `configs/asu_june_bot/source_policy.yaml` | Boost/penalty по `source_type`. | `src/asu_june_bot/retrieval/hybrid.py:139` через `cfg["asu_june_bot"]["source_policy"]` | `active` |
| `configs/asu_june_bot/query_expansion.yaml` | Синонимы для query expansion. | `src/asu_june_bot/retrieval/hybrid.py:140` через `cfg["asu_june_bot"]["query_expansion"]` | `active` |
| `configs/asu_june_bot/llm.yaml` | Параметры LLM подпроекта (`model`, `temperature`, `top_p`, `max_tokens`). | **Загружается** в `cfg["asu_june_bot"]["llm"]` (`core/config.py:46`), но **ни один файл кода это значение не читает**. | `dormant` |
| `configs/asu_june_bot/guardrails.yaml` | Правила refusal/sensitive подпроекта. | **Загружается** в `cfg["asu_june_bot"]["guardrails"]`, но **ни один файл кода не читает**. | `dormant` |

**Заметный факт:** `llm.yaml` зашит в `load_asu_config` (жёсткий список `("retrieval", "source_policy", "query_expansion", "llm", "guardrails")`), но потребителя для двух из пяти ключей в коде нет. Это означает один из двух сценариев: либо чтение запланировано в будущем коде чата подпроекта (которого пока нет), либо YAML — рудимент. По текущему репозиторию однозначно — рудимент.

## 10. `configs/prompts/` — Prompt-Шаблоны

| Файл | Кто читает | Статус |
| --- | --- | --- |
| `configs/prompts/project_only_chat.md` | `scripts/09_chat.py` через `--prompt` (дефолт). | `active` |
| `configs/prompts/meeting_map_extract.md` | `scripts/07_generate_meeting_artifacts.py:827`, `scripts/08_process_meeting_pipeline.py:845`. | `active` |
| `configs/prompts/meeting_reduce_artifacts.md` | `07:828`, `08:846`. | `active` |
| `configs/prompts/meeting_render_documents.md` | `07` (map-reduce ветка), `08:847`. | `active` |
| `configs/prompts/meeting_memo.md` | `07:957` (legacy три-вызовная ветка). | `legacy` |
| `configs/prompts/meeting_protocol.md` | `07:963` (legacy три-вызовная ветка). | `legacy` |
| `configs/prompts/meeting_artifacts_json.md` | `07:969` (legacy три-вызовная ветка). | `legacy` |
| `configs/prompts/.gitkeep` | — | `stub` (но папка уже непустая) |

**Заметный факт:** три legacy-промпта (`meeting_memo`, `meeting_protocol`, `meeting_artifacts_json`) фактически избыточны, потому что `docs/decisions.md` 2026-05-08 зафиксировала map-reduce-render как production-путь. Они остаются в коде только потому, что `--mode ollama` (три-вызовный) технически работает.

## 11. `configs/schemas/` — JSON-Схемы

| Файл | Кто читает | Статус |
| --- | --- | --- |
| `configs/schemas/meeting.schema.json` | `scripts/06_transcribe_meeting.py`, `07_generate_meeting_artifacts.py`, `08_process_meeting_pipeline.py` (загружают и валидируют). | `active schema` |
| `configs/schemas/meeting.decisions.schema.json` | `07_generate_meeting_artifacts.py`. | `active schema` |
| `configs/schemas/meeting.tasks.schema.json` | `07`. | `active schema` |
| `configs/schemas/meeting.risks.schema.json` | `07`. | `active schema` |
| `configs/schemas/meeting.open_questions.schema.json` | `07`. | `active schema` |
| `configs/schemas/.gitkeep` | — | `stub` (папка непустая) |

## 12. `docs/` — Документация

Перечислено только верхнеуровневое назначение и ключевые потребители. Для каждой подпапки указано, насколько её содержимое синхронно с кодом (на основании выявленных расхождений в предыдущем аудите).

### 12.1 `docs/` корневые

| Файл | Назначение | Состояние |
| --- | --- | --- |
| `docs/context.md` | Сводка состояния, что сделано / что осталось. | **Дрейфует**: «что осталось» содержит частично выполненные пункты. |
| `docs/decisions.md` | Архитектурные решения с датами и обоснованием. | В целом синхронен, но не содержит решения о реализации логирования запросов (внесено сегодня). |
| `docs/todo.md` | Ближайшие задачи. | Только что обновлён. |
| `docs/glossary.md` | Словарь терминов и заготовка `initial_prompt`. | `doc-only` |

### 12.2 `docs/architecture/`

| Файл | Описывает | Состояние |
| --- | --- | --- |
| `docs/architecture/ARCHITECTURE.md` | Общий поток + слои хранения. | Описывает «классификатор», «watchdog», «генератор» как компоненты — фактически они существуют только как скрипты, не как компоненты пакета. |
| `docs/architecture/FOLDER_STRUCTURE.md` | Описание структуры папок. | Местами рассинхронен с реальностью (см. артефакт №6 ревью). |
| `docs/architecture/MEETING_ARTIFACTS_PIPELINE.md` | Контракт map-reduce-render. | Синхронно с `scripts/07_*` map-reduce веткой. |

### 12.3 `docs/operations/`

| Файл | Описывает | Состояние |
| --- | --- | --- |
| `docs/operations/RAG_PIPELINE.md` | Команды локальной RAG-сборки. | Синхронно с `run_full_rag.ps1`. |
| `docs/operations/MEETING_PIPELINE.md` | Очерёдность для встречи. | Синхронно. |
| `docs/operations/WATCHDOG.md` | Логика `monitor_rag.ps1`. | Не проверял в этом артефакте, оставлю на №2 (data flow). |
| `docs/operations/BACKUP_AND_RETENTION.md` | Политика хранения. | `doc-only`, не имеет кода. |

### 12.4 `docs/product/`

| Файл | Назначение |
| --- | --- |
| `docs/product/PRODUCT_VISION_AND_PLAN.md` | Видение продукта. |
| `docs/product/PROJECT_STAGES_AND_FTT.md` | Execution checklist по ФТТ продукта. |
| `docs/product/PROJECT_TAXONOMY.md` | Таксономия этапов и документов. |
| `docs/product/PROJECT_ONLY_CHATBOT_MVP.md` | Roadmap чата. |
| `docs/product/ROADMAP.md` | Общий roadmap. |
| `docs/product/BACKLOG.md` | Бэклог. |
| `docs/product/PRODUCT_APPROACH.md` | Подход к продукту. |
| `docs/product/PARALLEL_WORK_WHILE_RAG_BUILDS.md` | Исторический план параллельных работ. |

Все 8 — `doc-only`, не порождают код напрямую, но многократно ссылаются друг на друга.

### 12.5 `docs/quality/`

| Файл | Назначение | Состояние |
| --- | --- | --- |
| `docs/quality/EVALUATION_PLAN.md` | План оценки RAG. | **Без раннера**: процесс описан, но скрипт прогона отсутствует. |
| `docs/quality/QUERY_FEEDBACK_LOOP.md` | Процесс логирования и разметки запросов. | Синхронно: реализовано `rag_common.append_query_log`. |
| `docs/quality/rag_eval_questions.md` | Контрольный набор вопросов. | Только текст. |
| `docs/quality/rag_eval_baseline_2026-05-07.md` | Первый baseline. | Снимок, не предполагается обновление. |
| `docs/quality/rag_eval_baseline_clean_2026-05-07.md` | Baseline после чистки корпуса. | Снимок. |
| `docs/quality/rag_eval_report_template.md` | Шаблон отчёта. | Используется вручную при новых прогонах. |
| `docs/quality/project_only_chatbot_smoke_questions.md` | Smoke-вопросы чата. | Только текст, нет авто-прогона. |

### 12.6 `docs/references/`

| Файл | Назначение |
| --- | --- |
| `docs/references/SPEAKR_REFERENCE.md` | Паттерны из Speakr. |
| `docs/references/WHISPERDESK_EXPERIMENT.md` | Эксперимент с WhisperDesk. |
| `docs/references/WHISPERX_EXPERIMENT.md` | Эксперимент с WhisperX. |

Все три — `doc-only`, исторические референсы.

### 12.7 `docs/security/`

| Файл | Назначение | Состояние |
| --- | --- | --- |
| `docs/security/PRIVACY_AND_DATA.md` | Локальная политика данных. | `doc-only` |

### 12.8 `docs/subprojects/asu-june-bot/`

| Файл | Назначение |
| --- | --- |
| `docs/subprojects/asu-june-bot/README.md` | Обзор подпроекта. |
| `docs/subprojects/asu-june-bot/context.md` | Контекст. |
| `docs/subprojects/asu-june-bot/decisions.md` | Решения. |
| `docs/subprojects/asu-june-bot/architecture.md` | Архитектура. |
| `docs/subprojects/asu-june-bot/mvp.md` | MVP. |
| `docs/subprojects/asu-june-bot/roadmap.md` | Roadmap. |
| `docs/subprojects/asu-june-bot/todo.md` | TODO. |
| `docs/subprojects/asu-june-bot/eval_questions.md` | Eval-вопросы. |
| `docs/subprojects/asu-june-bot/chunking_strategy.md` | Стратегия chunking. |
| `docs/subprojects/asu-june-bot/runbook_v2.md` | Runbook v2 (lowercase). |
| `docs/subprojects/asu-june-bot/RUNBOOK_V2.md` | Runbook v2 (uppercase). |

**Заметный факт:** `runbook_v2.md` и `RUNBOOK_V2.md` — два файла с разным регистром. На case-insensitive файловых системах (Windows, macOS APFS дефолт) — это **один и тот же файл**, на Linux (CI/контейнеры) — два разных. Потенциальный источник путаницы. Подробнее см. артефакт №5 ревью.

### 12.9 `docs/templates/`

| Файл | Назначение |
| --- | --- |
| `docs/templates/MEETING_CARD.md` | Шаблон карточки встречи (Markdown). |
| `docs/templates/DOCUMENT_GENERATION_BRIEF.md` | Бриф под будущую генерацию документов. |

### 12.10 `docs/examples/`

| Файл | Назначение |
| --- | --- |
| `docs/examples/meeting.new.example.json` | Пример `meeting.json` со статусом `new`. Используется как образец для создания папки встречи. |

## 13. Runtime-Папки И Stubs

| Путь | Назначение | В Git | Статус |
| --- | --- | --- | --- |
| `data/.gitkeep`, `data/README.md` | Runtime для chunks/embeddings/numpy_index/query_log. Содержимое не коммитится. | оба файла | `runtime` |
| `logs/.gitkeep`, `logs/README.md` | Runtime для логов RAG-сборки. | оба файла | `runtime` |
| `watched_folder/.gitkeep`, `watched_folder/README.md` | Inbox для новых записей встреч. Watcher пока не реализован. | оба файла | `runtime stub` (Watcher для FTT-MA-08 в TODO) |
| `templates/documents/.gitkeep` | Зарезервировано под шаблоны генерируемых документов. | только .gitkeep | `stub` |
| `templates/meetings/.gitkeep` | Зарезервировано под шаблоны встреч. | только .gitkeep | `stub` |
| `templates/prompts/.gitkeep` | Зарезервировано под пользовательские prompt-шаблоны. **Дублирует роль `configs/prompts/`.** | только .gitkeep | `stub` |
| `apps/api/.gitkeep` | Зарезервировано под local API. | только .gitkeep | `stub` |
| `apps/cli/.gitkeep` | Зарезервировано под CLI-обёртку. | только .gitkeep | `stub` |
| `apps/desktop/.gitkeep` | Зарезервировано под desktop UI. | только .gitkeep | `stub` |
| `apps/web/.gitkeep` | Зарезервировано под web UI. | только .gitkeep | `stub` |
| `tests/unit/.gitkeep` | Зарезервировано под unit-тесты. | только .gitkeep | `stub` |
| `tests/integration/.gitkeep` | Зарезервировано. | только .gitkeep | `stub` |
| `tests/evaluation/.gitkeep` | Зарезервировано. | только .gitkeep | `stub` |
| `meetings/2026-05-08__test-meeting/{artifacts,exports,source,transcript}/.gitkeep` | Каркас тестовой встречи. Реальные данные локальные, не в Git. | 4 × .gitkeep | `runtime stub` |

## 14. Сводка Dead / Dormant / Orphan

Список того, что **физически не нужно** для актуального рабочего потока или что объявлено deprecated.

### 14.1 Полностью dormant конфигурация

- `configs/asu_june_bot/llm.yaml` — загружается, но не читается.
- `configs/asu_june_bot/guardrails.yaml` — загружается, но не читается.

### 14.2 Dormant код (работает, но не подключён к продукту)

- `src/asu_june_bot/retrieval/vector.py`
- `src/asu_june_bot/retrieval/bm25.py`
- `src/asu_june_bot/retrieval/hybrid.py`
- `src/asu_june_bot/retrieval/query_expansion.py` (используется только через hybrid)
- `scripts/asu_june_bot_search.py` — единственный CLI к этой ветке.

Все они образуют **изолированный hybrid-retrieval контур**, доступный только через свой CLI и не вызываемый из основного `09_chat.py`.

### 14.3 Legacy ветки

- `scripts/07_generate_meeting_artifacts.py` — три-вызовная ветка (`--mode ollama`, без map-reduce).
- `configs/prompts/meeting_memo.md`, `meeting_protocol.md`, `meeting_artifacts_json.md` — питают только три-вызовную ветку.

### 14.4 Deprecated по решениям

- `vector_db/` — упомянут в `config.example.yaml:49`, в `.gitignore:27`, в `docs/architecture/ARCHITECTURE.md:47`. Физически нет ни одного файла в git. Сам ключ `paths.vector_db` в `config.example.yaml` можно удалить.

### 14.5 Архитектурные stubs

- `src/meeting_agent/` — 14 stub-папок.
- `apps/` — 4 stub-папки.
- `tests/` — 3 stub-папки.
- `templates/` — 3 stub-папки (роль частично пересекается с `configs/prompts/`).
- `.github/workflows/.gitkeep` — нет CI.

### 14.6 Orphan-файлы документации

- `docs/subprojects/asu-june-bot/runbook_v2.md` и `RUNBOOK_V2.md` — два файла с разным регистром, неоднозначно.

### 14.7 Файлы без entrypoint-обёртки

PowerShell-обёрток нет для:

- `scripts/04_query.py`
- `scripts/06_transcribe_meeting.py`
- `scripts/07_generate_meeting_artifacts.py`
- `scripts/08_process_meeting_pipeline.py`
- `scripts/09_chat.py`
- `scripts/asu_june_bot_search.py`
- `scripts/asu_june_bot_audit_sources_v2.py`

Это значит: «кнопка» для пользователя есть только у RAG-сборки (`run_full_rag.ps1`), её мониторинга (`monitor_rag.ps1`, `check_rag_status.ps1`) и подпроектной пересборки (`run_asu_june_bot_*.ps1`). Всё остальное — ручной запуск из README.

## 15. Чего В Этом Артефакте Нет

- **Точная карта схемы JSON-полей** — будет в артефакте №3 (`03_data_schemas_catalog.md`).
- **Mermaid-диаграммы потоков данных** — будут в артефакте №2 (`02_data_flow_pipelines.md`).
- **ER-диаграммы сущностей** — будут в артефакте №4 (`04_entity_relationships.md`).
- **Полный список того, что предлагается удалить** — будет в артефакте №5 (`05_dead_and_unused.md`) с конкретными командами `git rm`.
- **Все расхождения между документацией и кодом** — будут в артефакте №6 (`06_docs_vs_code_drift.md`).
- **Целевая структура каталогов после консолидации** — будет в артефакте №7 (`07_consolidation_plan.md`).

## 16. Неуверенные Пункты

- `08_process_meeting_pipeline.py` импортирует `07_*` через `importlib.util.spec_from_file_location` — не через стандартный `import`. Возможно, есть ещё подобные динамические импорты в других файлах, которые я не выловил статическим grep'ом.
- Не проверял содержимое всех `.gitkeep` (предположил, что они пустые или содержат один байт).
- В `configs/asu_june_bot/llm.yaml` и `guardrails.yaml` мог быть код-консумент в файле, который не покрылся моим `grep`-паттерном (`asu_june_bot[`, `cfg["asu_june_bot"]`). Если консумент использует `dict.get("asu_june_bot", {})` через промежуточную переменную, я мог пропустить.

Эти пункты помечу `[?]` при перепроверке в следующих артефактах.
