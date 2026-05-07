from __future__ import annotations

import json

from rag_common import ensure_runtime_dirs, load_config, print_summary, resolve_work_path
from rag_numpy_backend import build_index


def main() -> None:
    cfg = load_config()
    ensure_runtime_dirs(cfg)

    paths = cfg["paths"]
    chunks_path = resolve_work_path(cfg, paths["chunks"])
    embeddings_cache_path = resolve_work_path(cfg, paths.get("embeddings_cache", "data/embeddings_cache.jsonl"))
    index_dir = resolve_work_path(cfg, paths.get("numpy_index", "data/numpy_index"))
    embedding_model = cfg["ollama"]["embedding_model"]

    manifest = build_index(
        chunks_path=chunks_path,
        embeddings_cache_path=embeddings_cache_path,
        index_dir=index_dir,
        embedding_model=embedding_model,
    )

    print_summary(
        "Numpy RAG index",
        {
            "backend": manifest["backend"],
            "embedding_model": manifest["embedding_model"],
            "embedding_dim": manifest["embedding_dim"],
            "count": manifest["count"],
            "index_dir": index_dir,
        },
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
