from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from typing import Any

from rag_retrieval_quality import (
    build_quality_expansion,
    has_no_answer_marker,
    lexical_score,
    quality_confidence,
    rerank_contexts,
)


CHAT_PATH = Path(__file__).with_name("09_chat.py")

PROJECT_AUTH_ALLOW_TERMS = (
    "bearer",
    "jwt",
    "oauth",
    "oidc",
    "ldaps",
    "blitz",
)

PROJECT_AUTH_CONTEXT_TERMS = (
    "цп упкс",
    "сои",
    "интеграц",
    "справоч",
    "mdr",
    "active directory",
    " ad ",
    "авторизац",
)

TARGET_PATH_CHECKS = {
    "ftt": ("фтт", "функционально-технические"),
    "pr": ("проектное решение", "пр_смр", "строительный_контроль"),
    "cta": ("цта", "целевая техническая архитектура"),
    "soi_ad": ("сои_ad", "active directory", "ad.docx"),
    "soi_nsi": ("сои_справочники", "справочники", "mdr"),
    "pmi": ("пми", "пси", "протокол испытаний", "сценарии"),
    "passport": ("паспорт",),
}


def norm(text: str) -> str:
    return " ".join(str(text or "").lower().replace("ё", "е").split())


def is_project_auth_question(question: str) -> bool:
    lowered = f" {norm(question)} "
    has_allowed_auth_term = any(term in lowered for term in PROJECT_AUTH_ALLOW_TERMS)
    has_project_context = any(term in lowered for term in PROJECT_AUTH_CONTEXT_TERMS)
    return has_allowed_auth_term and has_project_context


def target_labels(question: str) -> set[str]:
    lowered = norm(question)
    labels: set[str] = set()
    if "фтт" in lowered or "требован" in lowered or any(x in lowered for x in ("4.1", "4.2", "4.3", "9.6", "10.8")):
        labels.add("ftt")
    if "проектное решение" in lowered or "пр " in lowered or "бизнес-процесс" in lowered or "статусная схема" in lowered:
        labels.add("pr")
    if "цта" in lowered or "архитектур" in lowered or any(x in lowered for x in ("postgresql", "kubernetes", "minio", "loki", "grafana")):
        labels.add("cta")
    if "active directory" in lowered or re.search(r"\bad\b", lowered) or "ldaps" in lowered or "групп" in lowered:
        labels.add("soi_ad")
    if "mdr" in lowered or "кшд" in lowered or "справоч" in lowered or "нси" in lowered or "bearer" in lowered:
        labels.add("soi_nsi")
    if "пми" in lowered or "пси" in lowered or "сфт" in lowered or "снт" in lowered:
        labels.add("pmi")
    if "паспорт" in lowered:
        labels.add("passport")
    return labels


def path_matches(relative_path: str, labels: set[str]) -> bool:
    path = norm(relative_path)
    return any(any(fragment in path for fragment in TARGET_PATH_CHECKS.get(label, ())) for label in labels)


def row_to_context(row: dict[str, Any], score: float, retrieval: str) -> dict[str, Any]:
    meta = {
        "chunk_id": row.get("chunk_id"),
        "db_id": row.get("db_id"),
        "source_path": row.get("source_path"),
        "relative_path": row.get("relative_path"),
        "extension": row.get("extension"),
        "sha256": row.get("sha256"),
        "mtime": float(row.get("mtime", 0.0) or 0.0),
        "chunk_index": int(row.get("chunk_index", 0) or 0),
        "chars": int(row.get("chars", len(str(row.get("text", "")))) or 0),
        "retrieval": retrieval,
    }
    return {
        "document": row.get("text", ""),
        "metadata": meta,
        "distance": float(1.0 - score),
        "score": score,
    }


