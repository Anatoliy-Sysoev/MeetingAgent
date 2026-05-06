from __future__ import annotations

import argparse
import json
from typing import Any

import chromadb
import requests

from rag_common import ensure_runtime_dirs, load_config, resolve_work_path


def ollama_embed(base_url: str, model: str, text: str) -> list[float]:
    resp = requests.post(
        f"{base_url.rstrip('/')}/api/embeddings",
        json={"model": model, "prompt": text},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["embedding"]


def ollama_chat(base_url: str, model: str, prompt: str) -> str:
    resp = requests.post(
        f"{base_url.rstrip('/')}/api/generate",
        json={
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.2,
                "top_p": 0.9,
            },
        },
        timeout=300,
    )
    resp.raise_for_status()
    return resp.json().get("response", "").strip()


def build_prompt(question: str, contexts: list[dict[str, Any]]) -> str:
    blocks = []
    for i, ctx in enumerate(contexts, start=1):
        meta = ctx["metadata"]
        blocks.append(
            "\n".join(
                [
                    f"[Источник {i}]",
                    f"Файл: {meta.get('relative_path')}",
                    f"Chunk: {meta.get('chunk_index')}",
                    ctx["document"],
                ]
            )
        )

    context_text = "\n\n---\n\n".join(blocks)
    return f"""Ты локальный RAG-ассистент по проекту АСУ.

Отвечай только по предоставленным источникам. Если данных недостаточно, прямо скажи, что в найденных фрагментах недостаточно информации.
В конце добавь раздел "Источники" со списком использованных файлов.

Вопрос:
{question}

Найденные фрагменты:
{context_text}
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Query local ASU RAG index")
    parser.add_argument("question", nargs="+", help="Вопрос к RAG-индексу")
    parser.add_argument("--top-k", type=int, default=None, help="Сколько chunks искать")
    parser.add_argument("--raw", action="store_true", help="Показать найденные chunks без LLM-ответа")
    args = parser.parse_args()

    question = " ".join(args.question).strip()
    cfg = load_config()
    ensure_runtime_dirs(cfg)

    base_url = cfg["ollama"]["base_url"]
    embedding_model = cfg["ollama"]["embedding_model"]
    chat_model = cfg["ollama"]["chat_model"]
    vector_db_path = resolve_work_path(cfg, cfg["paths"]["vector_db"])
    collection_name = cfg["collections"]["project_docs"]
    top_k = args.top_k or int(cfg["rag"]["top_k"])
    max_context_chars = int(cfg["rag"]["max_context_chars"])

    client = chromadb.PersistentClient(path=str(vector_db_path))
    collection = client.get_collection(collection_name)
    query_embedding = ollama_embed(base_url, embedding_model, question)
    result = collection.query(query_embeddings=[query_embedding], n_results=top_k, include=["documents", "metadatas", "distances"])

    contexts = []
    used_chars = 0
    for doc, meta, dist in zip(result["documents"][0], result["metadatas"][0], result["distances"][0]):
        if used_chars + len(doc) > max_context_chars and contexts:
            break
        contexts.append({"document": doc, "metadata": meta, "distance": dist})
        used_chars += len(doc)

    if args.raw:
        print(json.dumps(contexts, ensure_ascii=False, indent=2))
        return

    prompt = build_prompt(question, contexts)
    answer = ollama_chat(base_url, chat_model, prompt)
    print(answer)


if __name__ == "__main__":
    main()
