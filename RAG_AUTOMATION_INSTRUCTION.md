# Инструкция: локальный RAG-индекс проекта АСУ

## Цель

Создать локальную автоматизацию, которая анализирует папку проекта, строит RAG-индекс и позволяет агенту отвечать по проектным документам без загрузки всех файлов в контекст чата.

Проектная папка:

```text
%PROJECT_ROOT%
```

Главное правило: не отправлять все документы в чат и не просить LLM прочитать папку целиком. LLM должна получать только релевантные фрагменты, найденные локальным поиском.

## Текущий статус установки

На 2026-04-30 проверено в локальном окружении:

- рабочая папка создана: `%USERPROFILE%\Desktop\AI\MeetingAgent`;
- виртуальное окружение создано: `.venv`;
- Python-импорты проверены: `faster_whisper`, `watchdog`, `requests`, `yaml`, `docx`, `fitz`, `pptx`, `openpyxl`, `chromadb`, `bs4`, `lxml`, `pandas`, `easyocr`, `cv2`, `PIL`;
- дополнительно установлен `pyxlsb` для чтения `.xlsb`;
- Ollama-модели скачаны:
  - `qwen3:8b`;
  - `bge-m3:latest`;
- создан настоящий файл конфигурации: `config.yaml`;
- создана структура папок:
  - `scripts`;
  - `data`;
  - `data\extracted_text`;
  - `vector_db`;
  - `logs`;
  - `watched_folder`;
  - `templates`.
- написаны скрипты:
  - `scripts\rag_common.py`;
  - `scripts\01_inventory.py`;
  - `scripts\02_extract_text.py`;
  - `scripts\03_build_index.py`;
  - `scripts\04_query.py`.
- `01_inventory.py` успешно выполнен:
  - файлов в manifest: `1965`;
  - included: `1025`;
  - excluded: `898`;
  - unsupported: `42`;
  - errors: `0`.
- `02_extract_text.py` успешно выполнен:
  - extracted: `1016`;
  - errors: `3`;
  - оставшиеся ошибки: три `.xlsx` с некорректным/нестандартным stylesheet.
- Предварительное чанкование: около `13267` chunks, `26447727` символов текста.
- Проверен одиночный embedding-запрос к Ollama `bge-m3`: HTTP `200`, размерность embedding `1024`.
- `03_build_index.py` обновлен:
  - добавлен resumable cache embeddings: `data\embeddings_cache.jsonl`;
  - при повторном запуске уже посчитанные `chunk_id` пропускаются;
  - ChromaDB строится из готового cache;
  - retry Ollama embedding увеличен до `15` попыток.
  - embedding-запросы в Ollama теперь передают `options.num_ctx=8192` и `keep_alive=24h`;
  - размер chunk уменьшен до `3000` символов с overlap `300`, чтобы реальные JSON/HTML/кодовые фрагменты не превышали контекст bge-m3.
  - `monitor_rag.ps1` тоже проверяет Ollama с `num_ctx=8192` и `keep_alive=24h`;
  - watchdog работает как single-tick монитор для запуска каждые 15 минут: если build живой, второй build не запускается; если cache не растет 10+ минут, перезапускается только Ollama, Python build не убивается;
  - PowerShell watchdog больше не содержит буквальный путь с кириллицей, а собирает корень проекта через `$env:USERPROFILE`;
  - stale failed markers переносятся в `logs\archive`, чтобы они не мешали определению актуального статуса.

Следующий шаг: выполнить `03_build_index.py`. Первый прогон будет долгим, но повторные запуски продолжат расчет embeddings по cache.

## Долгий запуск на выходные

Создан runner:

```text
run_full_rag.ps1
```

Он выполняет:

```powershell
.\.venv\Scripts\python.exe scripts\01_inventory.py
.\.venv\Scripts\python.exe scripts\02_extract_text.py
.\.venv\Scripts\python.exe scripts\03_build_index.py
```

Логи пишутся в:

```text
logs\full_rag_*.log
```

При успешном завершении создается:

```text
logs\full_rag_*.done.txt
```

