# Подпроекты И Эксперименты

Артефакт №7 серии полного ревью. Разбирает «второй контур» репозитория, который существует параллельно основному pipeline: подпроект `asu_june_bot/` и три отложенных эксперимента (WhisperDesk, WhisperX, Speakr).

## Содержание

1. [Ключевая находка: два слоя подпроекта](#1-ключевая-находка-два-слоя-подпроекта)
2. [Структура `src/asu_june_bot/`](#2-структура-srcasu_june_bot)
3. [`configs/asu_june_bot/`: YAML-контракты](#3-configsasu_june_bot-yaml-контракты)
4. [Скрипты подпроекта](#4-скрипты-подпроекта)
5. [Что подключено, что осиротело](#5-что-подключено-что-осиротело)
6. [Интеграция с основным `09_chat.py`](#6-интеграция-с-основным-09_chatpy)
7. [Эксперименты: WhisperDesk, WhisperX, Speakr](#7-эксперименты-whisperdesk-whisperx-speakr)
8. [Roadmap vs реальность](#8-roadmap-vs-реальность)
9. [Самокоррекции артефактов №3 и №4](#9-самокоррекции-артефактов-3-и-4)
10. [Что не было проверено](#10-что-не-было-проверено)

## 1. Ключевая Находка: Два Слоя Подпроекта

В подпроекте `asu_june_bot/` **сосуществуют две параллельные кодовые линии**, которые я в артефактах №3 и №4 ошибочно объединил в одну «v2-вселенную»:

| Слой | Что включает | Какой корпус читает | Статус |
|---|---|---|---|
| **Search MVP v1** | `src/asu_june_bot/{core, ingestion/utils, retrieval/*}` + `scripts/asu_june_bot_search.py` + 5 YAML в `configs/asu_june_bot/` | **Основной MeetingAgent corpus**: `data/chunks.jsonl` + `data/numpy_index` | Работает |
| **Extract / Chunk v2** | `src/asu_june_bot/ingestion/models` + `scripts/asu_june_bot_{extract_text_v2, build_chunks_v2, audit_sources_v2}.py` | Свой независимый pipeline: `data/asu_june_bot/extracted_v2/{documents,blocks}.jsonl` → `data/asu_june_bot/chunks_v2.jsonl` | Производит данные, **никто не читает** |

### 1.1 Почему это важно

Это **не просто академическое разделение** — два слоя описывают разные стратегии:

- **v1 (работает)** — переиспользовать индекс основного MeetingAgent, добавить сверху BM25 + query expansion + source policy. Можно прогнать запрос **прямо сейчас**: `python scripts/asu_june_bot_search.py "Что входит в Паспорт ИС?"`.
- **v2 (производит, но не подключён)** — отдельный, более богатый extraction (blocks + tables + sheets с метаданными), отдельный chunker с parent/block split. Конечный артефакт `chunks_v2.jsonl` имеет 30+ метаданных полей (`stage`, `module`, `requirement_id`, `scenario_id`, …), но никакой скрипт его сейчас не читает.

Между ними **отсутствует мост** — `scripts/asu_june_bot_build_index_v2.py` упоминается в `docs/subprojects/asu-june-bot/{context.md, chunking_strategy.md}` как «future:», но не реализован (см. артефакт №6).

### 1.2 Декларированный план миграции

Из `docs/subprojects/asu-june-bot/todo.md`:

```
Новый Asu June Bot v2 строить независимо:
extract_text_v2 -> chunks_v2 -> index_v2

Не опираться на старый scripts/02_extract_text.py для v2.
Не менять старый run_full_rag.ps1, data/chunks.jsonl,
data/embeddings_cache.jsonl и data/numpy_index при проверке v2.
```

Текущее состояние: первые два шага сделаны, третий (`index_v2`) — нет. Поэтому **`asu_june_bot_search.py` продолжает обращаться к старому индексу**, а новые данные накапливаются без потребителя.

## 2. Структура `src/asu_june_bot/`

Итого: **15 файлов, 983 LOC** (включая `__init__.py`).

```
src/asu_june_bot/
├── __init__.py
├── core/
│   ├── __init__.py
│   └── config.py                 # 64 LOC — слияние main config + asu config
├── ingestion/
│   ├── __init__.py
│   ├── models.py                 # 61 LOC — SourceDocument, ExtractedBlock
│   └── utils.py                  # 133 LOC — общие хелперы (sha, jsonl, normalize)
└── retrieval/
    ├── __init__.py
    ├── models.py                 # 50 LOC — SearchQuery, SearchResult
    ├── chunks.py                 # 27 LOC — load_chunks из main chunks.jsonl
    ├── metadata.py               # 172 LOC — enrich_metadata: source_type, document_type, module, stage, sections
    ├── source_policy.py          # 64 LOC — SourcePolicy: allow + weight по source_type/document_type
    ├── vector.py                 # 90 LOC — VectorSearchAdapter (поверх main numpy_index)
    ├── bm25.py                   # 133 LOC — BM25SearchAdapter с section-boost
    ├── query_expansion.py        # 25 LOC — QueryExpander по YAML-словарю
    └── hybrid.py                 # 158 LOC — HybridRetriever (merge vector+bm25)
```

### 2.1 `core/config.py`

| Функция | Назначение |
|---|---|
| `load_main_config(path)` | Читает корневой `config.yaml`. |
| `load_asu_config(config_dir)` | Читает все 5 YAML из `configs/asu_june_bot/`, объединяет в `{asu_june_bot: {...}}`. |
| `load_config()` | `deep_merge(main_cfg, asu_cfg)` — единая точка входа для подпроекта. |
| `resolve_work_path(cfg, raw)` | Аналог из `rag_common`, но в namespace подпроекта. |

**Дублирование с `rag_common`:** `load_config`, `resolve_work_path` — почти идентичные реализации, что и в `scripts/rag_common.py`. Это **намеренное** разделение namespace, чтобы подпроект мог развиваться независимо.

### 2.2 `ingestion/models.py`

Dataclass'ы `SourceDocument` и `ExtractedBlock` — уже разобраны в артефакте №3 (slot=true, метаданные source/block).

### 2.3 `ingestion/utils.py`

| Функция | Назначение |
|---|---|
| `normalize_text` | Идентична `rag_common.normalize_text` (дублирующая реализация). |
| `stable_id` | **Длина по умолчанию 32**, не 24 как в `rag_common.stable_id`. |
| `sha256_file` | Идентична rag_common. |
| `read_text_guess` | Идентична. |
| `jsonl_write` | Идентична. |
| `is_office_temp_file` | Только подпроект. |
| `should_skip_path` | Только подпроект, используется в `extract_text_v2`. |
| `text_hash` | Не показан, но используется в `build_chunks_v2` для дедупликации. |
| `SECTION_RE` | Regex для извлечения номеров разделов («1.2.3»). |

**Архитектурное расхождение:** утилиты дублируются в `scripts/rag_common.py` и `src/asu_june_bot/ingestion/utils.py`. Это даёт независимость, но возможны расхождения семантики (например, `stable_id` имеет разный default length).

### 2.4 `retrieval/models.py`

Dataclass'ы `SearchQuery` (query + filters) и `SearchResult` (id, text, score, vector_score, bm25_score, metadata, matched_by, diagnostics).

### 2.5 `retrieval/chunks.py`

Одна функция: `load_chunks(cfg)` → читает `cfg.paths.chunks` = по умолчанию **`data/chunks.jsonl`** (главный корпус MeetingAgent, **не** v2).

### 2.6 `retrieval/metadata.py` (172 LOC, самый большой)

Реализует **эвристический enrichment**: из `relative_path` + `text` извлекает:
- `source_type` — `project_doc` / `meeting_artifact` / `analytical_note` / `instruction` / `system_export` / `runtime_export` / `code`. Определение через подстроки в пути (`SYSTEM_EXPORT_HINTS`, `ANALYTICAL_NOTE_HINTS`, `MEETING_HINTS`).
- `document_type` — `ЦТА`, `ФТТ`, `ПР`, `Паспорт ИС`, `ПМИ`, `СоИ AD`, `Руководство`, `Wiki` и др. Распознаётся по подстрокам в filename.
- `module` — конкретный модуль ЦП УПКС.
- `stage` — этап проекта.
- `section`, `sections` — номера разделов из текста (по regex `(\d+(?:\.\d+){1,5})`).
- `title` — заглушка.

Используется и в v1 retrieval (на ходу), и в `asu_june_bot_build_chunks_v2.py` (на этапе чункинга).

### 2.7 `retrieval/source_policy.py`

`SourcePolicy.is_allowed(metadata, query)` + `SourcePolicy.weight(metadata)`:
- **Allow** по списку `allowed_by_default` (по умолчанию `project_doc`, `meeting_artifact`, `analytical_note`, `instruction`), плюс автоматическое расширение по `explicit_enable_markers` (например, упоминание «админ»/«экспорт» → разрешает `system_export`).
- **Weight** = `weights[source_type] × document_type_weights[document_type]`. Дефолтные веса в коде совпадают с `configs/asu_june_bot/source_policy.yaml`:

| source_type | weight |
|---|---|
| `project_doc` | 1.0 |
| `meeting_artifact` | 0.9 |
| `analytical_note` | 0.85 |
| `instruction` | 0.8 |
| `system_export` | 0.55 |
| `runtime_export` | 0.4 |
| `code` | 0.35 |

| document_type | multiplier |
|---|---|
| `ЦТА` | 1.18 |
| `СоИ AD`, `СоИ Справочники` | 1.16 |
| `ФТТ` | 1.12 |
| `ПР`, `Паспорт ИС` | 1.08 |
| `ПМИ` | 1.0 |
| `Руководство` | 0.96 |
| `Реестр НСИ` | 0.86 |
| `Wiki` | 0.74 |

Применяется **в vector adapter** (`weighted_score = vector_score × weight`).

### 2.8 `retrieval/vector.py`

`VectorSearchAdapter(cfg, source_policy)`:
- При инициализации читает `paths.numpy_index` = по умолчанию **`data/numpy_index`** (главный индекс) через `rag_numpy_backend.load_index` (импортируется через `sys.path` hack, добавляющий `scripts/` в path).
- `search(query, top_k, include_source_types)`:
  1. `ollama_embed(query)` — вызов `/api/embeddings` Ollama (model из `cfg.ollama.embedding_model`, по умолчанию `bge-m3`).
  2. `self.index.query(embedding, top_k×4, exclude_path_patterns, dedupe_by_chunk_id=True)`.
  3. Для каждого результата: `enrich_metadata`, проверка `source_policy.is_allowed`, перевзвешивание `vector_score × source_policy.weight`.
  4. Top-k.

### 2.9 `retrieval/bm25.py`

`BM25SearchAdapter(rows, source_policy)`:
- При инициализации индексирует переданные `rows` (это `data/chunks.jsonl`!) — токенизация, term_freq, doc_freq.
- BM25 параметры: `k1=1.5, b=0.75`.
- `_exact_section_boost(query_sections, doc)` — boost ×1.45, если в запросе явно указан номер раздела (например «2.3.4»), который есть в `metadata.sections`.

**Реализован вручную**, без `rank_bm25`. Загрузка корпуса в память: ~5000 chunks × токенизация.

### 2.10 `retrieval/query_expansion.py`

`QueryExpander(config)` — простейшее: на основе `configs/asu_june_bot/query_expansion.yaml` подставляет в запрос синонимы. Например:

```yaml
integrations:
  triggers: [интеграции, внешние системы, ...]
  expansions: [MDR, КШД, СОИ, AD, LDAPS, Blitz IDP, SMTP, ...]
```

Если в запросе есть «интеграции», к нему дописываются термины `MDR КШД СОИ AD LDAPS …`.

### 2.11 `retrieval/hybrid.py`

`HybridRetriever(vector_search, bm25_search, source_policy, query_expander, vector_weight=0.65, bm25_weight=0.35)`:
- `search(query, top_k, mode)` — три режима: `hybrid`, `vector`, `bm25`.
- Hybrid: query expansion → vector search + BM25 → нормализация score'ов отдельно по каждому источнику → merge `score = 0.65 × vector_norm + 0.35 × bm25_norm` → дедуп по `chunk_key` (по `relative_path + chunk_index`) → ranked top-k.
- На выходе результаты пере-нумеруются в `SRC-001`, `SRC-002`, …

`build_hybrid_retriever(cfg, rows, mode)` — фабрика, читает `cfg.asu_june_bot.retrieval/source_policy/query_expansion`.

## 3. `configs/asu_june_bot/`: YAML-Контракты

Пять файлов, все читаются `core/config.load_asu_config`:

| Файл | Назначение | Реально используется? |
|---|---|---|
| `retrieval.yaml` | `mode: hybrid`, `vector_weight: 0.65`, `bm25_weight: 0.35`, `default_top_k: 10`, `candidate_multiplier: 3` | **Да**, через `build_hybrid_retriever`. |
| `source_policy.yaml` | Списки `allowed_by_default`, `weights`, `document_type_weights`, `explicit_enable_markers` | **Да**, через `SourcePolicy(config)`. |
| `query_expansion.yaml` | Словарь триггеров/расширений по темам (integrations, passport_is, ...) | **Да**, через `QueryExpander(config)`. |
| `llm.yaml` | `provider: openai_compatible`, `base_url: http://localhost:11434/v1`, `model: qwen3:4b`, `temperature: 0.1`, `top_p: 0.8`, `max_tokens: 1200` | **Нет**, LLM-слой не реализован. Комментарий в файле: «Chat layer will use this after search MVP». |
| `guardrails.yaml` | `out_of_scope_examples`, `sensitive_patterns`, `refusal_message` | **Нет**, project-guard не реализован. Комментарий: «Реализация guard будет добавлена после search MVP». |

**Итого:** 3 из 5 конфигов работают, 2 — контракты под будущий код. Все они **загружаются** в `cfg.asu_june_bot.*` (через `deep_merge`), но обращения к `llm` и `guardrails` ключам нет.

## 4. Скрипты Подпроекта

Уже подробно описаны в артефакте №5 (раздел 6). Здесь — резюме по принадлежности к слоям:

| Скрипт | Слой | Что делает |
|---|---|---|
| `scripts/asu_june_bot_search.py` | **v1 (работает)** | CLI для hybrid retrieval над `data/chunks.jsonl` + `data/numpy_index`. |
| `scripts/asu_june_bot_extract_text_v2.py` | **v2 (производит)** | Извлекает blocks из source-файлов в `data/asu_june_bot/extracted_v2/blocks.jsonl`. |
| `scripts/asu_june_bot_build_chunks_v2.py` | **v2 (производит)** | Из `blocks.jsonl` собирает `chunks_v2.jsonl` с богатой metadata. |
| `scripts/asu_june_bot_audit_sources_v2.py` | **v2 (диагностика)** | Аудит того, какие source-файлы попадут в v2. |

И обёртки (PowerShell):

| Скрипт | Назначение |
|---|---|
| `run_asu_june_bot_rebuild_v2.ps1` | extract_v2 → chunks_v2. |
| `run_asu_june_bot_chunks_v2.ps1` | Только chunks_v2 (когда blocks.jsonl готовы). |
| `monitor_asu_june_bot_v2.ps1` | Watchdog для v2-сборки. |
| `register_asu_june_bot_v2_watchdog.ps1` | Регистрация Task Scheduler. |

## 5. Что Подключено, Что Осиротело

### 5.1 Работающая цепочка v1

```
configs/asu_june_bot/*.yaml
       ↓ load_asu_config
       ↓ deep_merge with main config
asu_june_bot.core.config.load_config
       ↓
asu_june_bot_search.py
       ↓
load_chunks(cfg) → data/chunks.jsonl          [ОСНОВНОЙ корпус MeetingAgent]
       ↓
build_hybrid_retriever(cfg, rows)
       ↓
       ├─ VectorSearchAdapter → data/numpy_index   [ОСНОВНОЙ индекс]
       │     ├─ Ollama /api/embeddings  (bge-m3)
       │     ├─ enrich_metadata (на лету)
       │     └─ source_policy filter + weight
       └─ BM25SearchAdapter → in-memory из rows
             ├─ enrich_metadata (на лету)
             ├─ section_boost ×1.45
             └─ source_policy filter
       ↓
HybridRetriever.search
       ├─ QueryExpander (по themes из YAML)
       ├─ vector + bm25 candidates (top_k × 3)
       ├─ score normalization
       ├─ weighted merge (0.65 vector + 0.35 bm25)
       └─ dedupe + rank
       ↓
stdout (human / json)
```

### 5.2 Производящая цепочка v2 (потребителя нет)

```
configs/asu_june_bot/source_policy.yaml? (нет, использует только enrich_metadata)
       ↓
asu_june_bot_extract_text_v2.py
       ↓
SourceDocument + ExtractedBlock (dataclass to_dict)
       ↓
data/asu_june_bot/extracted_v2/documents.jsonl  [append]
data/asu_june_bot/extracted_v2/blocks.jsonl     [append]
       ↓
asu_june_bot_build_chunks_v2.py
       ↓
make_chunk (enrich_metadata + extra fields)
       ↓
data/asu_june_bot/chunks_v2.jsonl  [rewrite]
       ↓
       ╳  НЕТ ПОТРЕБИТЕЛЯ
       ╳  asu_june_bot_build_index_v2.py — не существует
       ╳  asu_june_bot_chat.py — не существует
       ╳  asu_june_bot_search.py читает не v2, а main chunks.jsonl
```

### 5.3 Орфаны внутри подпроекта

- `chunks_v2.jsonl` — данные накапливаются, потребителя нет.
- `configs/asu_june_bot/llm.yaml` — контракт без кода.
- `configs/asu_june_bot/guardrails.yaml` — контракт без кода.
- `src/asu_june_bot/__init__.py` — пустой (1 строка).
- `src/asu_june_bot/retrieval/__init__.py` — только docstring, без re-export'ов.

### 5.4 Дубли с основным кодом

| Функция | В подпроекте | В основном коде |
|---|---|---|
| `normalize_text` | `ingestion/utils.py:19` | `rag_common.py:120` |
| `stable_id` (length=32 vs 24) | `ingestion/utils.py:26` | `rag_common.py:116` |
| `sha256_file` | `ingestion/utils.py:30` | `rag_common.py:105` |
| `read_text_guess` | `ingestion/utils.py:41` | `rag_common.py:155` |
| `jsonl_write` | `ingestion/utils.py:51` | `rag_common.py:55` |
| `load_config` + `resolve_work_path` | `core/config.py:35,52` | `rag_common.py:20,30` |
| `ollama_embed` | `retrieval/vector.py:23` | `scripts/03_build_index.py:14` (с retry) и `09_chat.py` |

7 дублирующихся реализаций. Это **сознательная независимость** подпроекта, но риск дрифта реален (например, разный default `stable_id` length уже дрифтит).

## 6. Интеграция С Основным `09_chat.py`

**Нулевая.** Прямой grep:

```
grep -rn "asu_june_bot" scripts/09_chat.py scripts/04_query.py
# 0 matches
```

- `09_chat.py` не импортирует ничего из `asu_june_bot`.
- `asu_june_bot_search.py` не импортирует ничего из `09_chat.py`.
- `asu_june_bot_search.py` **не пишет в `data/query_log.jsonl`** — feedback loop изолирован.
- Источник модели LLM: в основном чате `09_chat.py` использует `cfg.ollama.chat_model` (по умолчанию `qwen3:8b`); в подпроекте план — `qwen3:4b` через OpenAI-compatible adapter (`configs/asu_june_bot/llm.yaml`).

**Архитектурное расхождение:** два чата с разными моделями, разными retrieval-стратегиями, разными prompts. Подпроект декларируется как **отдельный продукт** (см. `docs/subprojects/asu-june-bot/README.md` — рабочее название «Asu June Bot», цель — «ассистент системного аналитика по проекту ЦП УПКС»).

`09_chat.py` остаётся **прототипом** по `docs/subprojects/asu-june-bot/todo.md`:

> Использовать `scripts/09_chat.py` только как prototype и источник выводов.
> Не развивать дальше `scripts/09_chat.py` как основной продуктовый контур.

## 7. Эксперименты: WhisperDesk, WhisperX, Speakr

В `docs/references/` три заметки об **отложенных** экспериментах.

### 7.1 `WHISPERDESK_EXPERIMENT.md`

**Источник:** `C:\Users\Сотрудник\Desktop\AI\WhisperDesk` — отдельный Tkinter-инструмент пользователя для live-транскрибации (mic + system audio через WASAPI loopback).

**Что взято в MeetingAgent:** CPU-профиль live (`small/int8`, ru, chunk 5s, beam 3, VAD off), идея раздельных дорожек MIC+SYS.

**Что НЕ взято:** монолитная Tkinter-реализация. По `docs/decisions.md 2026-05-07`: «WhisperDesk используется как референс, но не переносится как продуктовая основа».

**Реализация в коде:** **нет**. Live pipeline не существует. Профиль из эксперимента зафиксирован в `config.example.yaml::live_transcription:` (который, как я установил в артефакте №6, **никем не читается**).

### 7.2 `WHISPERX_EXPERIMENT.md`

**Дата:** 2026-05-08. Тестовая встреча `meetings/2026-05-08__test-meeting/`.

**Результат:** WhisperX не показал преимущества над `large-v3-turbo/int8` по качеству текста; время хуже. Diarization не тестировалась (нужны HuggingFace токены).

**Решение (`decisions.md 2026-05-08`):** «WhisperX отложен до появления потребности в word-level timestamps или diarization».

**Реализация в коде:** **нет**. ASR — только `faster-whisper` через 06/08.

**Инфраструктурная проблема:** WhisperX не ставится в основной venv (Python 3.14 несовместим с требуемым `ctranslate2`). Эксперимент запускался в отдельном venv (`%LOCALAPPDATA%\MeetingAgent\whisperx-venv312`) — вне репозитория.

### 7.3 `SPEAKR_REFERENCE.md`

**Источник:** <https://github.com/murtaza-nasir/speakr> — продуктовый референс готового приложения для записи и поиска по встречам.

**Что взято:** идеи UI/UX (страница встречи, синхронизация транскрипта с аудио, теги, политики хранения, protected records). Все они **запланированы** в roadmap MeetingAgent, не реализованы.

**Что НЕ взято:** код, архитектура, framework — ничего. Это исключительно идеологический референс. Подтверждение в `docs/decisions.md 2026-05-06 Speakr Как Продуктовый Референс`.

### 7.4 Сводка

| Эксперимент | Реализация в коде | Артефакт в репозитории |
|---|---|---|
| WhisperDesk | Нет | Только `WHISPERDESK_EXPERIMENT.md` + dead config keys `live_transcription:` |
| WhisperX | Нет | Только `WHISPERX_EXPERIMENT.md` + папка `model_compare/` в тестовой встрече (runtime, не коммитится) |
| Speakr | Нет | Только `SPEAKR_REFERENCE.md` |

Все три — **информационные**, без кодовых артефактов.

## 8. Roadmap Vs Реальность

Из `docs/subprojects/asu-june-bot/roadmap.md`:

| Этап | Цель | Статус (моя оценка по коду) |
|---|---|---|
| 0. Документация и архитектурный reset | Отделить от MeetingAgent, остановить разрастание 09_chat | **Готово.** Полный пакет docs/ + namespace src/asu_june_bot/. |
| 1. Базовый Project-only Search | `/search` с hybrid retrieval | **В основном готово.** CLI работает, source policy + query expansion реализованы. Но: над v1 корпусом, не v2. |
| 2. Project-only Chat MVP | `/chat` с answer/refusal | **Не начато.** Нет ни `chat`-CLI, ни LLM-клиента, ни project-guard, ни answer-validator. |
| 3. FastAPI API | `/search` и `/chat` endpoint'ы | Не начато. |
| 4. Базовый UI / Open WebUI | Web-интерфейс | Не начато. |
| 5. v2-индекс и переключение | `index_v2`, переход на новый корпус | **Полупуть.** v2 extract + chunk готовы; индекса нет; переключения нет. |
| 6. GPU / vLLM | Миграция на GPU-сервер | Не начато. |

**MVP scope из `mvp.md`:**

| Должно быть в MVP | Статус |
|---|---|
| Локальный запуск | Готов (только search) |
| CLI и FastAPI API | CLI — да, API — нет |
| `/search` | Да |
| `/chat` | Нет |
| Project guard | Нет |
| Hybrid retrieval | Да |
| Source metadata | Да (enrich_metadata) |
| Простая source policy | Да |
| LLM через Ollama / OpenAI-compatible | Нет |
| Ответ с citations | Нет |
| Baseline из 30+ вопросов | Частично: `docs/subprojects/asu-june-bot/eval_questions.md` существует |
| Локальное логирование | Нет в подпроекте (поиск не пишет в query_log) |

**Итого:** примерно **45-55%** MVP scope реализовано. Поиск работает, чат — нет.

## 9. Самокоррекции Артефактов №3 И №4

В предыдущих артефактах я описывал v2 как «параллельную вселенную с собственным retrieval». Это **неточно**.

### 9.1 Артефакт №3, раздел 9.6 (`chunks_v2.jsonl`)

Было сказано:

> Богатство не используется в продуктовом чате `09_chat.py` — только в `hybrid retriever` подпроекта.

**Корректно:** `chunks_v2.jsonl` НЕ используется ни продуктовым чатом, ни hybrid retriever'ом подпроекта. **Никто не читает.** Hybrid retriever работает над основным `data/chunks.jsonl`.

### 9.2 Артефакт №4, раздел 3.2 (диаграмма namespace v2)

Было нарисовано:

```
BLOCK_V2 → CHUNK_V2 → отдельный retrieval (hybrid retriever в src/asu_june_bot/retrieval/)
```

**Корректно:** hybrid retriever читает **main CHUNK**, не CHUNK_V2. Стрелка от CHUNK_V2 в retrieval **отсутствует** в реальности. CHUNK_V2 — текущий terminal node без потребителя.

### 9.3 Артефакт №4, раздел 3.3 («Граница»)

Строка таблицы:

> Index backend | (main): NumpyRagIndex | (v2): hybrid retriever в коде, без отдельного persisted index

**Корректно:** **обе** колонки в реальности используют `NumpyRagIndex` поверх **main numpy_index**. Подпроект только добавляет BM25 (in-memory) и source policy сверху.

### 9.4 План правок

Эти три расхождения существенны для понимания архитектуры. Предлагаю исправить их в отдельном коммите после завершения серии — точечными правками в №3 и №4. Не вношу прямо сейчас, чтобы не дробить артефакт №7.

## 10. Что Не Было Проверено

- **Реальная работоспособность `asu_june_bot_search.py`** на моей машине (нет `data/numpy_index` для прогона). `[?]`
- **`text_hash` и прочие хелперы в `ingestion/utils.py`** — посмотрел только первую половину файла. `[?]`
- **Содержимое `docs/subprojects/asu-june-bot/{decisions.md, RUNBOOK_V2.md, eval_questions.md}`** — не разворачивал. `[?]`
- **Подключение `asu_june_bot_search` к `query_log`** — категорически утверждаю, что нет, но не сверял подробно с возможным append-on-error. `[?]`
- **Соответствие YAML и Python-defaults в `source_policy`** — проверил поверхностно, выглядят согласованными. Расхождения возможны. `[?]`
- **`asu_june_bot.core.config.deep_merge` корректность** — не проверял на edge cases (списки vs словари). `[?]`
- **План `index_v2`** — упомянут только в одной строке `chunking_strategy.md`. Не разворачивал, какой это должен быть backend (FAISS? Qdrant? новый numpy?). `[?]`
