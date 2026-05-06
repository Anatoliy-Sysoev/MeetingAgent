# RAG Pipeline

## Текущий Поток

1. `01_inventory.py`
   - сканирует папку проекта;
   - записывает metadata файлов в `data/manifest.jsonl`.

2. `02_extract_text.py`
   - извлекает текст из поддерживаемых форматов;
   - сохраняет извлеченный текст и metadata.

3. `03_build_index.py`
   - режет извлеченный текст на chunks;
   - переиспользует `data/embeddings_cache.jsonl`;
   - вызывает Ollama `/api/embeddings`;
   - записывает ChromaDB в `vector_db/`.

4. `04_query.py`
   - строит embedding запроса;
   - достает top chunks;
   - просит локальную LLM ответить с учетом найденного контекста.

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
- проверить количество записей в коллекции ChromaDB;
- выполнить smoke-запросы;
- проверить релевантность источников.
