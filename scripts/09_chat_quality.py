from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

from rag_retrieval_quality import (
    build_quality_expansion,
    has_no_answer_marker,
    quality_confidence,
    rerank_contexts,
)


CHAT_PATH = Path(__file__).with_name("09_chat.py")


def load_chat_module():
    spec = importlib.util.spec_from_file_location("meetingagent_09_chat", CHAT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load chat module: {CHAT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["meetingagent_09_chat"] = module
    spec.loader.exec_module(module)
    return module


def patch_chat(chat: Any) -> None:
    original_build_retrieval_query = chat.build_retrieval_query
    original_query_contexts = chat.query_contexts
    original_normalize_source = chat.normalize_source
    original_answer_response = chat.answer_response
    original_build_query_log_record = chat.build_query_log_record

    def build_retrieval_query_quality(question: str) -> str:
        base_query = original_build_retrieval_query(question)
        quality_query = build_quality_expansion(question)
        if quality_query == question:
            return base_query
        return base_query + "\n" + quality_query

    def query_contexts_quality(
        cfg: dict[str, Any],
        question: str,
        top_k: int,
        include_excluded: bool,
        no_dedupe: bool,
    ) -> list[dict[str, Any]]:
        # Oversampling before lexical/section-aware rerank. This keeps the same public top_k,
        # but gives the reranker enough candidates for structured documents such as FTT/PMI.
        oversampled_top_k = max(top_k * 4, top_k, 12)
        raw_contexts = original_query_contexts(
            cfg,
            question,
            oversampled_top_k,
            include_excluded,
            no_dedupe,
        )
        return rerank_contexts(question, raw_contexts, top_k)

    def normalize_source_quality(ctx: dict[str, Any], idx: int, source_links: dict[str, str] | None = None) -> dict[str, Any]:
        source = original_normalize_source(ctx, idx, source_links)
        meta = ctx.get("metadata", {}) or {}
        quality = meta.get("quality")
        if quality:
            source["quality"] = quality
            source["retrieval"] = meta.get("retrieval", source.get("retrieval"))
        return source

    def answer_response_quality(
        question: str,
        answer: str,
        sources: list[dict[str, Any]],
        threshold: float,
        answer_mode: str = "llm",
        details: str | None = None,
    ) -> dict[str, Any]:
        result = original_answer_response(question, answer, sources, threshold, answer_mode, details)
        result["confidence"] = quality_confidence(sources, threshold, answer)
        result.setdefault("diagnostics", {})
        result["diagnostics"]["retrieval_quality"] = {
            "enabled": True,
            "rerank": "hybrid_vector_lexical",
            "oversampling": "top_k_x4_min_12",
            "top_source_quality": sources[0].get("quality") if sources else None,
        }
        if has_no_answer_marker(answer):
            result["status"] = "no_answer"
            result["refusal_reason"] = "insufficient_grounding_in_sources"
            result["diagnostics"]["no_answer_marker_detected"] = True
        return result

    def build_query_log_record_quality(result: dict[str, Any], args: Any) -> dict[str, Any]:
        record = original_build_query_log_record(result, args)
        record["diagnostics"] = result.get("diagnostics")
        record["top_sources"] = []
        for src in result.get("sources", [])[:8]:
            quality = src.get("quality") or {}
            record["top_sources"].append(
                {
                    "relative_path": src.get("relative_path"),
                    "chunk_index": src.get("chunk_index"),
                    "score": round(float(src.get("score", 0.0)), 6),
                    "retrieval": src.get("retrieval"),
                    "lexical_score": quality.get("lexical_score"),
                    "matched_terms": quality.get("matched_terms"),
                    "matched_numbers": quality.get("matched_numbers"),
                    "phrase_matches": quality.get("phrase_matches"),
                }
            )
        return record

    chat.build_retrieval_query = build_retrieval_query_quality
    chat.query_contexts = query_contexts_quality
    chat.normalize_source = normalize_source_quality
    chat.answer_response = answer_response_quality
    chat.confidence_from_sources = lambda sources, threshold: quality_confidence(sources, threshold)
    chat.build_query_log_record = build_query_log_record_quality


def main() -> None:
    chat = load_chat_module()
    patch_chat(chat)
    chat.main()


if __name__ == "__main__":
    main()