def targeted_contexts(chat: Any, cfg: dict[str, Any], question: str, limit: int) -> list[dict[str, Any]]:
    labels = target_labels(question)
    if not labels:
        return []

    chunks_path = chat.resolve_work_path(cfg, cfg["paths"].get("chunks", "data/chunks.jsonl"))
    if not chunks_path.exists():
        return []

    scored: list[dict[str, Any]] = []
    for row in chat.jsonl_read(chunks_path):
        relative_path = str(row.get("relative_path") or "")
        if not path_matches(relative_path, labels):
            continue
        text = str(row.get("text") or "")
        q = lexical_score(question, text, relative_path)
        lexical = float(q.get("lexical_score", 0.0) or 0.0)
        if lexical < 0.20 and not q.get("matched_numbers") and not q.get("phrase_matches"):
            continue
        score = min(1.0, 0.30 + lexical + (0.12 if q.get("matched_numbers") else 0.0) + (0.08 if q.get("phrase_matches") else 0.0))
        ctx = row_to_context(row, score, "targeted_lexical_scan")
        meta = dict(ctx["metadata"])
        meta["quality"] = {**q, "vector_score": 0.0, "final_score": round(score, 6)}
        ctx["metadata"] = meta
        scored.append(ctx)

    scored.sort(key=lambda item: float(item.get("score", 0.0)), reverse=True)
    return scored[:limit]


def reattach_quality_to_contexts(question: str, contexts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # document_expansion creates fresh contexts and drops quality metadata. Recompute it here.
    return rerank_contexts(question, contexts, len(contexts))


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
    original_is_sensitive_question = chat.is_sensitive_question
    original_expand_contexts_by_document = chat.expand_contexts_by_document

    def is_sensitive_question_quality(question: str) -> bool:
        if is_project_auth_question(question):
            return False
        return original_is_sensitive_question(question)

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
        oversampled_top_k = max(top_k * 8, top_k, 48)
        raw_contexts = original_query_contexts(
            cfg,
            question,
            oversampled_top_k,
            include_excluded,
            no_dedupe,
        )
        targeted = targeted_contexts(chat, cfg, question, limit=max(top_k * 4, 16))
        merged: list[dict[str, Any]] = []
        seen: set[tuple[str, int]] = set()
        for ctx in [*targeted, *raw_contexts]:
            meta = ctx.get("metadata", {}) or {}
            key = (str(meta.get("relative_path")), int(meta.get("chunk_index", 0) or 0))
            if key in seen:
                continue
            seen.add(key)
            merged.append(ctx)
        return rerank_contexts(question, merged, top_k)

    def expand_contexts_by_document_quality(
        cfg: dict[str, Any],
        contexts: list[dict[str, Any]],
        expand_top_documents: int,
        document_expansion_chunks: int,
    ) -> list[dict[str, Any]]:
        expanded = original_expand_contexts_by_document(cfg, contexts, expand_top_documents, document_expansion_chunks)
        question = getattr(chat, "_quality_current_question", "")
        if question:
            return reattach_quality_to_contexts(question, expanded)
        return expanded

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
            "rerank": "hybrid_vector_lexical_with_targeted_scan",
            "oversampling": "top_k_x8_min_48",
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
                    "target_path_labels": quality.get("target_path_labels"),
                    "path_target_match": quality.get("path_target_match"),
                }
            )
        return record

    def build_answer_prompt_quality(question: str, contexts: list[dict[str, Any]], prompt_template: str, source_char_limit: int, source_links: dict[str, str] | None = None) -> str:
        chat._quality_current_question = question
        return chat.build_answer_prompt_original(question, contexts, prompt_template, source_char_limit, source_links)

    chat.build_answer_prompt_original = chat.build_answer_prompt
    chat.is_sensitive_question = is_sensitive_question_quality
    chat.build_retrieval_query = build_retrieval_query_quality
    chat.query_contexts = query_contexts_quality
    chat.expand_contexts_by_document = expand_contexts_by_document_quality
    chat.normalize_source = normalize_source_quality
    chat.answer_response = answer_response_quality
    chat.confidence_from_sources = lambda sources, threshold: quality_confidence(sources, threshold)
    chat.build_query_log_record = build_query_log_record_quality
    chat.build_answer_prompt = build_answer_prompt_quality


def main() -> None:
    chat = load_chat_module()
    patch_chat(chat)
    chat.main()


if __name__ == "__main__":
    main()