При ошибке создается:

```text
logs\full_rag_*.failed.txt
```

Проверка статуса:

```powershell
.\check_rag_status.ps1
```

На 2026-04-30 фоновый запуск стартовал и дошел до стадии `03_build_index`.

## Архитектура

```text
project folder
  -> inventory
  -> text extraction
  -> chunking
  -> embeddings
  -> vector db
  -> retrieval
  -> LLM answer with citations
```

Рекомендуемая рабочая папка:

```text
%USERPROFILE%\Desktop\AI\MeetingAgent
  config.yaml
  RAG_AUTOMATION_INSTRUCTION.md
  scripts\
    01_inventory.py
    02_extract_text.py
    03_build_index.py
    04_query.py
    05_watch_project.py
  data\
    manifest.jsonl
    extracted_text\
    chunks.jsonl
    rag_state.json
  vector_db\
  logs\
```

## Что индексировать

Индексировать в первую очередь:

- `.docx`
- `.pdf`
- `.xlsx`
- `.xlsb`
- `.pptx`
- `.md`
- `.txt`
- `.html`
- `.json`
- `.yml`
- `.drawio`
- `.puml`
- `.srt`
- исходные `.py`, `.js`, `.ts`, `.css`, если они относятся к проектной логике

Не индексировать напрямую:

- `.mp4` без предварительной транскрибации
- `.zip`, `.rar` без отдельной распаковки в карантинную папку
- `.pyc`
- шрифты `.ttf`
- временные, backup и cache-файлы
- большие машинные HTML/JS-бандлы, если они являются сборкой, а не документацией

Папки `_backup` и похожие служебные папки индексировать только после отдельного решения, иначе они дадут много дублей.

## Модели

Для embeddings:

```powershell
ollama pull bge-m3
```

Для анализа и ответов:

```powershell
ollama pull qwen3:8b
```

Если qwen3:8b работает медленно:

```powershell
ollama pull qwen3:4b
```

Для транскрибации встреч:

- `faster-whisper`
- модель: `large-v3-turbo` или `turbo`
- CPU режим: `int8`

## Python-пакеты

Установить в отдельное виртуальное окружение MeetingAgent:

```powershell
cd "$env:USERPROFILE\Desktop\AI\MeetingAgent"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install faster-whisper watchdog requests pyyaml python-docx pymupdf python-pptx openpyxl pyxlsb chromadb beautifulsoup4 lxml pandas tqdm
```

Если нужен OCR по сканам или кадрам видео:

```powershell
.\.venv\Scripts\python.exe -m pip install easyocr opencv-python pillow
```

## config.yaml

Файл уже создан:

```yaml
project_root: "%PROJECT_ROOT%"
work_root: "%USERPROFILE%/Desktop/AI/MeetingAgent"

ollama:
  base_url: "http://localhost:11434"
  embedding_model: "bge-m3"
  chat_model: "qwen3:8b"

rag:
  chunk_size_chars: 2200
  chunk_overlap_chars: 300
  top_k: 12
  max_context_chars: 24000

transcription:
  model: "large-v3-turbo"
  language: "ru"
  compute_type: "int8"
  device: "cpu"
  beam_size: 5
  vad_filter: true

paths:
  manifest: "data/manifest.jsonl"
  extracted_text_dir: "data/extracted_text"
  chunks: "data/chunks.jsonl"
  vector_db: "vector_db"
  logs: "logs"
  watched_folder: "watched_folder"

collections:
  project_docs: "asu_project_docs"
  meeting_transcripts: "asu_meeting_transcripts"
  protocols: "asu_protocols"

include_extensions:
  - ".docx"
  - ".pdf"
  - ".xlsx"
  - ".xlsb"
  - ".pptx"
  - ".md"
  - ".txt"
  - ".html"
  - ".json"
  - ".yml"
  - ".yaml"
  - ".drawio"
  - ".puml"
  - ".srt"
  - ".py"
  - ".js"
  - ".ts"
  - ".css"

exclude_dirs:
  - ".git"
  - "__pycache__"
  - "node_modules"
  - "_backup"
  - "backup"
  - "cache"
  - ".venv"
  - "dist"
  - "build"

exclude_extensions:
  - ".pyc"
  - ".ttf"
  - ".zip"
  - ".rar"
  - ".mp4"
```

