# Inputs / Outputs / Side Effects Каждого Скрипта

Артефакт №5 серии полного ревью. Справочник «один скрипт = один блок».

Цель: для каждого исполняемого файла дать полный контракт — какие CLI-флаги, что читает, что пишет, какие сетевые / системные зависимости, какие exit-коды, идемпотентен ли, мутирует ли state. Чтобы понять любой запуск в логах, можно сюда заглянуть и сразу увидеть полный side-effect surface.

## Содержание

1. [Условные обозначения](#1-условные-обозначения)
2. [Глобальные предпосылки](#2-глобальные-предпосылки)
3. [Python: основной RAG-пайплайн (01-05)](#3-python-основной-rag-пайплайн-01-05)
4. [Python: запрос и чат (04, 09)](#4-python-запрос-и-чат-04-09)
5. [Python: обработка встреч (06-08)](#5-python-обработка-встреч-06-08)
6. [Python: подпроект Asu June Bot v2](#6-python-подпроект-asu-june-bot-v2)
7. [Python: helper-модули](#7-python-helper-модули)
8. [PowerShell: обёртки и watchdog'и](#8-powershell-обёртки-и-watchdogи)
9. [Сводка по сетевым endpoint'ам и внешним зависимостям](#9-сводка-по-сетевым-endpointам-и-внешним-зависимостям)
10. [Сводка идемпотентности](#10-сводка-идемпотентности)
11. [Что не было проверено](#11-что-не-было-проверено)

## 1. Условные Обозначения

- **CLI** — позиционные аргументы и флаги. Default из кода в скобках.
- **Reads** — пути / endpoint'ы, которые скрипт читает.
- **Writes** — пути, в которые пишет; маркируется `(rewrite)`, `(append)`, `(atomic)`.
- **Mutates** — какой ключевой state меняется (например, `meeting.json::processing_status`).
- **Network** — внешние HTTP вызовы.
- **Exit codes** — `0` если успех, иначе явные значения. Если не указано — Python default (исключения → exit 1).
- **Idempotent** — `да` / `нет` / `условно` с пояснением.

## 2. Глобальные Предпосылки

Эти инварианты держатся **для всех Python-скриптов**.

| Аспект | Значение |
|---|---|
| Конфиг | `config.yaml` в корне репозитория (читается `rag_common.load_config:21`). Не `config.example.yaml` — пользователь должен скопировать. Hardcoded путь. |
| `work_root` | Из `config.yaml::work_root`, с `os.path.expandvars`. Все относительные `paths.*` резолвятся относительно него. |
| `project_root` | Из `config.yaml::project_root`. Определяет корень исходных файлов. |
| Cwd | Не важен — все пути абсолютные после `resolve_work_path`. |
| Env vars | **Никакие** не читаются напрямую в Python. `os.path.expandvars` применяется только к значениям конфига (`work_root`, `project_root`). |
| Stdout | UTF-8, обычно JSON dump или человеческие строки. |
| Stderr | Только tqdm progress bars и предупреждения сторонних библиотек. |

PowerShell-скрипты дополнительно:
- Устанавливают `PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8`.
- Резолвят путь к `.venv\Scripts\python.exe` относительно скрипта.
- Cwd: `Set-Location $Root` (директория самого `.ps1`).

## 3. Python: Основной RAG-Пайплайн (01-05)

### 3.1 `scripts/01_inventory.py`

**Назначение:** инвентаризация всех файлов в `project_root` с фильтрацией и подсчётом sha256.

| Категория | Значение |
|---|---|
| CLI | Нет аргументов. |
| Reads | `config.yaml`; `project_root_path/**` рекурсивно; читает байты для sha256 только для `status=included`. |
| Writes | `data/manifest.jsonl` (rewrite через `jsonl_write`). |
| Mutates | `data/manifest.jsonl`. |
| Network | Нет. |
| Внешние зависимости | Только stdlib + `rag_common`. |
| Exit codes | `0` норма; исключение → `1`. |
| Idempotent | **Да**: вывод полностью определяется содержимым `project_root` и фильтрами. Повторный запуск даёт битово идентичный результат, если файлы не менялись. |
| Время выполнения | Линейно от числа файлов + I/O sha256. На ~5000 файлов ≈ 30-90 секунд. |

### 3.2 `scripts/02_extract_text.py`

**Назначение:** извлечение текста из docx/pdf/pptx/xlsx/xlsb/html/plain → `data/extracted_text/<rel_id>.<sha[:12]>.txt`.

| Категория | Значение |
|---|---|
| CLI | Нет аргументов. |
| Reads | `config.yaml`; `data/manifest.jsonl`; исходные файлы по `path` (только `status=included`). |
| Writes | `data/extracted_text/<rel_id>.<sha[:12]>.txt` (per file, текст); `data/extracted_text/_metadata.jsonl` (rewrite). |
| Mutates | `data/extracted_text/`. |
| Network | Нет. |
| Внешние зависимости | `python-docx`, `pymupdf` (fitz), `python-pptx`, `pandas`, `pyxlsb`, `openpyxl`, `beautifulsoup4`, `lxml`. |
| Exit codes | `0` норма; индивидуальные ошибки извлечения записываются в `_metadata.jsonl::error` и **не валят запуск**. |
| Idempotent | **Условно**: имя файла включает `sha256[:12]`, поэтому старые версии остаются на диске при изменении источника (рудиментарные файлы не чистятся). `_metadata.jsonl` всегда отражает только последний прогон. |
| Время выполнения | Минуты на полный корпус; bottleneck — PDF (fitz). |

### 3.3 `scripts/03_build_index.py`

**Назначение:** chunking текстов + embedding через Ollama с дописыванием в cache.

| Категория | Значение |
|---|---|
| CLI | Нет аргументов. |
| Reads | `config.yaml`; `data/extracted_text/_metadata.jsonl`; все `data/extracted_text/*.txt` (для `meta.error is None`); существующий `data/embeddings_cache.jsonl` (для skip). |
| Writes | `data/chunks.jsonl` (rewrite); `data/embeddings_cache.jsonl` (**append**, по одной записи на chunk); `logs/build_index.lock` (FileLock на время работы). |
| Mutates | `data/chunks.jsonl`, `data/embeddings_cache.jsonl`. |
| Network | **HTTP POST** `{ollama.base_url}/api/embeddings` на каждый новый chunk. До 15 retry с backoff (max 180s). |
| Внешние зависимости | `requests`, `tqdm`, Ollama runtime с моделью `bge-m3` (из `config.yaml::ollama.embedding_model`). |
| Exit codes | `0` норма; `RuntimeError` после 15 неудачных retry → `1`. |
| Idempotent | **Да на уровне embedding cache**: уже посчитанные `chunk_id` пропускаются. Stale записи в cache остаются (по `decisions.md` 2026-05-06). `chunks.jsonl` всегда перезаписывается заново. |
| Concurrency | **Защищён `FileLock`** (`logs/build_index.lock`, stale_after=24h). Второй запуск откажется. |
| Время | Часы на полный корпус (~5000+ chunks × ≥1s embedding на Ollama). |

### 3.4 `scripts/05_build_numpy_index.py`

**Назначение:** сборка локального numpy-индекса из `chunks.jsonl` + `embeddings_cache.jsonl`.

| Категория | Значение |
|---|---|
| CLI | Нет аргументов. |
| Reads | `config.yaml`; `data/chunks.jsonl`; `data/embeddings_cache.jsonl` (только записи с подходящей `embedding_model`). |
| Writes | `data/numpy_index/.tmp/{embeddings.npy, metadata.jsonl, manifest.json}` → атомарно перемещается в `data/numpy_index/`. |
| Mutates | `data/numpy_index/`. |
| Network | Нет. |
| Внешние зависимости | `numpy`. |
| Exit codes | `0` норма; `RuntimeError` если в cache нет ни одного валидного embedding для текущих chunks. |
| Idempotent | **Да**: вывод определяется состоянием входных файлов. Атомарная замена `.tmp → final` гарантирует, что неполный индекс не виден потребителям. |
| Время | Секунды-минуты (только linalg для L2-нормализации). |

## 4. Python: Запрос И Чат (04, 09)

### 4.1 `scripts/04_query.py`

**Назначение:** прямой запрос к RAG-индексу. Не для прода, для отладки.

| Категория | Значение |
|---|---|
| CLI (позиц.) | `question` (nargs="+"): сам вопрос. |
| `--top-k` | int, default из `config.yaml::rag.query_top_k`. |
| `--raw` | bool, JSON-вывод найденных chunks без LLM. |
| `--compact` | bool, компактный список источников. |
| `--include-excluded` | bool, отключить query-фильтр служебных путей. |
| `--no-dedupe` | bool, не дедуплицировать chunks по тексту. |
| Reads | `config.yaml`; `data/numpy_index/*` (через `NumpyRagIndex.load`); fallback `data/chunks.jsonl` + `data/embeddings_cache.jsonl`. |
| Writes | `data/query_log.jsonl` (append). |
| Mutates | Только query_log. |
| Network | **HTTP POST** `/api/embeddings` (для embed запроса); если режим не `raw`/`compact`/`sources-only`, ещё `/api/generate` (LLM). |
| Exit codes | `0` норма. |
| Idempotent | **Нет** (append в query_log + side-effect ответа в stdout). Семантически: тот же вопрос даст ту же выборку chunks, но LLM-ответ не воспроизводим (`temperature > 0`). |
| Заметка | Sensitive-фильтр `rag_common.is_sensitive_query` блокирует логирование запросов с подстроками `.env`, `пароль`, `token`, `system prompt` и т.д. |

### 4.2 `scripts/09_chat.py`

**Назначение:** «product chat» — project-only retrieval-augmented Q&A с document expansion, фильтрами и refusal-логикой.

| CLI | Default | Назначение |
|---|---|---|
| `question` (pos, nargs="+") | — | Вопрос. |
| `--top-k` | 12 | Сколько chunks искать до фильтрации. |
| `--score-threshold` | 0.35 | Минимальный score источника. |
| `--min-sources` | 1 | Минимум источников выше порога. |
| `--max-context-chars` | 14000 | Лимит prompt context. |
| `--source-char-limit` | 1800 | Максимум на один источник в prompt. |
| `--document-expansion-chunks` | 6 | Сколько chunks брать из top-документа для расширения. |
| `--expand-top-documents` | 2 | Сколько top-документов расширять. |
| `--no-document-expansion` | False | Отключить расширение. |
| `--model` | None (из config) | Ollama chat model. |
| `--prompt` | `configs/prompts/chat.md` | Путь к prompt-шаблону. |
| `--temperature` | None (из config) | |
| `--top-p` | None | |
| `--num-predict` | 1024 | Лимит длины ответа Ollama. |
| `--timeout-sec` | 240 | HTTP timeout. |
| `--json` | False | JSON-вывод. |
| `--sources-only` | False | Не вызывать LLM, только источники. |
| `--include-excluded` | False | Без query-фильтра путей. |
| `--no-dedupe` | False | Без дедупа. |
| `--think` | False | Разрешить thinking-режим Ollama. |
| `--no-extractive-fallback` | False | Не возвращать extractive-ответ при LLM-сбое. |

| Категория | Значение |
|---|---|
| Reads | `config.yaml`; `data/numpy_index/*`; `data/chunks.jsonl` (для document expansion в `load_document_chunks`); `data/source_links.json` (если есть); `configs/prompts/chat.md` или `--prompt`. |
| Writes | `data/query_log.jsonl` (append). |
| Network | `/api/embeddings` + `/api/generate` (если LLM включён). |
| Exit codes | `0` норма. |
| Idempotent | Нет (append + non-deterministic LLM). |
| Заметка | Дополнительный sensitive-фильтр `SENSITIVE_PATTERNS` в самом 09 шире, чем общий `is_sensitive_query`: блокирует «инструкции модели», «developer message», «пароли», «.env» — такие запросы отказываются ДО логирования. |

## 5. Python: Обработка Встреч (06-08)

### 5.1 `scripts/06_transcribe_meeting.py`

**Назначение:** ASR одной встречи через faster-whisper. Сохраняет `transcript/segments.jsonl` и `transcript.md`.

| CLI | Required | Default | Назначение |
|---|---|---|---|
| `--meeting-dir` | yes | — | Путь к папке встречи. |
| `--model` | no | `small` | Имя faster-whisper модели. |
| `--compute-type` | no | `int8` | CTranslate2 compute type. |
| `--language` | no | `ru` | Язык транскрипции. |
| `--dry-run` | no | False | Валидация inputs + загрузка модели, без транскрипции. |
| `--force` | no | False | Перетранскрибировать, даже если статус `transcribed`. |

| Категория | Значение |
|---|---|
| Reads | `meeting.json` (валидируется по `configs/schemas/meeting.schema.json`); медиа из `source.media_files[]` или derived; `meetings/<id>/glossary.md` (initial prompt) если есть. |
| Writes (атомарно) | `meeting.json` (3 раза: при входе → `transcribing`, при успехе → `transcribed`, при ошибке → `failed` + `last_error`); `transcript/transcript.md`; `transcript/segments.jsonl`. |
| Mutates | `meeting.json::processing_status`, `meeting.json::artifacts.{transcript,segments}`, `meeting.json::updated_at`. |
| Network | Нет (faster-whisper — локальная модель). |
| Внешние зависимости | `faster-whisper`, `ffmpeg` (через `ensure_ffmpeg`). |
| Exit codes | `0` норма; `1` при ошибке (с записью `last_error` в `meeting.json`). |
| Idempotent | **Условно**: повторный запуск без `--force` отказывается, если `processing_status=transcribed`. С `--force` транскрибирует заново (модель детерминирована при том же `beam_size`, но faster-whisper не гарантирует битовое равенство). |
| Pre-check | Schema-валидация meeting.json **до** мутации. Если `processing_status` не in `{new, transcribed (с --force), failed}` — отказ. |

### 5.2 `scripts/07_generate_meeting_artifacts.py`

**Назначение:** генерация артефактов встречи (decisions/tasks/risks/open_questions + memo/protocol). Три режима: `extractive`, `ollama`, `ollama-map-reduce`.

| CLI | Required | Default | Назначение |
|---|---|---|---|
| `--meeting-dir` | yes | — | Путь к папке встречи. |
| `--model` | no | None → config | Ollama chat model. |
| `--base-url` | no | None → config | Ollama base URL. |
| `--num-ctx` | no | None → config | Ollama context window. |
| `--temperature` | no | None → config | |
| `--top-p` | no | None → config | |
| `--timeout-sec` | no | 900 | HTTP timeout. |
| `--max-transcript-chars` | no | 12000 | Лимит compact transcript для LLM. |
| `--mode` | no | `extractive` | `extractive` (без LLM), `ollama` (one-pass), `ollama-map-reduce` (windowed). |
| `--window-seconds` | no | 360 | Размер окна (только для map-reduce). |
| `--window-overlap-seconds` | no | 30 | Overlap окна. |
| `--dry-run` | no | False | Валидация + загрузка prompts, без вызова LLM. |
| `--force` | no | False | Перегенерировать при статусе `summarized` или `failed`. |

| Категория | Значение |
|---|---|
| Reads | `meeting.json` (валидация); `transcript/segments.jsonl`; `configs/prompts/meeting_*.md` (несколько prompts в зависимости от mode); `configs/schemas/meeting.{decisions,tasks,risks,open_questions}.schema.json`. |
| Writes (атомарно) | `meeting.json` (статус → `failed`/`summarized`); `artifacts/{decisions,tasks,risks,open_questions}.json`; `artifacts/{memo,protocol}.md`. **Если mode=map-reduce**: `artifacts/_partials/window_<id>.{raw.txt,json}` + `artifacts/_partials/reduce.{raw.txt,json}`. |
| Mutates | `meeting.json::processing_status`, `meeting.json::artifacts.*`, `_partials/`. |
| Network | `/api/generate` (Ollama) — N+1 вызов в map-reduce (N окон + 1 reduce); 3 вызова в ollama mode (memo+protocol+artifacts_json); 0 в extractive. |
| Exit codes | `0` норма; `1` при schema-валидации или ошибке. |
| Idempotent | **Условно**: с `--force` всегда перегенерирует. Без `--force` отказывается, если `processing_status=summarized`. **Не использует `_partials` как resume cache** — всегда удаляет директорию в начале (`07:825 shutil.rmtree`). |
| Pre-check | Требует `processing_status=transcribed` (или `summarized`/`failed` + `--force`). |

### 5.3 `scripts/08_process_meeting_pipeline.py`

**Назначение:** windowed end-to-end pipeline: ASR per window → MAP per window → REDUCE → RENDER. Альтернатива связке 06+07.

| CLI | Required | Default | Назначение |
|---|---|---|---|
| `--meeting-dir` | yes | — | Путь к папке встречи. |
| `--asr-model` | no | `small` | faster-whisper модель. |
| `--llm-model` | no | None → config | Ollama chat model. |
| `--window-seconds` | no | 120 | Размер окна. |
| `--window-overlap-seconds` | no | 15 | Overlap. |
| `--num-ctx` | no | 8192 | Ollama context. |
| `--temperature` | no | 0.1 | |
| `--top-p` | no | 0.8 | |
| `--timeout-sec` | no | 900 | |
| `--max-asr-workers` | no | 1 | Параллелизм ASR (faster-whisper не thread-safe — лучше 1). |
| `--max-llm-workers` | no | 1 | Параллелизм LLM-вызовов (Ollama keep-alive). |
| `--force` | no | False | Не пропускать существующие partials. |
| `--dry-run` | no | False | |
| `--max-windows` | no | None | Калибровка: первые N окон. |
| `--asr-compute-type` | no | `int8` | |
| `--asr-language` | no | `ru` | |
| `--base-url` | no | None → config | Ollama base URL. |

| Категория | Значение |
|---|---|
| Reads | `meeting.json`; медиа; `transcript/chunks/W<NN>.{audio.wav,segments.jsonl}` если есть (resume cache); `_partials/{window_*.json,reduce.json,render.json}` (resume cache); все prompts (`meeting_map_extract.md`, `meeting_reduce_artifacts.md`, `meeting_render_memo_protocol.md`). |
| Writes (атомарно) | `meeting.json` (статусы `processing`/`summarized`/`failed`); `transcript/chunks/W<NN>.audio.wav`; `transcript/chunks/W<NN>.segments.jsonl`; `transcript/segments.jsonl` (склейка); `transcript/transcript.md`; `artifacts/_partials/window_<id>.{raw.txt,json}` или `.error.json`; `artifacts/_partials/reduce.{raw.txt,json}`; `artifacts/_partials/render.{raw.txt,json}`; финальные `artifacts/{decisions,tasks,risks,open_questions}.json`; `artifacts/{memo,protocol,pipeline_report}.md`. |
| Mutates | `meeting.json` + всё внутри `meetings/<id>/`. |
| Network | `/api/generate` × N окон + 1 reduce + 1 render. ASR не сетевая. |
| Exit codes | `0` норма; `1` при критической ошибке (с записью `last_error`). Отдельные MAP-окна с ошибкой не валят запуск — записываются как `_partials/window_<id>.error.json` и пропускаются на REDUCE. |
| Idempotent | **Да на уровне resume**: без `--force` пропускает окна, у которых уже есть валидный `_partials/window_<id>.json` или `transcript/chunks/W<NN>.audio.wav`. С `--force` пересчитывает заново. |
| Pre-check | Schema-валидация meeting.json; статус **должен быть `new`, `transcribed`, `summarized` (с `--force`), или `failed`**. `transcribing`/`processing` блокирует (lock-семантика). |
| Threading | Используется `ThreadPoolExecutor` для ASR-окон (`--max-asr-workers`) и LLM-окон (`--max-llm-workers`). |

## 6. Python: Подпроект Asu June Bot V2

### 6.1 `scripts/asu_june_bot_extract_text_v2.py`

**Назначение:** независимый extractor подпроекта — превращает source-файлы в blocks (paragraph, table, row, page, slide, sheet, heading) с богатой метадатой.

| CLI | Default | Назначение |
|---|---|---|
| `--dry-run` | False | Не писать output. |
| `--limit` | 0 (без лимита) | Ограничить число source-файлов. |
| `--path-contains` | None | Фильтр по подстроке `relative_path`. |
| `--output-dir` | `data/asu_june_bot/extracted_v2` | |
| `--reset` | False | Удалить `output_dir` и начать с нуля. |
| `--no-resume` | False | Игнорировать уже извлечённые `source_id`. |

| Категория | Значение |
|---|---|
| Reads | `config.yaml`; иерархия `project_root` (через `iter_source_files`); существующий `output_dir/documents.jsonl` (для resume). |
| Writes | `output_dir/documents.jsonl` (**append**); `output_dir/blocks.jsonl` (**append**); `output_dir/errors.jsonl` (**append**); `output_dir/extraction_v2_progress.json` (rewrite на каждом файле); `output_dir/extraction_v2_report.{json,md}` (rewrite в конце). |
| Mutates | `data/asu_june_bot/extracted_v2/`. |
| Network | Нет. |
| Внешние зависимости | Те же, что 02: `python-docx`, `pymupdf`, `python-pptx`, `pandas`, `pyxlsb`, `openpyxl`, `bs4`, `lxml`. |
| Exit codes | `0` норма; ошибки per file записываются и не валят прогон. |
| Idempotent | **Да**: по `source_id`. С `--reset` — сначала удаляет директорию. С `--no-resume` — переиздаёт всё, но не очищает старые записи (просто дублирует). |
| Время | Десятки минут на полный корпус. |

### 6.2 `scripts/asu_june_bot_build_chunks_v2.py`

**Назначение:** chunking из v2-blocks: parent-chunks по source-документу + block-chunks с rich metadata.

| CLI | Default | Назначение |
|---|---|---|
| `--dry-run` | False | |
| `--limit` | 0 | Ограничить number of source documents. |
| `--path-contains` | None | Фильтр. |
| `--blocks-path` | `data/asu_june_bot/extracted_v2/blocks.jsonl` | Input. |
| `--output-dir` | `data/asu_june_bot` | Output. |

| Категория | Значение |
|---|---|
| Reads | `config.yaml`; `data/asu_june_bot/extracted_v2/blocks.jsonl`. |
| Writes | `data/asu_june_bot/chunks_v2.jsonl` (**rewrite**); `data/asu_june_bot/chunking_v2_report.{json,md}` (rewrite). |
| Mutates | `data/asu_june_bot/chunks_v2.jsonl`. |
| Network | Нет. |
| Exit codes | `0` норма. |
| Idempotent | **Да**: вывод — функция от blocks.jsonl. |
| Заметка | Embedding'и для v2 не считаются этим скриптом — отдельный hybrid retriever строится в памяти в `asu_june_bot_search.py`. |

### 6.3 `scripts/asu_june_bot_audit_sources_v2.py`

**Назначение:** аудит покрытия source-файлов — что попадает в v2 pipeline, что отфильтровано.

| CLI | Default | Назначение |
|---|---|---|
| `--output-dir` | (default из кода) | Куда писать отчёт. |
| `--json` | False | Печатать полный JSON в stdout. |

| Категория | Значение |
|---|---|
| Reads | `config.yaml`; иерархия `project_root`. |
| Writes | `data/asu_june_bot/source_audit_v2_report.json`. |
| Network | Нет. |
| Exit codes | `0`. |
| Idempotent | Да. |

### 6.4 `scripts/asu_june_bot_search.py`

**Назначение:** CLI для тестирования hybrid retrieval подпроекта (BM25 + vector).

| CLI | Default | Назначение |
|---|---|---|
| `query` (pos, nargs="+") | — | Запрос. |
| `--top-k` | 10 | |
| `--mode` | `hybrid` | `hybrid`, `vector`, `bm25`. |
| `--include-source-type` | (множественный) | Whitelist source_type. |
| `--json` | False | JSON-вывод. |

| Категория | Значение |
|---|---|
| Reads | `config.yaml`; `data/asu_june_bot/chunks_v2.jsonl`. |
| Writes | **Ничего**. Только stdout. |
| Network | `/api/embeddings` если `mode in {hybrid, vector}` (для embed запроса). |
| Exit codes | `0`; `SystemExit("Пустой запрос")` если query пустой. |
| Idempotent | Чистое чтение. |
| Заметка | **НЕ пишет в query_log.jsonl** — отдельный pipeline без feedback-loop. |

## 7. Python: Helper-Модули

### 7.1 `scripts/rag_common.py`

**Импортируется** скриптами 01-05, 09. Не имеет `__main__`.

Экспортирует:
- `load_config`, `resolve_work_path`, `ensure_runtime_dirs`
- `jsonl_read`, `jsonl_write`
- `sha256_file`, `stable_id`, `normalize_text`, `chunk_text`, `read_text_guess`, `safe_rel_id`
- `path_rel_to_project`, `is_excluded_by_path_patterns`, `is_under_excluded_dir`
- `FileLock` (контекстный менеджер; `stale_after_sec=86400`)
- `print_summary`
- `is_sensitive_query`, `append_query_log` (sensitive-фильтр + append-only лог)

### 7.2 `scripts/rag_numpy_backend.py`

**Импортируется** 05_build_numpy_index и 04_query (для load) и 09_chat (для load). Не имеет `__main__`.

Экспортирует:
- `build_index(chunks_path, embeddings_cache_path, index_dir, embedding_model)` — атомарная сборка `data/numpy_index/*`.
- `NumpyRagIndex.load(index_dir)` / `.query(embedding, top_k)` — runtime поисковый объект.
- `INDEX_VERSION = 1`.

## 8. PowerShell: Обёртки И Watchdog'и

### 8.1 `run_full_rag.ps1`

**Назначение:** последовательный запуск 01 → 02 → 03 → 05.

| Категория | Значение |
|---|---|
| Параметры | Нет CLI-параметров. |
| Reads | Существование `.venv\Scripts\python.exe`. |
| Writes | `logs/full_rag_<stamp>.log` (tee всех шагов); `logs/full_rag_<stamp>.done.txt` ИЛИ `logs/full_rag_<stamp>.failed.txt`. |
| Mutates | Всё, что мутируют 01/02/03/05 + log-маркеры. |
| Exit | `0` если все шаги прошли; `1` если любой `$LASTEXITCODE -ne 0` (выбрасывает throw). |
| Idempotent | Условно: 01/02/05 — да; 03 — да на уровне embedding cache; конкатенация может перевыполнять работу. |
| Concurrency | Нет внутренней защиты от параллельного запуска; `03_build_index.py` сам берёт `FileLock`. |

### 8.2 `run_asu_june_bot_rebuild_v2.ps1`

**Назначение:** последовательный запуск `asu_june_bot_extract_text_v2.py` → `asu_june_bot_build_chunks_v2.py`.

| Категория | Значение |
|---|---|
| Параметры | Нет. |
| Writes | `logs/asu_june_bot_rebuild_v2_<stamp>.{log,done.txt,failed.txt}`. |
| Mutates | `data/asu_june_bot/`. |
| Exit | Аналогично 8.1. |

### 8.3 `run_asu_june_bot_chunks_v2.ps1`

**Назначение:** только chunking (без extract). Предполагает, что `blocks.jsonl` уже существует.

| Категория | Значение |
|---|---|
| Параметры | Нет. |
| Pre-check | `Test-Path` для blocks.jsonl → ошибка при отсутствии. |
| Writes | `logs/asu_june_bot_chunks_v2_<stamp>.{log,done.txt,failed.txt}`. |
| Mutates | `data/asu_june_bot/chunks_v2.jsonl`, отчёты. |

### 8.4 `check_rag_status.ps1`

**Назначение:** показать последний `done`/`failed` маркер RAG-сборки + живые процессы python/ollama + tail последнего лога.

| Категория | Значение |
|---|---|
| Параметры | Нет. |
| Reads | `logs/full_rag_*.{log,done.txt,failed.txt}`; `Get-Process powershell,python,ollama`. |
| Writes | Только stdout. |
| Mutates | Ничего. |
| Exit | `0`. |

### 8.5 `monitor_rag.ps1`

**Назначение:** single-tick watchdog. Раз в N минут (через Task Scheduler) проверяет, идёт ли сборка, не зависла ли.

| Параметр | Default | Назначение |
|---|---|---|
| `-Root` | `$env:USERPROFILE\Desktop\AI\MeetingAgent` | Корень репо. |
| `-EmbeddingModel` | `bge-m3` | Для health-check. |
| `-OllamaUrl` | `http://localhost:11434` | |
| `-EmbeddingNumCtx` | 8192 | |
| `-KeepAlive` | `24h` | |
| `-StallMinutes` | 10 | Считать сборку зависшей, если `embeddings_cache.jsonl` не рос N минут. |

| Категория | Значение |
|---|---|
| Reads | `logs/build_index.lock` (PID); `data/embeddings_cache.jsonl`, `data/chunks.jsonl` (mtime/size); `Get-Process`. |
| Writes | `logs/watchdog.log` (append); `logs/.watchdog_state.json` (mutating state). |
| Network | Возможно health-check на `/api/embeddings`. |
| Mutates | Возможно `taskkill` + re-launch `run_full_rag.ps1` при stall. См. `monitor_rag.ps1` полностью для деталей. `[?]` |
| Exit | `0`. |

### 8.6 `monitor_asu_june_bot_v2.ps1`

**Назначение:** аналог 8.5 для подпроекта.

| Параметр | Default |
|---|---|
| `-Root` | `$env:USERPROFILE\Desktop\AI\MeetingAgent` |
| `-StallMinutes` | 30 |
| `-NoAutoStart` | switch |

| Категория | Значение |
|---|---|
| Reads | `logs/.asu_june_bot_v2_watchdog_state.json`; `data/asu_june_bot/extracted_v2/{documents.jsonl, blocks.jsonl, extraction_v2_progress.json}`; `data/asu_june_bot/chunks_v2.jsonl`; `data/asu_june_bot/chunking_v2_report.json`. |
| Writes | `logs/asu_june_bot_v2_watchdog.log`; `logs/.asu_june_bot_v2_watchdog_state.json`. |
| Mutates | Может стартовать `run_asu_june_bot_rebuild_v2.ps1`, если `-NoAutoStart` не задан. |
| Exit | `0`. |

### 8.7 `register_asu_june_bot_v2_watchdog.ps1`

**Назначение:** одноразовая регистрация задачи Windows Task Scheduler для `monitor_asu_june_bot_v2.ps1`.

| Параметр | Default |
|---|---|
| `-Root` | `$env:USERPROFILE\Desktop\AI\MeetingAgent` |
| `-TaskName` | `AsuJuneBotV2Watchdog` |
| `-IntervalMinutes` | 15 |

| Категория | Значение |
|---|---|
| Reads | Существование `monitor_asu_june_bot_v2.ps1`. |
| Writes | **Системная мутация**: создаёт scheduled task через `New-ScheduledTaskAction` / `Register-ScheduledTask`. Сначала пытается удалить старую (`Unregister-ScheduledTask`). |
| Mutates | Windows Task Scheduler. |
| Network | Нет. |
| Exit | `Stop` при `ErrorActionPreference`; иначе `0`. |

## 9. Сводка По Сетевым Endpoint'ам И Внешним Зависимостям

| Скрипт | `/api/embeddings` | `/api/generate` | ffmpeg | faster-whisper | Внешние py-deps |
|---|---|---|---|---|---|
| 01_inventory | — | — | — | — | stdlib |
| 02_extract_text | — | — | — | — | docx, pymupdf, pptx, pandas, openpyxl, pyxlsb, bs4, lxml |
| 03_build_index | **да** (per chunk, до 15 retry) | — | — | — | requests, tqdm |
| 04_query | да (per query) | да (при llm mode) | — | — | requests |
| 05_build_numpy_index | — | — | — | — | numpy |
| 06_transcribe_meeting | — | — | **да** | **да** | faster-whisper |
| 07_generate_meeting_artifacts | — | да (N или N+1 окон в mode) | — | — | requests, jsonschema |
| 08_process_meeting_pipeline | — | да (N+1+1 на окно/reduce/render) | **да** | **да** | requests, faster-whisper, jsonschema |
| 09_chat | да | да | — | — | requests |
| asu_june_bot_extract_text_v2 | — | — | — | — | (как 02) |
| asu_june_bot_build_chunks_v2 | — | — | — | — | stdlib |
| asu_june_bot_audit_sources_v2 | — | — | — | — | stdlib |
| asu_june_bot_search | да (vector/hybrid) | — | — | — | requests, rank_bm25 |

**Единственный внешний сервис — Ollama** на `http://localhost:11434` (из конфига `ollama.base_url`). Никаких облачных API.

## 10. Сводка Идемпотентности

| Скрипт | Idempotent | Mode |
|---|---|---|
| 01_inventory | да | full rewrite, детерминирован от inputs |
| 02_extract_text | условно | новые файлы; старые с прежним sha остаются |
| 03_build_index | да (на уровне embedding cache) | cache append + chunks rewrite |
| 04_query | нет (append query_log + non-det LLM) | side-effects |
| 05_build_numpy_index | да | atomic rewrite |
| 06_transcribe_meeting | условно (требует `--force` если уже transcribed) | mutates meeting.json |
| 07_generate_meeting_artifacts | условно (требует `--force` если уже summarized); `_partials` НЕ переиспользуются | mutates meeting.json + artifacts/ |
| 08_process_meeting_pipeline | условно (resume через partials без `--force`) | mutates meeting.json + transcript/ + artifacts/ |
| 09_chat | нет (см. 04) | side-effects |
| asu_june_bot_extract_text_v2 | да (resume по source_id) | append на disk |
| asu_june_bot_build_chunks_v2 | да | full rewrite |
| asu_june_bot_audit_sources_v2 | да | rewrite report |
| asu_june_bot_search | да | read-only |
| run_full_rag.ps1 | условно (обёртка) | log markers |
| run_asu_june_bot_rebuild_v2.ps1 | да | log markers |
| check_rag_status.ps1 | да | read-only |
| monitor_rag.ps1 | условно | mutates state + может restart |
| monitor_asu_june_bot_v2.ps1 | условно | mutates state + может restart |
| register_asu_june_bot_v2_watchdog.ps1 | условно (re-register) | системная мутация |

## 11. Что Не Было Проверено

- **`monitor_rag.ps1` полное поведение auto-restart** — что именно делает при stall (kill + relaunch?), не разворачивал полностью. `[?]`
- **`monitor_asu_june_bot_v2.ps1` watchdog state schema** — структура `.asu_june_bot_v2_watchdog_state.json` не разворачивалась. `[?]`
- **Точное поведение faster-whisper при разных `--compute-type`** (`int8`/`float16`/`float32`) — на детерминированность не проверял. `[?]`
- **Конкретные default'ы для `--top-k`, `--temperature` в `09_chat`/`04_query`** — некоторые ссылаются на `config.yaml`, точные значения зависят от пользовательского конфига. Здесь указаны default'ы из кода. `[?]`
- **`07_generate_meeting_artifacts` extractive mode полностью** — не разворачивал, какие именно секции он заполняет без LLM. `[?]`
