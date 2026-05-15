from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests

from asu_june_bot.core.config import load_config, resolve_work_path


DEFAULT_CHUNKS_PATH = "data/asu_june_bot/chunks_v2.jsonl"
DEFAULT_CACHE_PATH = "data/asu_june_bot/embeddings_cache_v2.jsonl"
DEFAULT_INDEX_DIR = "data/asu_june_bot/numpy_index_v2"
DEFAULT_REPORT_PATH = "data/asu_june_bot/index_v2_report.json"


def count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    count = 0
    with path.open("r", encoding="utf-8") as fp:
        for line in fp:
            if line.strip():
                count += 1
    return count


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def check_ollama(base_url: str, embedding_model: str, timeout_sec: int) -> dict[str, Any]:
    result: dict[str, Any] = {
        "base_url": base_url,
        "available": False,
        "embedding_model": embedding_model,
        "embedding_model_installed": False,
        "models": [],
        "error": None,
    }
    try:
        response = requests.get(f"{base_url.rstrip('/')}/api/tags", timeout=timeout_sec)
        response.raise_for_status()
        data = response.json()
        models = [str(item.get("name") or item.get("model") or "") for item in data.get("models", [])]
        result["available"] = True
        result["models"] = models
        result["embedding_model_installed"] = any(model == embedding_model or model.startswith(f"{embedding_model}:") for model in models)
    except Exception as exc:  # noqa: BLE001
        result["error"] = repr(exc)
    return result


def health_status(ok: bool) -> str:
    return "ok" if ok else "error"


class HealthService:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config

    def check(
        self,
        chunks_path: str = DEFAULT_CHUNKS_PATH,
        cache_path: str = DEFAULT_CACHE_PATH,
        index_dir: str = DEFAULT_INDEX_DIR,
        report_path: str = DEFAULT_REPORT_PATH,
        timeout_sec: int = 5,
    ) -> dict[str, Any]:
        cfg = self.config or load_config()
        chunks_file = resolve_work_path(cfg, chunks_path)
        cache_file = resolve_work_path(cfg, cache_path)
        index_path = resolve_work_path(cfg, index_dir)
        manifest_path = index_path / "manifest.json"
        embeddings_path = index_path / "embeddings.npy"
        metadata_path = index_path / "metadata.jsonl"
        report_file = resolve_work_path(cfg, report_path)

        manifest = read_json(manifest_path)
        report = read_json(report_file)
        chunks_count = count_jsonl(chunks_file)
        cache_count = count_jsonl(cache_file)
        index_metadata_count = count_jsonl(metadata_path)

        base_url = str(cfg.get("ollama", {}).get("base_url", "http://127.0.0.1:11434"))
        embedding_model = str(cfg.get("ollama", {}).get("embedding_model", "bge-m3"))
        ollama = check_ollama(base_url, embedding_model, timeout_sec)

        manifest_count = int(manifest.get("count", 0)) if manifest else 0
        index_ok = bool(manifest and embeddings_path.exists() and metadata_path.exists() and manifest_count == index_metadata_count)
        cache_ok = cache_count >= manifest_count > 0 if manifest else cache_count > 0
        chunks_ok = chunks_count > 0
        vector_ready = index_ok and cache_ok and ollama.get("available") and ollama.get("embedding_model_installed")

        payload = {
            "status": health_status(chunks_ok and index_ok and cache_ok),
            "service": "asu_june_bot",
            "corpus_ready": bool(chunks_ok),
            "vector_ready": bool(vector_ready),
            "bm25_ready": bool(chunks_ok),
            "guard_v2_ready": True,
            "paths": {
                "chunks_v2": str(chunks_file),
                "embeddings_cache_v2": str(cache_file),
                "numpy_index_v2": str(index_path),
                "manifest": str(manifest_path),
                "index_metadata": str(metadata_path),
                "index_embeddings": str(embeddings_path),
                "index_report": str(report_file),
            },
            "counts": {
                "chunks_v2": chunks_count,
                "embeddings_cache_v2": cache_count,
                "manifest_count": manifest_count,
                "index_metadata": index_metadata_count,
                "report_index_count": (report or {}).get("summary", {}).get("index_count") if report else None,
            },
            "checks": {
                "chunks_exists": chunks_file.exists(),
                "cache_exists": cache_file.exists(),
                "manifest_exists": manifest_path.exists(),
                "embeddings_npy_exists": embeddings_path.exists(),
                "metadata_jsonl_exists": metadata_path.exists(),
                "index_count_matches_metadata": manifest_count == index_metadata_count if manifest else False,
                "cache_count_covers_index": cache_ok,
                "ollama_available": bool(ollama.get("available")),
                "embedding_model_installed": bool(ollama.get("embedding_model_installed")),
            },
            "ollama": ollama,
            "next_steps": [],
        }

        if not chunks_ok:
            payload["next_steps"].append("Собери chunks: python scripts/asu_june_bot_build_chunks_v2.py")
        if not cache_ok:
            payload["next_steps"].append("Дособери embeddings cache: python scripts/asu_june_bot_build_index_v2.py --embed-only")
        if not index_ok:
            payload["next_steps"].append("Построй индекс: python scripts/asu_june_bot_build_index_v2.py --index-only")
        if not ollama.get("available"):
            payload["next_steps"].append("Запусти Ollama Desktop или команду: ollama serve")
        if ollama.get("available") and not ollama.get("embedding_model_installed"):
            payload["next_steps"].append(f"Установи embedding model: ollama pull {embedding_model}")
        if vector_ready:
            payload["next_steps"].append("Vector/hybrid search готов. Можно запускать smoke search_v2 --mode hybrid")
        elif chunks_ok:
            payload["next_steps"].append("BM25 search готов. Vector/hybrid заработает после запуска Ollama и проверки embedding model")

        return payload