## Шаг 1. Инвентаризация

Скрипт `01_inventory.py` должен:

1. Рекурсивно пройти по `project_root`.
2. Записать по каждому файлу:
   - путь;
   - относительный путь;
   - расширение;
   - размер;
   - дата изменения;
   - sha256;
   - статус `included`, `excluded`, `too_large`, `unsupported`.
3. Сохранить результат в:

```text
data\manifest.jsonl
```

Зачем это нужно:

- не переиндексировать неизменившиеся файлы;
- видеть состав проекта;
- отлавливать дубли;
- не тратить время на мусорные файлы.

## Шаг 2. Извлечение текста

Скрипт `02_extract_text.py` должен читать только файлы из manifest со статусом `included`.

Правила извлечения:

- `.docx`: `python-docx`
- `.pdf`: `pymupdf`
- `.xlsx`, `.xlsb`: `pandas` / `openpyxl`; листы сохранять с названием листа
- `.pptx`: `python-pptx`
- `.html`: `beautifulsoup4`, убрать scripts/styles
- `.md`, `.txt`, `.json`, `.yml`, `.py`, `.js`, `.ts`, `.css`: читать как текст
- `.mp4`: не читать; сначала транскрибировать отдельным пайплайном

Каждый извлеченный текст сохранять отдельным `.txt` в:

```text
data\extracted_text\
```

Для каждого извлечения сохранять metadata:

- исходный путь;
- тип файла;
- страница PDF / лист Excel / слайд PPTX, если применимо;
- дата индексации;
- sha256 исходника.

## Шаг 3. Чанкование

Скрипт `03_build_index.py` должен:

1. Читать извлеченные тексты.
2. Разбивать на chunks по 1800-2500 символов.
3. Делать overlap 250-350 символов.
4. Сохранять каждый chunk с metadata:
   - `chunk_id`;
   - `source_path`;
   - `source_type`;
   - `section`;
   - `page_or_sheet`;
   - `text`;
   - `sha256`;
   - `mtime`.

Сохранить chunks в:

```text
data\chunks.jsonl
```

Важно: не делать огромные chunks. Большие chunks ухудшают поиск и быстро забивают контекст.

## Шаг 4. Embeddings и ChromaDB

Для каждого chunk:

1. Отправить текст в Ollama embeddings API с моделью `bge-m3`.
2. Сохранить embedding в ChromaDB.
3. В ChromaDB metadata обязательно хранить путь к исходнику.

Коллекции:

```text
asu_project_docs
asu_meeting_transcripts
asu_protocols
```

Документы проекта, транскрипты встреч и протоколы лучше хранить в разных коллекциях, чтобы можно было искать отдельно или вместе.

## Шаг 5. Запрос к RAG

Скрипт `04_query.py` должен:

1. Принять вопрос пользователя.
2. Сделать embedding вопроса.
3. Найти `top_k` chunks в ChromaDB.
4. Сжать контекст до `max_context_chars`.
5. Отправить в `qwen3:8b` только:
   - вопрос;
   - найденные chunks;
   - metadata источников;
   - инструкцию отвечать с ссылками на файлы.

LLM не должна фантазировать. Если источников недостаточно, ответ должен быть:

```text
Недостаточно данных в индексе. Нужно проверить такие-то документы или расширить поиск.
```

## Шаг 6. Автообновление

Скрипт `05_watch_project.py` должен:

1. Следить за `project_root`.
2. При появлении или изменении файла ждать 30-60 секунд, пока запись завершится.
3. Пересчитать sha256.
4. Если файл новый или изменился:
   - извлечь текст;
   - перечанковать;
   - удалить старые chunks этого файла из ChromaDB;
   - добавить новые chunks.

Для больших папок watcher не заменяет периодический полный reindex. Раз в день или вручную запускать:

