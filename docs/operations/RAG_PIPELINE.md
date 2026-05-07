# Поток Сборки RAG

## Текущий Поток

1. `01_inventory.py`
   - сканирует папку проекта;
   - применяет `exclude_dirs`, `exclude_extensions` и `exclude_path_patterns`;
   - записывает metadata файлов в `data/manifest.jsonl`.

2. `02_extract_text.py`
   - извлекает текст из поддерживаемых форматов;
   - сохраняет извлеченный текст и metadata.

3. `03_build_index.py`
   - режет извлеченный текст на chunks;
   - переиспользует `data/embeddings_cache.jsonl`;
   - вызывает Ollama `/api/embeddings`;
   - дописывает недостающие embeddings в cache;
   - не пересоздает ChromaDB и не пишет в `vector_db/`.

4. `05_build_numpy_index.py`
   - собирает основной локальный numpy-индекс в `data/numpy_index`;
   - использует готовые chunks и embeddings cache;
   - не пересчитывает embeddings.

5. `04_query.py`
   - строит embedding запроса;
   - достает top chunks из `data/numpy_index`;
   - по умолчанию фильтрует служебные и архивные пути из `exclude_path_patterns`;
   - дедуплицирует одинаковые chunks по тексту;
   - если numpy-индекса нет, использует fallback напрямую по JSONL cache;
   - просит локальную LLM ответить с учетом найденного контекста.

## Гигиена Корпуса

Рабочая папка проекта может содержать архивы, черновики, backup-копии и служебные результаты анализа. Они остаются на диске, но не должны попадать в продуктивный RAG.

В `config.example.yaml` для этого предусмотрены:

- `exclude_dirs`: быстрые исключения по имени папки;
- `exclude_path_patterns`: glob-паттерны для точных случаев вроде `_analysis/docx_json*/**`, `**/Архив/**`, `**/Черновики и шаблоны/**`.

Curated markdown-заметки в `_analysis/*.md` могут оставаться источниками, если содержат выводы по замечаниям, сверкам и расхождениям. Сгенерированные JSON/Docx-слепки и рабочие папки `_analysis/docx_json*` исключаются.

## Параметры Chunking

Текущие параметры MVP:

- `chunk_size_chars`: 3000;
- `chunk_overlap_chars`: 300.

Эти параметры влияют на `chunk_id`. При их изменении часть старого embeddings cache становится устаревшей по дизайну, потому что меняются границы chunks.

## Требования К Embeddings

Каждый embedding-запрос должен включать:

```json
{
  "model": "bge-m3",
  "keep_alive": "24h",
  "options": {
    "num_ctx": 8192
  }
}
```

## Стратегия Продолжения

Самая долгая часть - генерация embeddings. Каждый готовый embedding сразу дописывается в `data/embeddings_cache.jsonl`.

Если процесс остановился:

- не удалять `embeddings_cache.jsonl`;
- удалять stale lock только если нет живого процесса `03_build_index.py`;
- перезапустить `run_full_rag.ps1`;
- уже посчитанные chunks будут пропущены.

## Проверка

После сборки:

- проверить наличие done marker;
- проверить `data/numpy_index/manifest.json`;
- сравнить количество chunks в manifest с `data/chunks.jsonl`;
- выполнить smoke-запросы;
- проверить релевантность источников.

## Проверка Query

Компактный вывод источников:

```powershell
.\.venv\Scripts\python.exe scripts\04_query.py "Что входит в Паспорт ИС?" --top-k 8 --compact
```

JSON для evaluation:

```powershell
.\.venv\Scripts\python.exe scripts\04_query.py "Что входит в Паспорт ИС?" --top-k 8 --raw
```

Диагностика без query-фильтров и дедупликации:

```powershell
.\.venv\Scripts\python.exe scripts\04_query.py "Что входит в Паспорт ИС?" --top-k 8 --compact --include-excluded --no-dedupe
```
