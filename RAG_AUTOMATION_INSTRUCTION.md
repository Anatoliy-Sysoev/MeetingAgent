# Инструкция По Локальной RAG-Автоматизации

Обновлено: 2026-05-07.

Этот файл заменяет старую инструкцию периода первой долгой сборки RAG. Актуальная архитектура больше не использует ChromaDB в основном поиске: основной поисковый слой - `data/numpy_index`, который строится из `data/chunks.jsonl` и `data/embeddings_cache.jsonl`.

## Цель

Создать и поддерживать локальный RAG-индекс проектной папки без загрузки всего корпуса документов в чат.

Главные правила:

- реальные проектные документы не коммитить;
- `data/embeddings_cache.jsonl` не удалять без явной причины;
- каждый embedding-запрос к Ollama должен передавать `options.num_ctx=8192` и `keep_alive=24h`;
- ChromaDB и `vector_db/` не использовать как основной путь поиска;
- полный build не запускать второй раз, если уже жив `03_build_index.py`.

## Актуальный Поток

```powershell
cd "$env:USERPROFILE\Desktop\AI\MeetingAgent"
.\.venv\Scripts\python.exe scripts\01_inventory.py
.\.venv\Scripts\python.exe scripts\02_extract_text.py
.\.venv\Scripts\python.exe scripts\03_build_index.py
.\.venv\Scripts\python.exe scripts\05_build_numpy_index.py
```

Или одной командой:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\run_full_rag.ps1
```

## Что Делает Каждый Шаг

1. `01_inventory.py` сканирует проектную папку и пишет `data/manifest.jsonl`.
2. `02_extract_text.py` извлекает текст в `data/extracted_text/`.
3. `03_build_index.py` создает `data/chunks.jsonl` и пополняет `data/embeddings_cache.jsonl`.
4. `05_build_numpy_index.py` строит `data/numpy_index/`.
5. `04_query.py` задает вопросы через numpy-индекс или fallback по JSONL cache.

## Проверка

Компактная проверка источников:

```powershell
.\.venv\Scripts\python.exe scripts\04_query.py "Что входит в Паспорт ИС?" --top-k 8 --compact
```

JSON для baseline качества:

```powershell
.\.venv\Scripts\python.exe scripts\04_query.py "Что входит в Паспорт ИС?" --top-k 8 --raw
```

Набор контрольных вопросов: `docs/quality/rag_eval_questions.md`.

## Мониторинг

`monitor_rag.ps1` - один тик мониторинга. Его можно запускать вручную или по расписанию.

Инварианты:

- не запускать второй build, если жив `03_build_index.py`;
- не убивать живой Python build worker;
- при stall перезапускать только Ollama;
- stale lock удалять только если нет живого build worker;
- failed markers архивировать, если они устарели.

## Backup

Главный артефакт для сохранения:

```text
data/embeddings_cache.jsonl
```

Подробные правила: `docs/operations/BACKUP_AND_RETENTION.md`.

## Устаревшие Сведения

Старые упоминания ChromaDB, коллекций Chroma и `vector_db/` относятся к прошлой версии потока сборки. `vector_db/` может оставаться на диске как локальная устаревшая папка, но основной RAG ее не читает и не пересоздает.
