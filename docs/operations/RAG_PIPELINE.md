# RAG Pipeline

## Current Pipeline

1. `01_inventory.py`
   - scans project folder;
   - writes file metadata to `data/manifest.jsonl`.

2. `02_extract_text.py`
   - extracts text from supported document formats;
   - writes extracted text and metadata.

3. `03_build_index.py`
   - chunks extracted text;
   - reuses `data/embeddings_cache.jsonl`;
   - calls Ollama `/api/embeddings`;
   - writes ChromaDB to `vector_db/`.

4. `04_query.py`
   - embeds query;
   - retrieves top chunks;
   - asks local LLM to answer with context.

## Embedding Requirements

Every embedding request must include:

```json
{
  "model": "bge-m3",
  "keep_alive": "24h",
  "options": {
    "num_ctx": 8192
  }
}
```

## Resume Strategy

The long part is embedding generation. Each completed embedding is appended to `data/embeddings_cache.jsonl`.

If the process stops:

- do not delete `embeddings_cache.jsonl`;
- remove stale lock only if no `03_build_index.py` process is alive;
- restart `run_full_rag.ps1`;
- already cached chunks are skipped.

## Validation

After build:

- verify done marker exists;
- verify ChromaDB collection count;
- run smoke queries;
- inspect sources and relevance.

