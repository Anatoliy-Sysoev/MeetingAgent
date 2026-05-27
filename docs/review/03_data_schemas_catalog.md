# Каталог Данных И Схем

Артефакт №3 серии полного ревью. Описывает **все JSON / JSONL / NPY / Markdown структуры**, которыми обмениваются скрипты репозитория: формальные JSON-схемы, неявные форматы, продьюсеры и потребители.

Цель: при чтении любого файла из `data/`, `meetings/<id>/`, `logs/` сразу знать, какое поле что значит, кто его пишет и кто читает.

## Содержание

1. [Как читать таблицы](#1-как-читать-таблицы)
2. [Сводка структур по слоям](#2-сводка-структур-по-слоям)
3. [Слой 1. Корпус RAG](#3-слой-1-корпус-rag)
4. [Слой 2. Логирование запросов и ссылки на источники](#4-слой-2-логирование-запросов-и-ссылки-на-источники)
5. [Слой 3. Карточка встречи (meeting.json)](#5-слой-3-карточка-встречи-meetingjson)
6. [Слой 4. Транскрипт встречи](#6-слой-4-транскрипт-встречи)
7. [Слой 5. Артефакты встречи (LLM-выходы)](#7-слой-5-артефакты-встречи-llm-выходы)
8. [Слой 6. Промежуточные партишены pipeline](#8-слой-6-промежуточные-партишены-pipeline)
9. [Слой 7. Подпроект Asu June Bot v2](#9-слой-7-подпроект-asu-june-bot-v2)
10. [Слой 8. Локи, маркеры, логи](#10-слой-8-локи-маркеры-логи)
11. [Сквозные паттерны](#11-сквозные-паттерны)
12. [Расхождения схема vs код](#12-расхождения-схема-vs-код)
13. [Что не было проверено](#13-что-не-было-проверено)

## 1. Как Читать Таблицы

В каждой таблице полей колонки:

- **Поле** — имя ключа в JSON.
- **Тип** — `string`, `int`, `float`, `bool`, `array`, `object`, `null`. Для enum явно перечислены значения.
- **Обязательность** — `required` / `optional` / `derived` (вычисляется автоматически).
- **Источник** — какой скрипт пишет.
- **Описание** — что значит и как используется.

В заголовке каждой структуры:

- **Файл** — путь в репозитории (с шаблонами `<…>`).
- **Формат** — JSON, JSONL (одна JSON-строка на запись), NPY, Markdown, plain text.
- **Кардинальность** — сколько таких файлов одновременно.
- **Жизненный цикл** — кем создаётся, кем обновляется, когда удаляется.
- **Схема** — путь к формальной JSON-схеме, если есть.
- **Продьюсер / Потребитель** — конкретные скрипты.

## 2. Сводка Структур По Слоям

| Слой | Структура | Файл | Формат | Кардинальность |
|---|---|---|---|---|
| 1 | Inventory | `data/manifest.jsonl` | JSONL | 1 |
| 1 | Extracted text metadata | `data/extracted_text/_metadata.jsonl` | JSONL | 1 |
| 1 | Extracted text files | `data/extracted_text/<rel_id>.<sha256_short>.txt` | text | N |
| 1 | Chunks | `data/chunks.jsonl` | JSONL | 1 |
| 1 | Embedding cache | `data/embeddings_cache.jsonl` | JSONL append-only | 1 |
| 1 | Numpy index — vectors | `data/numpy_index/embeddings.npy` | NPY float32 | 1 |
| 1 | Numpy index — metadata | `data/numpy_index/metadata.jsonl` | JSONL | 1 |
| 1 | Numpy index — manifest | `data/numpy_index/manifest.json` | JSON | 1 |
| 2 | Query log | `data/query_log.jsonl` | JSONL append-only | 1 |
| 2 | Source links | `data/source_links.json` | JSON map | 0..1 (опционально) |
| 3 | Meeting card | `meetings/<id>/meeting.json` | JSON | N (одна на встречу) |
| 4 | Transcript segments | `meetings/<id>/transcript/segments.jsonl` | JSONL | 1 на встречу |
| 4 | Transcript markdown | `meetings/<id>/transcript/transcript.md` | Markdown | 1 на встречу |
| 5 | Decisions | `meetings/<id>/artifacts/decisions.json` | JSON | 1 на встречу |
| 5 | Tasks | `meetings/<id>/artifacts/tasks.json` | JSON | 1 на встречу |
| 5 | Risks | `meetings/<id>/artifacts/risks.json` | JSON | 1 на встречу |
| 5 | Open questions | `meetings/<id>/artifacts/open_questions.json` | JSON | 1 на встречу |
| 5 | Memo | `meetings/<id>/artifacts/memo.md` | Markdown | 1 на встречу |
| 5 | Protocol | `meetings/<id>/artifacts/protocol.md` | Markdown | 1 на встречу |
| 5 | Pipeline report | `meetings/<id>/artifacts/pipeline_report.md` | Markdown | 1 на встречу |
| 6 | Window partials | `meetings/<id>/artifacts/_partials/window_<id>.{raw.txt,json,error.json}` | mixed | N окон |
| 6 | Reduce partials | `meetings/<id>/artifacts/_partials/reduce.{raw.txt,json}` | mixed | 1 |
| 6 | Render partials | `meetings/<id>/artifacts/_partials/render.{raw.txt,json}` | mixed | 0..1 |
| 6 | Window audio (08 pipeline) | `meetings/<id>/transcript/chunks/W<NN>.audio.wav` | WAV | N |
| 6 | Window segments (08) | `meetings/<id>/transcript/chunks/W<NN>.segments.jsonl` | JSONL | N |
| 7 | Subproject documents | `data/asu_june_bot/extracted_v2/documents.jsonl` | JSONL append-only | 1 |
| 7 | Subproject blocks | `data/asu_june_bot/extracted_v2/blocks.jsonl` | JSONL append-only | 1 |
| 7 | Subproject errors | `data/asu_june_bot/extracted_v2/errors.jsonl` | JSONL append-only | 1 |
| 7 | Subproject progress | `data/asu_june_bot/extracted_v2/extraction_v2_progress.json` | JSON | 1 |
| 7 | Subproject extraction report | `data/asu_june_bot/extracted_v2/extraction_v2_report.{json,md}` | JSON+MD | 1 |
| 7 | Subproject chunks v2 | `data/asu_june_bot/chunks_v2.jsonl` | JSONL (full rewrite) | 1 |
| 7 | Subproject chunking report | `data/asu_june_bot/chunking_v2_report.{json,md}` | JSON+MD | 1 |
| 7 | Subproject source audit | `data/asu_june_bot/source_audit_v2_report.json` | JSON | 1 |
| 8 | RAG build lock | `logs/build_index.lock` | text (PID) | 0..1 |
| 8 | RAG build log | `logs/full_rag_<stamp>.log` | text | N |
| 8 | RAG build markers | `logs/full_rag_<stamp>.{done,failed}.txt` | text | N |
| 8 | Subproject build logs | `logs/asu_june_bot_*_v2_<stamp>.{log,done.txt,failed.txt}` | text | N |
| 8 | Watchdog state | `logs/.asu_june_bot_v2_watchdog_state.json` | JSON | 1 |
| 8 | Watchdog log | `logs/asu_june_bot_v2_watchdog.log` | text | 1 |

## 3. Слой 1. Корпус RAG

### 3.1 `data/manifest.jsonl`

**Назначение:** инвентаризация всех файлов в `project_root` с фильтрацией по `include_extensions`, `exclude_dirs`, `exclude_path_patterns`.

**Формат:** JSONL, одна запись на найденный файл.
**Кардинальность:** один файл на репозиторий.
**Жизненный цикл:** **полностью перезаписывается** на каждом запуске `01_inventory.py` (через `jsonl_write`).

**Продьюсер:** `scripts/01_inventory.py:83` — `jsonl_write(manifest_path, rows)`.
**Потребители:**
- `scripts/02_extract_text.py:122` — итерирует записи, обрабатывает только `status == "included"`.
- Любой ручной анализ (нет других программных потребителей).

#### Поля записи

| Поле | Тип | Обязательность | Источник | Описание |
|---|---|---|---|---|
| `path` | string | required | `01:72` | Абсолютный путь к файлу в `project_root`. |
| `relative_path` | string | required | `01:73` через `path_rel_to_project` | Относительный путь от `project_root`, нормализованный к `/`. |
| `extension` | string | required | `01:74` | `path.suffix.lower()` (включая точку: `.docx`). |
| `size` | int | required | `01:75` | Размер файла в байтах. |
| `mtime` | float | required | `01:76` | Unix-timestamp последней модификации. |
| `sha256` | string\|null | required | `01:77` | Hex sha256 (64 символа). `null` если файл `excluded` или `unsupported`. |
| `status` | enum | required | `01:78` | `included`, `excluded`, `unsupported`, `error`. |
| `reason` | string | required | `01:79` | Причина статуса: `ok`, `office_temp_file`, `excluded_dir`, `excluded_path_pattern`, `excluded_extension`, `unsupported_extension`, `sha256_error: <msg>`. |

### 3.2 `data/extracted_text/_metadata.jsonl`

**Назначение:** метаданные извлечённых текстовых файлов; связь `manifest record ↔ extracted_text/<file>.txt`.

**Формат:** JSONL.
**Кардинальность:** один файл на репозиторий (внутри `extracted_text/`).
**Жизненный цикл:** полностью перезаписывается каждым запуском `02_extract_text.py:169`.

**Продьюсер:** `scripts/02_extract_text.py`.
**Потребители:** `scripts/03_build_index.py:51-56` — итерирует, читает `extracted_path` и нарезает на chunks.

#### Поля записи (успешная)

| Поле | Тип | Обязательность | Источник | Описание |
|---|---|---|---|---|
| `source_path` | string | required | `02:147` | Абсолютный путь источника. |
| `relative_path` | string | required | `02:148` | Относительный путь от `project_root`. |
| `extension` | string | required | `02:149` | Расширение источника. |
| `sha256` | string | required | `02:150` | Sha256 источника (копируется из manifest). |
| `mtime` | float | required | `02:151` | Mtime источника. |
| `extracted_path` | string | required | `02:152` | Путь к `data/extracted_text/<rel_id>.<sha256[:12]>.txt`. |
| `chars` | int | required | `02:153` | Количество символов в нормализованном тексте. |

#### Поля записи (ошибка)

| Поле | Тип | Описание |
|---|---|---|
| `source_path`, `relative_path`, `extension`, `sha256` | как в успешной | |
| `error` | string | `repr(exc)`. **Все ошибки извлечения собираются в этот же JSONL**, отличаются от успешных только наличием `error` и отсутствием `extracted_path` / `chars`. |

### 3.3 `data/extracted_text/<rel_id>.<sha256_short>.txt`

**Назначение:** нормализованный текст одного файла; используется `03_build_index.py` для chunking.

**Формат:** plain UTF-8 текст. Имя: `<safe_rel_id>.<sha256[:12]>.txt`.
**Кардинальность:** один файл на каждый успешно извлечённый источник.
**Жизненный цикл:** перезаписывается при каждом запуске `02` (старые файлы остаются, если sha256 не изменился — будут считаться валидным cache).

**Структура содержимого** (из `02:135-139`): секции склеены через `\n\n`, каждая секция начинается с `# <section name>\n\n<text>`. Возможные имена секций:

| Section | Происхождение |
|---|---|
| `document` | docx (весь текст + таблицы). |
| `page <N>` | pdf, одна секция на страницу. |
| `slide <N>` | pptx, одна секция на слайд. |
| `sheet <name>` | xlsx/xlsb, одна секция на лист, в формате TSV. |
| `html` | html после очистки `<script>/<style>/<noscript>`. |
| `file` | любой plain-text файл. |

### 3.4 `data/chunks.jsonl`

**Назначение:** все chunks текущего корпуса, готовые к embedding.

**Формат:** JSONL.
**Кардинальность:** один файл на репозиторий.
**Жизненный цикл:** полностью перезаписывается `03_build_index.py:125` (`jsonl_write`).

**Продьюсер:** `scripts/03_build_index.py:49-80`.
**Потребители:**
- `scripts/05_build_numpy_index.py` → `rag_numpy_backend.build_index` (читает все chunks).
- `scripts/04_query.py:105` — fallback, когда нет numpy-индекса (`query_from_jsonl_cache`).
- `scripts/09_chat.py:437-441` — `load_document_chunks(relative_path)` для document expansion (читает chunks.jsonl целиком на каждый расширяемый документ).

#### Поля записи

| Поле | Тип | Обязательность | Источник | Описание |
|---|---|---|---|---|
| `chunk_id` | string (sha256 hex, 24 символа) | required | `03:64` через `stable_id(f"{sha256}:{index}:{chunk[:120]}")` | **Стабильный** идентификатор для cache embeddings. Не зависит от пути файла → одинаковый chunk в двух копиях документа делит embedding. |
| `db_id` | string (sha256 hex, 24 символа) | required | `03:65` через `stable_id(f"{relative_path}:{sha256}:{index}:{chunk[:120]}")` | Уникальный идентификатор для ChromaDB (legacy, ChromaDB не используется в основном пути, но поле сохранено для совместимости). |
| `text` | string | required | `03:70` | Нормализованный chunk текста (`normalize_text` уже применён в 02). |
| `source_path` | string | required | `03:71` | Абсолютный путь источника. |
| `relative_path` | string | required | `03:72` | Относительный путь от `project_root`. |
| `extension` | string | required | `03:73` | Расширение источника. |
| `sha256` | string | required | `03:74` | Sha256 источника. |
| `mtime` | float | required | `03:75` | Mtime источника. |
| `chunk_index` | int | required | `03:76` | Позиция chunk внутри документа (0-based). |
| `chars` | int | required | `03:77` | Длина `text` в символах. |

### 3.5 `data/embeddings_cache.jsonl`

**Назначение:** переиспользуемый cache embeddings; ключ — `chunk_id`.

**Формат:** JSONL **append-only**.
**Кардинальность:** один файл.
**Жизненный цикл:** **никогда не очищается** автоматически. Записи stale (для удалённых/изменённых chunks) сохраняются. Решение зафиксировано в `docs/decisions.md` 2026-05-06.

**Продьюсер:** `scripts/03_build_index.py:105-108` — `append_embedding_cache(path, rec)` дописывает по одной записи.
**Потребители:**
- `scripts/03_build_index.py:127` — `load_embedding_cache` (skip уже обработанных chunks).
- `scripts/05_build_numpy_index.py` через `rag_numpy_backend.build_index` (загружает в матрицу).
- `scripts/04_query.py:107` (fallback без numpy-индекса).
- `scripts/rag_numpy_backend.py:51-60` — общая функция загрузки.

#### Поля записи

| Поле | Тип | Обязательность | Источник | Описание |
|---|---|---|---|---|
| `chunk_id` | string | required | `03:151` | Ключ. |
| `embedding_model` | string | required | `03:152` | Имя модели (например `bge-m3`). Фильтр при загрузке: записи других моделей игнорируются. |
| `embedding` | array of float | required | `03:153` | Вектор. Длина зависит от модели (для `bge-m3` = 1024). |
| `source_path` | string | required | `03:154` | Дублируется из chunks для self-contained cache. |
| `relative_path` | string | required | `03:155` | Аналогично. |
| `extension` | string | required | `03:156` | Аналогично. |
| `sha256` | string | required | `03:157` | Аналогично. |
| `mtime` | float | required | `03:158` | Аналогично. |
| `chunk_index` | int | required | `03:159` | Аналогично. |
| `chars` | int | required | `03:160` | Аналогично. |

**Известная проблема:** битые строки JSON молча пропускаются в `03:94`, `rag_numpy_backend.py:51-60`, `04_query.py:107`. Cache corruption не диагностируется.

### 3.6 `data/numpy_index/`

Атомарно собираемая директория. Сборка: `scripts/05_build_numpy_index.py` → `rag_numpy_backend.build_index`. Сначала создаётся `<dir>.tmp/`, потом `shutil.move` в финальный путь — гарантирует, что неполный индекс не виден потребителям.

#### 3.6.1 `embeddings.npy`

**Назначение:** матрица L2-нормализованных embeddings.
**Формат:** NPY (`numpy.save`), shape `(N, embedding_dim)`, dtype `float32`.
**Загрузка:** через `mmap_mode="r"` в `NumpyRagIndex.__init__`.
**Заметный факт:** нормализация выполняется при сборке (`rag_numpy_backend.py:24-26`), поэтому query тоже нормализуется и cosine ≡ dot product.

#### 3.6.2 `metadata.jsonl`

**Назначение:** одна запись на строку матрицы embeddings, тот же порядок что и в `.npy`.
**Формат:** JSONL.

#### Поля записи

| Поле | Тип | Источник | Описание |
|---|---|---|---|
| `row_id` | int | `rag_numpy_backend.py:95` | Индекс строки в матрице (0-based). |
| `document` | string | `:96` | Текст chunk (копируется из `chunks.jsonl.text`). |
| `metadata.chunk_id` | string | `:98` | Копия из chunks. |
| `metadata.db_id` | string\|null | `:99` | Копия. |
| `metadata.source_path` | string | `:100` | Копия. |
| `metadata.relative_path` | string | `:101` | Копия. |
| `metadata.extension` | string | `:102` | Копия. |
| `metadata.sha256` | string | `:103` | Копия. |
| `metadata.mtime` | float | `:104` | Копия. |
| `metadata.chunk_index` | int | `:105` | Копия. |
| `metadata.chars` | int | `:106` | Копия. |

#### 3.6.3 `manifest.json`

**Назначение:** манифест индекса: версия, модель, размерности, источник.
**Формат:** JSON-объект (один).
**Источник:** `rag_numpy_backend.py:124-139`.

| Поле | Тип | Описание |
|---|---|---|
| `version` | int | Версия формата индекса (`INDEX_VERSION = 1`). |
| `backend` | string | Всегда `"numpy"`. |
| `embedding_model` | string | Имя модели (`bge-m3`). |
| `embedding_dim` | int | Размерность вектора. |
| `count` | int | Число записей (равно `embeddings.shape[0]` и числу строк `metadata.jsonl`). При load проверяется консистентность (`:157-160`). |
| `created_at` | string | ISO-8601 UTC timestamp создания. |
| `source.chunks.path` | string | Путь к `chunks.jsonl`, из которого собран индекс. |
| `source.chunks.size` | int | Размер `chunks.jsonl` на момент сборки. |
| `source.chunks.mtime` | float | Mtime `chunks.jsonl`. |
| `source.embeddings_cache.{path,size,mtime}` | string/int/float | То же для `embeddings_cache.jsonl`. |
| `files.embeddings` | string | Имя файла векторов (`"embeddings.npy"`). |
| `files.metadata` | string | Имя файла метаданных (`"metadata.jsonl"`). |

Поле `source` позволяет диагностически сверить, на каком корпусе собран индекс. Программно нигде не проверяется (это только справочная информация).

## 4. Слой 2. Логирование Запросов И Ссылки На Источники

### 4.1 `data/query_log.jsonl`

**Назначение:** лог всех запросов к RAG для feedback-loop.

**Формат:** JSONL **append-only**.
**Кардинальность:** один файл.
**Жизненный цикл:** дописывается на каждый запрос. Никогда не очищается автоматически. Sensitive-запросы (по фильтру `rag_common.is_sensitive_query`) **не пишутся**.

**Продьюсер:** `rag_common.append_query_log`.
**Зовут:**
- `scripts/09_chat.py:emit` (через `build_query_log_record`).
- `scripts/04_query.py:main` (для каждого из трёх режимов: `raw`, `compact`, `llm`).

**Потребители:** ручной анализ согласно `docs/quality/QUERY_FEEDBACK_LOOP.md`. Программных потребителей пока нет.

#### Поля записи (источник `09_chat`)

| Поле | Тип | Источник | Описание |
|---|---|---|---|
| `ts` | string | `rag_common.append_query_log` | ISO-8601 UTC timestamp (проставляется автоматически, если не было в record). |
| `source` | string | `09:build_query_log_record` | Всегда `"09_chat"`. |
| `question` | string | `:question` | Сам вопрос. |
| `status` | enum | result | `"answered"` или `"refused"`. |
| `refusal_reason` | string\|null | result | `out_of_scope_or_no_relevant_sources`, `obviously_out_of_project_scope`, `sensitive_or_system_request`, `rag_index_not_found`, `llm_error`, `llm_empty_response`. |
| `answer_mode` | string\|null | result | `"llm"`, `"extractive_fallback"`, `"sources_only"`. |
| `confidence` | float | result | `confidence_from_sources` (top_score / threshold, clamp 0..1). |
| `top_sources` | array of object | `09:611` (build) | До 8 источников: `{relative_path, chunk_index, score}` (score округлён до 6 знаков). |
| `answer` | string\|null | result | Текст ответа, если `status=answered`. Иначе `null`. |
| `params.top_k` | int | args | `--top-k`. |
| `params.score_threshold` | float | args | `--score-threshold`. |
| `params.min_sources` | int | args | `--min-sources`. |
| `params.model` | string\|null | args | `--model` или `null`. |
| `params.sources_only` | bool | args | `--sources-only`. |

#### Поля записи (источник `04_query`)

| Поле | Тип | Описание |
|---|---|---|
| `ts`, `source` | как выше | `source = "04_query"`. |
| `question` | string | |
| `mode` | enum | `"raw"`, `"compact"`, `"llm"`. |
| `top_sources` | array | До 8 источников: `{relative_path, chunk_index, score}`. |
| `answer` | string\|null | Текст ответа в режиме `llm`, иначе `null`. |
| `params.top_k`, `params.include_excluded`, `params.dedupe` | int/bool | |

**Заметный факт:** sensitive-фильтр в `rag_common.is_sensitive_query` отличается от `SENSITIVE_PATTERNS` в `09_chat.py` — `09_chat` дополнительно блокирует `"инструкции модели"`, `"developer message"`, `"пароли"`. Эти запросы из `09_chat` режутся раньше, поэтому в `query_log` не попадут. А из `04_query` — попадут, если не содержат паттерн из общего списка. См. артефакт №5 ревью.

### 4.2 `data/source_links.json`

**Назначение:** карта `relative_path → URL` для добавления ссылок на источники в ответах чата.

**Формат:** JSON-объект.
**Кардинальность:** один файл, **опциональный** (если отсутствует — `load_source_links` возвращает `{}`).

**Продьюсер:** **нет** (создаётся вручную пользователем).
**Потребитель:** `scripts/09_chat.py:load_source_links` (`:251-267`).

**Допустимые форматы значений:**

```json
{
  "relative/path/to/file.docx": "https://example.com/file.docx",
  "relative/path/to/other.docx": {"url": "https://example.com/other.docx"}
}
```

Реальная схема — `dict[str, str | {url: str}]`. Любые другие значения игнорируются (`isinstance(value, str)` или `isinstance(value, dict) and isinstance(value.get("url"), str)`).

**Битый JSON или отсутствующий файл — не ошибка**: возвращается пустой словарь без логов.

## 5. Слой 3. Карточка Встречи (meeting.json)

### 5.1 `meetings/<meeting_id>/meeting.json`

**Назначение:** машинный контракт карточки встречи. Видимое состояние всей обработки одной встречи.

**Формат:** JSON-объект.
**Кардинальность:** один файл на встречу.
**Формальная схема:** `configs/schemas/meeting.schema.json` (Draft 2020-12, `$id: https://meetingagent.local/schemas/meeting.schema.json`).
**Жизненный цикл:**
- Создаётся **вручную** или по шаблону `docs/examples/meeting.new.example.json` со статусом `"new"`.
- `06_transcribe_meeting.py` переводит в `transcribing` → `transcribed`.
- `07_generate_meeting_artifacts.py` переводит в `summarized`.
- `08_process_meeting_pipeline.py` оркеструет `processing` → `summarized`.
- `failed` устанавливается любым из 06/07/08 при ошибке.
- `classified` и `indexed` — **в коде не устанавливаются ни одним скриптом** (зарезервированы в схеме, см. артефакт №6 ревью).

**Валидация:** `validate_schema` в `06_transcribe_meeting.py:101+` и `07_generate_meeting_artifacts.py`. **Каждое обновление meeting.json валидируется перед записью.**

**Запись:** атомарно через `write_json_atomic` (07:101 — пишет в `.tmp`, потом `os.replace`).

#### 5.1.1 Корневые обязательные поля

| Поле | Тип | Описание |
|---|---|---|
| `schema_version` | int | Всегда `1`. Меняется только при явной миграции (`docs/decisions.md` 2026-05-07). |
| `meeting_id` | string | Slug `YYYY-MM-DD__short-title`. Pattern: `^\d{4}-\d{2}-\d{2}__[a-z0-9]+(?:-[a-z0-9]+)*$`. |
| `title` | string (minLength 1) | Человекочитаемый заголовок. |
| `date` | string (date) | `YYYY-MM-DD`. |
| `processing_status` | enum | См. ниже. |
| `participants` | array of string (unique) | Просто список имён без diarization. |
| `source` | object | См. 5.1.2. |
| `artifacts` | object | См. 5.1.3. |
| `classification` | object | См. 5.1.4. |
| `links` | object | См. 5.1.5. |
| `retention` | object | См. 5.1.6. |
| `rag` | object | См. 5.1.7. |
| `created_at` | string (date-time) | ISO-8601. |
| `updated_at` | string (date-time) | ISO-8601. Обновляется каждой записью. |

#### 5.1.2 `source` (источник записи)

| Поле | Тип | Required | Описание |
|---|---|---|---|
| `kind` | enum | yes | `offline_record`, `live_session`. |
| `original_location` | string | no | Откуда пришла запись. |
| `media_files` | array of media_file | no | См. ниже. |
| `audio_tracks` | array enum | no | `MIC`, `SYS` (unique). Для live MVP оба обязательны как «источники истины» по `decisions.md`. |
| `derived_tracks` | array enum | no | Только `MIX`. |
| `notes` | string | no | |

`media_file`:

| Поле | Тип | Required | Описание |
|---|---|---|---|
| `path` | string | yes | Относительный путь внутри папки встречи. |
| `media_type` | enum | yes | `video`, `audio`, `screen_recording`, `other`. |
| `sha256` | string (64 hex) | no | |
| `duration_seconds` | number ≥ 0 | no | |

#### 5.1.3 `artifacts` (относительные пути)

Все значения — относительные пути внутри `meetings/<id>/`. Отсутствие поля = артефакт ещё не создан.

| Поле | Куда указывает | Кто пишет |
|---|---|---|
| `transcript` | `transcript/transcript.md` | `06:386` |
| `segments` | `transcript/segments.jsonl` | `06:387` |
| `memo` | `artifacts/memo.md` | `07`/`08` |
| `protocol` | `artifacts/protocol.md` | `07`/`08` |
| `decisions` | `artifacts/decisions.json` | `07`/`08` |
| `tasks` | `artifacts/tasks.json` | `07`/`08` |
| `risks` | `artifacts/risks.json` | `07`/`08` |
| `open_questions` | `artifacts/open_questions.json` | `07`/`08` |
| `pipeline_report` | `artifacts/pipeline_report.md` | `08:989` |
| `classification_report` | — | **никто** (зарезервировано) |

#### 5.1.4 `classification` (вся секция — зарезервирована)

| Поле | Тип | Описание |
|---|---|---|
| `project_stage` | string (pattern `^PRJ-\d{2}$`) | Код этапа из `docs/product/PROJECT_TAXONOMY.md`. |
| `ftt_candidates` | array of `classification_candidate` | |
| `document_candidates` | array of `classification_candidate` | |
| `task_candidates` | array of `classification_candidate` | |
| `confidence` | number 0..1 | |
| `summary` | string | |
| `needs_review` | bool | |

`classification_candidate`: `{id (required), title, confidence (0..1), source_refs[]}`.

**В коде сейчас ни один скрипт эту секцию не пишет.** Классификатор не реализован, см. артефакт №6 ревью.

#### 5.1.5 `links`

| Поле | Тип |
|---|---|
| `related_documents`, `related_meetings`, `related_decisions` | array of `related_link` |

`related_link`: `{id_or_path (required), title, relation, confidence}`. Никем не пишется в текущем коде.

#### 5.1.6 `retention`

| Поле | Тип | Required | Описание |
|---|---|---|---|
| `policy` | enum | yes | `default`, `protected`. См. `decisions.md` 2026-05-07 «Политика Ротации Медиа». |
| `reason` | string | no | Когда `protected` — желательна. |
| `review_after` | string (date) | no | |
| `media_delete_after_days` | int ≥ 0 | no | |

#### 5.1.7 `rag`

| Поле | Тип | Required | Описание |
|---|---|---|---|
| `index_policy` | enum | yes | `structured_artifacts_and_final_transcript`, `do_not_index`. |
| `indexed_artifacts` | array of relative_path (unique) | no | |
| `no_index_artifacts` | array of relative_path (unique) | no | |
| `last_indexed_at` | string (date-time) | no | |

**В коде сейчас никто не индексирует артефакты встречи в основной RAG.** Поля задают будущий контракт.

#### 5.1.8 `last_error` (failure-safe)

Optional, очищается при успешном повторном запуске (`06:391`, `07:649`).

| Поле | Тип | Required |
|---|---|---|
| `stage` | string | yes |
| `message` | string | yes |
| `type` | string | no |
| `timestamp` | string (date-time) | yes |

#### 5.1.9 Реально записываемые значения `processing_status`

| Статус | Кем пишется | Где |
|---|---|---|
| `new` | вручную (шаблон) | `docs/examples/meeting.new.example.json` |
| `processing` | `08` | `08:834` |
| `transcribing` | `06` | `06:356` |
| `transcribed` | `06` | `06:389` |
| `summarized` | `07`/`08` | `07:1016`, `08:991` |
| `failed` | `06`/`07`/`08` | `06:255`, `07:640`, `08:220` |
| `classified` | **никто** | — |
| `indexed` | **никто** | — |

## 6. Слой 4. Транскрипт Встречи

### 6.1 `meetings/<id>/transcript/segments.jsonl`

**Назначение:** машинный transcript со временными метками для использования в map-reduce pipeline и для source_refs.

**Формат:** JSONL.
**Продьюсер:** `06_transcribe_meeting.py:239-243` (`write_segments_jsonl`).
**Потребители:** `07_generate_meeting_artifacts.py` (build_segment_windows), `08_process_meeting_pipeline.py` (через `artifacts07.read_json` для нормализации source_refs).

#### Поля записи

| Поле | Тип | Источник | Описание |
|---|---|---|---|
| `start` | float | `06:296` | Секунды от начала медиа (округлены до 3 знаков). |
| `end` | float | `06:297` | Секунды. |
| `text` | string | `06:298` | Текст сегмента, trimmed. |
| `source` | enum | `06:299` | Сейчас **всегда `"MIX"`**. Схема `meeting.json` позволяет `MIC`/`SYS`, но 06 не различает дорожки. |

**Неявный «segment_index»:** это номер строки в JSONL (0-based). Используется в `source_refs.segment_index` артефактов.

### 6.2 `meetings/<id>/transcript/transcript.md`

**Назначение:** человекочитаемый transcript.
**Формат:** Markdown, генерируется `06_transcribe_meeting.py:build_markdown_transcript`.
**Структура:** заголовок встречи + метаданные модели + блоки `[HH:MM:SS - HH:MM:SS]\n<text>`.
**Программных потребителей нет** (только глазами).

## 7. Слой 5. Артефакты Встречи (LLM-Выходы)

Все четыре JSON-артефакта имеют идентичную верхнюю структуру и идентичный `source_ref`. Меняется только формат `items[i]`.

### 7.1 Общая структура корня

| Поле | Тип | Required | Описание |
|---|---|---|---|
| `schema_version` | int | yes | Всегда `1`. |
| `meeting_id` | string | yes | Pattern совпадает с `meeting.json`. |
| `generated_at` | string (date-time) | yes | |
| `items` | array | yes | См. подсхемы ниже. |

### 7.2 Общий `source_ref`

Используется во всех 4 артефактах (decisions, tasks, risks, open_questions). `source_refs` обязателен, `minItems: 1`.

| Поле | Тип | Required | Описание |
|---|---|---|---|
| `kind` | enum | yes | `transcript_segment`, `rag_source`, `manual_note`. |
| `path` | string | yes | Относительный путь источника: для `transcript_segment` → `transcript/segments.jsonl`; для `rag_source` → `relative_path` из чанка. |
| `segment_index` | int ≥ 0 | no | Номер строки в `segments.jsonl` (для `transcript_segment`). |
| `start` | number ≥ 0 | no | Таймкод начала (для `transcript_segment`). |
| `end` | number ≥ 0 | no | Таймкод конца. |
| `quote` | string ≤ 500 | no | Цитата. |
| `score` | number 0..1 | no | Score для `rag_source`. |

В `08_process_meeting_pipeline.py` финальные source_refs **нормализуются** по реальному `transcript/segments.jsonl` (восстанавливаются точные `segment_index`/`start`/`end`).

### 7.3 `meetings/<id>/artifacts/decisions.json`

**Схема:** `configs/schemas/meeting.decisions.schema.json`.

Поле `items[i]` (decision):

| Поле | Тип | Required | Описание |
|---|---|---|---|
| `decision_id` | string (pattern `^DEC-\d{3}$`) | yes | |
| `title` | string (minLength 1) | yes | |
| `decision` | string (minLength 1) | yes | Формулировка решения. |
| `rationale` | string | no | |
| `status` | enum | yes | `proposed`, `accepted`, `rejected`, `superseded`. |
| `owner` | string | no | |
| `due_date` | string (date) | no | |
| `source_refs` | array (minItems 1) | yes | |
| `needs_review` | bool | no | Помечает сомнительные выводы LLM. |

### 7.4 `meetings/<id>/artifacts/tasks.json`

**Схема:** `configs/schemas/meeting.tasks.schema.json`.

| Поле | Тип | Required | Описание |
|---|---|---|---|
| `task_id` | string (pattern `^TASK-\d{3}$`) | yes | |
| `title` | string | yes | |
| `description` | string | no | |
| `owner` | string | no | |
| `due_date` | string (date) | no | |
| `status` | enum | yes | `open`, `in_progress`, `done`, `blocked`, `cancelled`. |
| `priority` | enum | no | `low`, `normal`, `high` (default `normal`). |
| `source_refs` | array (minItems 1) | yes | |
| `needs_review` | bool | no | |

### 7.5 `meetings/<id>/artifacts/risks.json`

**Схема:** `configs/schemas/meeting.risks.schema.json`.

| Поле | Тип | Required | Описание |
|---|---|---|---|
| `risk_id` | string (pattern `^RISK-\d{3}$`) | yes | |
| `title` | string | yes | |
| `description` | string | yes | |
| `impact` | enum | yes | `low`, `medium`, `high`. |
| `probability` | enum | yes | `low`, `medium`, `high`. |
| `mitigation` | string | no | |
| `owner` | string | no | |
| `status` | enum | yes | `open`, `monitoring`, `mitigated`, `closed`. |
| `source_refs` | array (minItems 1) | yes | |
| `needs_review` | bool | no | |

### 7.6 `meetings/<id>/artifacts/open_questions.json`

**Схема:** `configs/schemas/meeting.open_questions.schema.json`.

| Поле | Тип | Required | Описание |
|---|---|---|---|
| `question_id` | string (pattern `^Q-\d{3}$`) | yes | |
| `question` | string | yes | |
| `context` | string | no | |
| `owner` | string | no | |
| `due_date` | string (date) | no | |
| `status` | enum | yes | `open`, `answered`, `closed`. |
| `answer` | string | no | |
| `source_refs` | array (minItems 1) | yes | |
| `needs_review` | bool | no | |

### 7.7 `meetings/<id>/artifacts/{memo,protocol}.md`

**Формат:** Markdown.
**Продьюсер:** `07_generate_meeting_artifacts.py` (`render_markdown_documents`), `08_process_meeting_pipeline.py` (`render_documents` + `write_text_atomic`).
**Контракт:** должны быть **представлением** структурированных JSON (`docs/decisions.md` 2026-05-07). Расхождения с JSON считаются багом.

### 7.8 `meetings/<id>/artifacts/pipeline_report.md`

**Формат:** Markdown.
**Продьюсер:** `08_process_meeting_pipeline.py:build_pipeline_report` (`:729`+) → `write_text_atomic(... pipeline_report.md ...)` (`:983`).
**Содержимое:** параметры запуска (модель, top_k, окно), время каждой стадии (ASR/MAP/REDUCE/RENDER), статистика восстановления `source_refs`, перечень окон. Используется человеком для контроля.

Программных потребителей нет.

## 8. Слой 6. Промежуточные Партишены Pipeline

Папка `meetings/<id>/artifacts/_partials/`. **Создаётся, пересоздаётся и используется как resume-cache** для повторных запусков 07/08.

### 8.1 `_partials/window_<id>.json`

**Назначение:** распарсенный MAP-вывод одного окна.
**Структура (контракт MAP-prompt):**

```json
{
  "window_id": "W01",
  "decisions": [ /* decision items без decision_id */ ],
  "tasks":     [ /* task items без task_id */ ],
  "risks":     [ /* risk items без risk_id */ ],
  "open_questions": [ /* question items без question_id */ ]
}
```

Поля внутри items соответствуют финальным схемам (5.x), но без обязательного префиксного ID — он назначается на REDUCE.

### 8.2 `_partials/window_<id>.raw.txt`

Raw-ответ LLM до парсинга. Сохраняется для диагностики и для resume-чтения через `extract_json_object_lenient` (`08:511`).

### 8.3 `_partials/window_<id>.error.json` (только 08)

Создаётся `08:367, 444`, если MAP-окно упало. Содержит сообщение об ошибке. На REDUCE такие окна отбрасываются (`08:903 valid_partials`).

### 8.4 `_partials/reduce.{raw.txt,json}`

Аналогично window-партишенам, но для REDUCE-этапа.

### 8.5 `_partials/render.{raw.txt,json}` (только 08)

Render-этап производит JSON `{"memo_md": "...", "protocol_md": "..."}` (`08:505-513`), который потом записывается в memo.md / protocol.md.

### 8.6 `meetings/<id>/transcript/chunks/W<NN>.audio.wav` (только 08)

**Назначение:** аудио одного окна, нарезанное `cut_window_audio` через ffmpeg (`08:234-272`).
**Имя:** `W<NN>.audio.wav`.

### 8.7 `meetings/<id>/transcript/chunks/W<NN>.segments.jsonl` (только 08)

Segments транскрибации одного окна, та же структура что в 6.1 (start/end/text/source).
**Источник:** `08:283-300` (transcribe_window). После всех окон 08 сшивает их в финальный `transcript/segments.jsonl`.

## 9. Слой 7. Подпроект Asu June Bot V2

Все данные пишутся в `data/asu_june_bot/`, **отдельно** от основного `data/`.

### 9.1 `data/asu_june_bot/extracted_v2/documents.jsonl`

**Назначение:** одна запись на исходный файл (`SourceDocument.to_dict()`).
**Формат:** JSONL **append-only** (`scripts/asu_june_bot_extract_text_v2.py:593`).
**Поля** (из `src/asu_june_bot/ingestion/models.py:8-22`):

| Поле | Тип | Описание |
|---|---|---|
| `source_id` | string | Стабильный ID источника. |
| `source_path` | string | Абсолютный путь. |
| `relative_path` | string | Относительный путь от `project_root`. |
| `extension` | string | |
| `sha256` | string | |
| `mtime` | float | |
| `size_bytes` | int | |
| `source_type` | string\|null | Классификация (`enrich_metadata`). |
| `document_type` | string\|null | |
| `stage` | string\|null | |
| `module` | string\|null | |

### 9.2 `data/asu_june_bot/extracted_v2/blocks.jsonl`

**Назначение:** атомарные блоки текста (параграф / ячейка таблицы / страница / слайд).
**Формат:** JSONL **append-only**.
**Поля** (из `ExtractedBlock`, models.py:25-61):

| Поле | Тип | Описание |
|---|---|---|
| `block_id` | string (sha256, 32 символа) | Стабильный ID блока. |
| `source_id` | string | FK к documents.jsonl. |
| `block_index` | int | Позиция блока в документе. |
| `block_type` | string | `paragraph`, `heading`, `page`, `slide`, `sheet`, `table`, `row` и т.п. |
| `text` | string | Содержимое. |
| `source_path`, `relative_path`, `extension`, `sha256`, `mtime` | … | Копия из source. |
| `document_name` | string | Имя файла. |
| `source_type`, `document_type`, `stage`, `module` | string\|null | Классификация. |
| `page`, `slide`, `sheet` | int\|string\|null | Где блок в документе. |
| `paragraph_index`, `heading_level`, `style_name` | int\|string\|null | Для docx. |
| `section`, `sections` | string\|array | Заголовки, в которые входит блок. |
| `table_id`, `table_index`, `row_id`, `row_index`, `col_count` | various | Для таблиц. |
| `headers` | array of string | Заголовки таблицы. |
| `cells` | dict[str, str] | Ячейки одной строки. |
| `title`, `parent_hint` | string\|null | |

**Важно:** `block_id` использует `stable_id(length=32)` из `asu_june_bot.ingestion.utils`. Это **другой namespace**, чем `chunk_id` основного пайплайна (length=24).

### 9.3 `data/asu_june_bot/extracted_v2/errors.jsonl`

Append-only. Поля: `relative_path`, `source_id` (опц.), `error` (repr exception).

### 9.4 `data/asu_june_bot/extracted_v2/extraction_v2_progress.json`

Runtime-progress, обновляется по мере прохода (`:596-606`).

| Поле | Тип |
|---|---|
| `updated_at` | string (UTC ISO) |
| `candidate_sources_total` | int |
| `pending_sources_at_start` | int |
| `processed_this_run` | int |
| `completed_sources_total` | int |
| `last_source` | string |
| `last_source_id` | string |

Читается мониторингом `monitor_asu_june_bot_v2.ps1` для отображения прогресса.

### 9.5 `data/asu_june_bot/extracted_v2/extraction_v2_report.{json,md}`

Итоговая сводка по экстракции. JSON: машиночитаемая статистика (источники по типам, ошибки). MD: тот же отчёт в Markdown. Содержимое не описано в схеме, генерируется `build_report` (asu_june_bot_extract_text_v2.py:614+).

### 9.6 `data/asu_june_bot/chunks_v2.jsonl`

**Назначение:** chunks для подпроекта.
**Формат:** JSONL, **полная перезапись** (`asu_june_bot_build_chunks_v2.py:425` — `jsonl_write`).
**Поля** (из `make_chunk` :200-238):

| Поле | Тип | Описание |
|---|---|---|
| `chunk_id` | string (sha256, 32 символа) | Стабильный ID. |
| `db_id` | string (sha256, 32 символа) | `stable_id(f"{relative_path}:{chunk_id}", length=32)`. |
| `chunker_version` | string | `CHUNKER_VERSION` (V2-метка). |
| `chunk_level` | enum | `parent` (для source-parent чанков), `block` (для блочных). |
| `parent_chunk_id` | string\|null | FK на parent. |
| `block_id` | string\|null | FK к blocks.jsonl. |
| `block_type`, `block_index` | string/int | Из блока. |
| `page`, `slide`, `sheet`, `paragraph_index`, `heading_level`, `style_name` | various | Из блока. |
| `table_id`, `table_title`, `row_id`, `row_header`, `row_index`, `headers`, `cells` | various | Для таблиц. |
| `title` | string\|null | |
| `text` | string | Нормализованный текст chunk. |
| `text_hash` | string | sha256 для дедупликации. |
| `chars` | int | |
| `chunk_index` | int | |
| `created_at` | string (UTC) | |
| `relative_path`, `source_path`, `extension`, `sha256`, `mtime` | various | Копия из блока. |
| `source_url` | string\|null | Пока всегда `null`, под будущие ссылки. |
| `stage`, `module`, `section`, `sections` | various | Классификация. |
| `requirement_id`, `scenario_id` | string\|null | Извлечённые ID по regex. |
| `source_system`, `target_system`, `integration`, `protocol` | string\|null | Извлечённые интеграционные термины. |

**Это значительно более богатые метаданные, чем в основном `data/chunks.jsonl`.** Богатство не используется в продуктовом чате `09_chat.py` — только в `hybrid retriever` подпроекта.

### 9.7 `data/asu_june_bot/chunking_v2_report.{json,md}`

Итоговая сводка chunking-этапа: количества по типам, parent/block split, контроль дублей. Структура задаётся `build_report` (asu_june_bot_build_chunks_v2.py:415).

Читается мониторингом `monitor_asu_june_bot_v2.ps1:27-28`.

### 9.8 `data/asu_june_bot/source_audit_v2_report.json`

**Назначение:** аудит, что попало в индекс и что отфильтровано.
**Продьюсер:** `scripts/asu_june_bot_audit_sources_v2.py:185` (вручную).
**Структура:** не описана в схеме, генерируется `build_report` подпроектного аудита.

## 10. Слой 8. Локи, Маркеры, Логи

### 10.1 `logs/build_index.lock`

**Назначение:** взаимная блокировка против двух одновременных `03_build_index.py`.
**Формат:** plain text.
**Содержимое:** `pid=<int>\nstarted=<YYYY-MM-DD HH:MM:SS>\n` (rag_common.FileLock:172).
**Жизненный цикл:** создаётся при входе в `with FileLock(...)`, удаляется при выходе. При `stale_after_sec=24h` старый lock переустанавливается.
**Читается:** `monitor_rag.ps1` (PID fallback для определения живого build).

### 10.2 `logs/full_rag_<YYYY-MM-DD_HH-mm-ss>.{log,done.txt,failed.txt}`

**Продьюсер:** `run_full_rag.ps1`.
- `.log` — поток stdout/stderr всех шагов (через `Tee-Object`).
- `.done.txt` — маркер успешного завершения (создаётся на финальной итерации).
- `.failed.txt` — маркер failed с сообщением и ссылкой на log.

**Потребители:** `check_rag_status.ps1`, `monitor_rag.ps1`.

### 10.3 `logs/asu_june_bot_{rebuild_v2,chunks_v2}_<stamp>.{log,done.txt,failed.txt}`

Аналогично, для подпроекта. Продьюсеры: `run_asu_june_bot_rebuild_v2.ps1`, `run_asu_june_bot_chunks_v2.ps1`.

### 10.4 `logs/.asu_june_bot_v2_watchdog_state.json` и `logs/asu_june_bot_v2_watchdog.log`

Внутреннее состояние watchdog подпроекта. Структура задаётся `monitor_asu_june_bot_v2.ps1`, в этом артефакте не разворачивалась (PowerShell, runtime).

## 11. Сквозные Паттерны

### 11.1 Идентификаторы

| ID | Длина | Алгоритм | Namespace |
|---|---|---|---|
| `chunk_id` (chunks.jsonl) | 24 hex | `rag_common.stable_id(f"{sha256}:{index}:{chunk[:120]}")` | Основной RAG |
| `db_id` (chunks.jsonl) | 24 hex | `rag_common.stable_id(f"{relative_path}:{sha256}:{index}:{chunk[:120]}")` | Основной RAG (legacy Chroma) |
| `block_id` (blocks.jsonl) | 32 hex | `asu_june_bot.ingestion.utils.stable_id(...)` (length=32) | Подпроект |
| `chunk_id` (chunks_v2.jsonl) | 32 hex | `asu_june_bot.ingestion.utils.stable_id(f"v2:{source_id}:{block_id}:...", length=32)` | Подпроект |
| `db_id` (chunks_v2.jsonl) | 32 hex | `asu_june_bot.ingestion.utils.stable_id(f"{relative_path}:{chunk_id}", length=32)` | Подпроект |
| `source_id` (documents.jsonl) | — | Внутренне в `make_source_document` | Подпроект |
| `decision_id`, `task_id`, `risk_id`, `question_id` | — | Pattern `^(DEC|TASK|RISK|Q)-\d{3}$` | Назначаются на REDUCE |
| `meeting_id` | — | slug `YYYY-MM-DD__short-title` | Глобальный |

### 11.2 Append-Only vs Полная Перезапись

| Файл | Режим | Почему |
|---|---|---|
| `data/manifest.jsonl` | rewrite | Инвентаризация всегда полная. |
| `data/extracted_text/_metadata.jsonl` | rewrite | То же. |
| `data/chunks.jsonl` | rewrite | Корпус собирается заново. |
| `data/embeddings_cache.jsonl` | **append** | Resumability на долгой сборке. |
| `data/numpy_index/*` | atomic rewrite | Через `.tmp` → `shutil.move`. |
| `data/query_log.jsonl` | **append** | Лог обращений. |
| `data/asu_june_bot/extracted_v2/{documents,blocks,errors}.jsonl` | **append** | Resumability экстракции. |
| `data/asu_june_bot/chunks_v2.jsonl` | rewrite | Chunking всегда полный. |
| `meetings/<id>/meeting.json` | atomic rewrite | Через `.tmp` + `os.replace`. |
| `meetings/<id>/transcript/segments.jsonl` | rewrite | Полная транскрибация. |
| `meetings/<id>/artifacts/*.json` | atomic rewrite | Финальные после REDUCE. |
| `_partials/*` | rewrite (но reuse при resume) | Используются как cache. |

### 11.3 source_refs Контракт

Все 4 артефакта встречи (decisions/tasks/risks/open_questions) **обязаны** иметь `source_refs.minItems=1`. Это машинная гарантия трассируемости.

Поле `path` интерпретируется так:
- `kind=transcript_segment` → `path=transcript/segments.jsonl`, плюс `segment_index`/`start`/`end`.
- `kind=rag_source` → `path=<relative_path из RAG chunk>`, плюс `score`.
- `kind=manual_note` → `path=<любой относительный путь>`.

`08_process_meeting_pipeline.py` после REDUCE нормализует source_refs по реальному `transcript/segments.jsonl` (`collect_source_ref_pool` :910).

## 12. Расхождения Схема Vs Код

| Расхождение | Где |
|---|---|
| `processing_status` `classified` и `indexed` — в enum, но **ни один скрипт их не пишет**. Классификатор и индексация артефактов встречи в RAG не реализованы. | `meeting.schema.json:114-125` vs `06/07/08`. |
| `meeting.json::classification` — секция полностью зарезервирована, нет продьюсера. | `meeting.schema.json:164-202`. |
| `meeting.json::links` — секция полностью зарезервирована, нет продьюсера. | `meeting.schema.json:204-226`. |
| `meeting.json::rag.{indexed_artifacts,no_index_artifacts,last_indexed_at}` — нет продьюсера (incremental RAG для встреч не реализован). | `meeting.schema.json:269-286`. |
| `meeting.json::artifacts.classification_report` — нет продьюсера. | `meeting.schema.json:159-161`. |
| `segments.jsonl::source` — schema допускает `MIC`/`SYS`, но `06` пишет всегда `MIX`. | `06:299` vs `meeting.schema.json:audio_tracks`. |
| `audio_tracks=[MIC,SYS]` обязательны для live-сценария по `decisions.md` 2026-05-07, но live-pipeline не реализован. | `decisions.md` vs код. |
| `data/source_links.json` — нет ни одного скрипта, который его создаёт; используется только `09_chat.py` при наличии. | `09:251-267`. |
| `embeddings_cache.jsonl` поле `embedding_model` — единственный валидационный фильтр. Если cache содержит другие модели, они молча пропускаются (без warning). | `03:96`, `rag_numpy_backend.py:54`. |
| `chunks.jsonl::db_id` — рудимент ChromaDB, нигде в коде сейчас не используется кроме записи в `metadata.jsonl` numpy-индекса. | `decisions.md` 2026-05-07 уточнение. |

## 13. Что Не Было Проверено

- **Точное содержимое `chunking_v2_report.json` и `extraction_v2_report.json`** подпроекта (поля внутри `build_report`) — не разворачивал, чтобы артефакт не разрастался. Это можно посмотреть в `asu_june_bot_extract_text_v2.py:614-650` и `asu_june_bot_build_chunks_v2.py:340-415` напрямую.
- **`source_audit_v2_report.json`** — структура определяется `asu_june_bot_audit_sources_v2.py:build_audit_report`, не разворачивал поля.
- **Watchdog state JSON** (`.asu_june_bot_v2_watchdog_state.json`) — PowerShell-runtime, не разворачивал.
- **Формат `transcript.md`** и `pipeline_report.md` — это человеческие документы, не машинный контракт.
- **`docs/examples/meeting.new.example.json`** — должен валидироваться `meeting.schema.json`; не проверял прогоном валидатора. `[?]`
- **Случаи resume в 08** — какие именно поля считаются «валидным partial» (`is_valid_partial` :436) — не разворачивал, осталось на артефакт №2 (data flow).

Все эти точки помечу `[?]` в следующих артефактах при касании.
