from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from asu_june_bot.core.config import load_config, resolve_work_path
from asu_june_bot.guardrails.project_guard import GuardDecision, ProjectGuard
from asu_june_bot.retrieval.chunks import read_jsonl
from asu_june_bot.retrieval.context_builder import ContextBuilder
from asu_june_bot.retrieval.hybrid import build_hybrid_retriever
from asu_june_bot.retrieval.post_rerank import PostReranker
from asu_june_bot.retrieval.query_intent import classify_query_intent
from asu_june_bot.retrieval.vector import OllamaUnavailableError

from .models import SearchDiagnostics, SearchRequest, SearchResponse, SearchStatus, empty_context


CORPUS_NAME = "asu_june_bot_v2"


def make_v2_cfg(cfg: dict[str, Any], chunks_path: str, index_dir: str) -> dict[str, Any]:
    patched = dict(cfg)
    paths = dict(patched.get("paths") or {})
    paths["chunks"] = chunks_path
    paths["numpy_index"] = index_dir
    patched["paths"] = paths
    return patched


def unavailable_payload(query: str, mode: str, exc: Exception, query_intent: dict[str, Any] | None = None, guard: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "query": query,
        "corpus": CORPUS_NAME,
        "mode": mode,
        "status": SearchStatus.ERROR.value,
        "error_code": "ollama_unavailable",
        "error": str(exc),
        "query_intent": query_intent,
        "guard": guard,
        "next_steps": [
            "Запусти Ollama Desktop или команду: ollama serve",
            "Проверь доступность: ollama list",
            "Проверь, что модель embeddings установлена: ollama pull bge-m3",
            "После запуска Ollama повтори vector/hybrid smoke",
            "Для проверки без Ollama используй --mode bm25",
        ],
    }


class SearchService:
    """Single orchestration layer for CLI and future API search.

    The service intentionally stays synchronous because current retrieval/index/context
    components are synchronous. API routes can call it directly in MVP or wrap it in
    a worker thread later if needed.
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        guard: ProjectGuard | None = None,
        post_reranker: PostReranker | None = None,
        context_builder: ContextBuilder | None = None,
        work_root: Path | None = None,
    ) -> None:
        self.config = config
        self.guard = guard or ProjectGuard()
        self.post_reranker = post_reranker or PostReranker()
        self.context_builder = context_builder or ContextBuilder()
        self.work_root = work_root or Path.cwd()

    def search(self, request: SearchRequest) -> SearchResponse:
        diagnostics = SearchDiagnostics()

        t0 = time.perf_counter()
        query_intent_result = classify_query_intent(request.query)
        query_intent_payload = query_intent_result.to_dict()
        diagnostics.add_stage("intent", self._elapsed_ms(t0), query_intent_payload)

        t0 = time.perf_counter()
        guard_result = self.guard.evaluate(request.query, query_intent_result)
        guard_payload = guard_result.to_dict()
        diagnostics.add_stage("guard", self._elapsed_ms(t0), guard_payload)

        if not request.no_guard and not guard_result.allowed:
            status = SearchStatus.CLARIFY.value if guard_result.decision == GuardDecision.CLARIFY else SearchStatus.REFUSED.value
            payload = {
                "query": request.query,
                "corpus": CORPUS_NAME,
                "mode": request.mode,
                "status": status,
                "answer": guard_result.message,
                "query_intent": query_intent_payload,
                "guard": guard_payload,
                "warnings": [],
                "results": [],
                "context": empty_context(),
            }
            return self._with_diagnostics(payload, diagnostics, request.include_diagnostics)

        cfg = self._load_v2_config(request)
        chunks_path = resolve_work_path(cfg, request.chunks_path)
        index_dir = resolve_work_path(cfg, request.index_dir)

        t0 = time.perf_counter()
        rows = read_jsonl(chunks_path)
        diagnostics.add_stage("load_chunks", self._elapsed_ms(t0), {"chunks_path": str(chunks_path), "rows": len(rows)})

        if request.mode in {"hybrid", "vector"} and not (index_dir / "manifest.json").exists():
            raise FileNotFoundError(
                f"numpy_index_v2 не найден: {index_dir}. "
                "Сначала запусти scripts/asu_june_bot_build_index_v2.py или используй --mode bm25."
            )

        t0 = time.perf_counter()
        retriever = build_hybrid_retriever(cfg, rows, mode=request.mode)
        diagnostics.add_stage("build_retriever", self._elapsed_ms(t0), {"mode": request.mode})

        try:
            t0 = time.perf_counter()
            diagnostics.retrieval_called = True
            raw_results = retriever.search(
                query=request.query,
                top_k=max(request.top_k * 2, request.top_k + 8),
                include_source_types=request.include_source_types,
                mode=request.mode,
            )
            diagnostics.add_stage("retrieval", self._elapsed_ms(t0), {"raw_results": len(raw_results), "mode": request.mode})
        except OllamaUnavailableError as exc:
            payload = unavailable_payload(request.query, request.mode, exc, query_intent_payload, guard_payload)
            return self._with_diagnostics(payload, diagnostics, request.include_diagnostics)

        t0 = time.perf_counter()
        rerank_result = self.post_reranker.rerank(request.query, query_intent_result, raw_results, top_k=request.top_k)
        diagnostics.add_stage("rerank", self._elapsed_ms(t0), rerank_result.diagnostics)

        t0 = time.perf_counter()
        built_context = self.context_builder.build(request.query, query_intent_result, rerank_result.results, rerank_result.excluded)
        diagnostics.add_stage("context", self._elapsed_ms(t0), built_context.diagnostics)

        warnings = list(getattr(retriever, "last_warnings", []) or [])
        payload = {
            "query": request.query,
            "corpus": CORPUS_NAME,
            "mode": request.mode,
            "status": SearchStatus.OK.value,
            "top_k": request.top_k,
            "chunks_path": str(chunks_path),
            "index_dir": str(index_dir),
            "query_intent": query_intent_payload,
            "guard": guard_payload,
            "warnings": warnings,
            "rerank": rerank_result.diagnostics,
            "context": built_context.to_dict(),
            "results": [result.to_dict() for result in rerank_result.results],
        }
        return self._with_diagnostics(payload, diagnostics, request.include_diagnostics)

    def _load_v2_config(self, request: SearchRequest) -> dict[str, Any]:
        cfg = self.config or load_config()
        return make_v2_cfg(cfg, request.chunks_path, request.index_dir)

    @staticmethod
    def _elapsed_ms(start: float) -> float:
        return (time.perf_counter() - start) * 1000

    @staticmethod
    def _with_diagnostics(payload: dict[str, Any], diagnostics: SearchDiagnostics, include_diagnostics: bool) -> SearchResponse:
        if include_diagnostics:
            existing = dict(payload.get("diagnostics") or {})
            existing["search_service"] = diagnostics.to_dict()
            payload["diagnostics"] = existing
        return SearchResponse(payload=payload)