```powershell
.\.venv\Scripts\python.exe scripts\01_inventory.py
.\.venv\Scripts\python.exe scripts\02_extract_text.py
.\.venv\Scripts\python.exe scripts\03_build_index.py
```

## Как настраивать Codex / ИИ, чтобы не закончились токены

Правильный режим работы:

1. Не просить ИИ "прочитай всю папку".
2. Сначала просить построить или обновить индекс.
3. Для каждого вопроса использовать RAG-запрос.
4. В чат передавать только:
   - вопрос;
   - 5-15 найденных фрагментов;
   - ссылки на источники;
   - краткую сводку.
5. Для длинных документов делать отдельные локальные summaries и хранить их рядом с индексом.

Формулировка для агента:

```text
Используй локальный RAG-индекс проекта. Не загружай документы целиком в контекст. Для каждого ответа сначала найди релевантные chunks через vector_db, затем отвечай по найденным источникам. Если найденных источников недостаточно, явно скажи, какие документы нужно доиндексировать или открыть точечно.
```

## Как подключить встречи

После обработки новой встречи сохранять:

```text
original_video.mp4
audio.wav
transcript.md
segments.jsonl
memo.md
protocol.md
routing.json
```

Затем добавлять в RAG:

- `transcript.md` в коллекцию `asu_meeting_transcripts`;
- `memo.md` и `protocol.md` в коллекцию `asu_protocols`;
- `routing.json` использовать для связи с этапом, ФТТ и задачей.

Классификация встречи должна идти так:

1. Получить транскрипт.
2. Найти похожие chunks в `asu_project_docs`.
3. Найти похожие предыдущие встречи в `asu_meeting_transcripts`.
4. Попросить LLM выбрать:
   - проект;
   - этап;
   - ФТТ;
   - задачу;
   - уверенность;
   - причины выбора;
   - альтернативы.
5. Если уверенность ниже 0.75, положить в `_Неразобранные встречи` и запросить подтверждение пользователя.

## Минимальный порядок запуска

Установка уже выполнена. Повторять ее не нужно, если `.venv` не удалялся.

```powershell
cd "$env:USERPROFILE\Desktop\AI\MeetingAgent"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install faster-whisper watchdog requests pyyaml python-docx pymupdf python-pptx openpyxl chromadb beautifulsoup4 lxml pandas tqdm
ollama pull bge-m3
ollama pull qwen3:8b
```

Фактический следующий запуск после создания скриптов:

```powershell
.\.venv\Scripts\python.exe scripts\01_inventory.py
.\.venv\Scripts\python.exe scripts\02_extract_text.py
.\.venv\Scripts\python.exe scripts\03_build_index.py
```

После этого можно задавать вопросы через:

```powershell
.\.venv\Scripts\python.exe scripts\04_query.py "К какому этапу относится обсуждение интеграции НСИ?"
```

Оставшиеся ошибки извлечения на текущем наборе:

```text
ПД НТК/Общепроектные/КСГ_НТК.xlsx
ПД НТК/Этап 2.1/Черновики и шаблоны/Чек-лист этапа 2.1.xlsx
ПД НТК/Этап 1.2/Черновики и шаблоны/Чек-лист этапа 1.2.xlsx
```

Их можно позже открыть и пересохранить в Excel, либо добавить отдельный fallback-экстрактор.

Для проверки найденных фрагментов без LLM:

```powershell
.\.venv\Scripts\python.exe scripts\04_query.py "НСИ интеграция" --raw
```

Если нужно искать больше или меньше фрагментов:

```powershell
.\.venv\Scripts\python.exe scripts\04_query.py "Что входит в документацию для сдачи?" --top-k 20
```

## Критерий готовности

RAG считается готовым, когда:

- есть `manifest.jsonl`;
- есть извлеченные тексты;
- есть `chunks.jsonl`;
- ChromaDB содержит коллекцию `asu_project_docs`;
- запросы возвращают ответы со ссылками на конкретные файлы;
- при изменении файла индекс обновляется без полного пересоздания.
