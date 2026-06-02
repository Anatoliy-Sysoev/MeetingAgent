from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from asu_june_bot.core.config import load_config, resolve_work_path
from asu_june_bot.core.corpus import get_corpus_config
from asu_june_bot.guardrails.project_guard import GuardDecision, ProjectGuard
from asu_june_bot.retrieval.chunks import read_jsonl
from asu_june_bot.retrieval.context_builder import ContextBuilder
from asu_june_bot.retrieval.hybrid import build_hybrid_retriever
from asu_june_bot.retrieval.models import SearchResult
from asu_june_bot.retrieval.post_rerank import PostReranker
from asu_june_bot.retrieval.query_intent import classify_query_intent
from asu_june_bot.retrieval.vector import OllamaUnavailableError

from .models import SearchDiagnostics, SearchRequest, SearchResponse, SearchStatus, empty_context


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
                "corpus": self._corpus_name(cfg=None),
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
        corpus = get_corpus_config(cfg)
        chunks_path_raw = request.chunks_path or corpus.chunks_path
        index_dir_raw = request.index_dir or corpus.index_dir
        chunks_path = resolve_work_path(cfg, chunks_path_raw)
        index_dir = resolve_work_path(cfg, index_dir_raw)

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
            payload["corpus"] = corpus.name
            payload["corpus_key"] = corpus.key
            return self._with_diagnostics(payload, diagnostics, request.include_diagnostics)

        t0 = time.perf_counter()
        rerank_result = self.post_reranker.rerank(request.query, query_intent_result, raw_results, top_k=request.top_k)
        diagnostics.add_stage("rerank", self._elapsed_ms(t0), rerank_result.diagnostics)

        t0 = time.perf_counter()
        built_context = self.context_builder.build(request.query, query_intent_result, rerank_result.results, rerank_result.excluded)
        built_context = self._promote_ad_cc_role_mapping_sources(request.query, built_context)
        diagnostics.add_stage("context", self._elapsed_ms(t0), built_context.diagnostics)

        warnings = list(getattr(retriever, "last_warnings", []) or [])
        payload = {
            "query": request.query,
            "corpus": corpus.name,
            "corpus_key": corpus.key,
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
        corpus = get_corpus_config(cfg)
        return make_v2_cfg(cfg, request.chunks_path or corpus.chunks_path, request.index_dir or corpus.index_dir)

    def _corpus_name(self, cfg: dict[str, Any] | None) -> str:
        resolved_cfg = cfg or self.config or load_config()
        return get_corpus_config(resolved_cfg).name

    @staticmethod
    def _is_ad_cc_role_mapping_query(query: str) -> bool:
        lowered = " ".join((query or "").lower().split())
        has_explicit_cc_group = "app_ccpm_ul_cc" in lowered
        has_app_group = "app_ccpm" in lowered
        has_role_route = any(marker in lowered for marker in ("роль", "роли", "ролей", "mapping", "маппинг", "соответствие", "связаны"))
        has_cc_route = any(marker in lowered for marker in ("строительного контроля", "строительный контроль", "ск"))
        return has_explicit_cc_group or (has_app_group and has_role_route and has_cc_route)

    @staticmethod
    def _is_ad_cc_role_mapping_source(source: SearchResult) -> bool:
        text = " ".join((source.text or "").lower().split())
        metadata = source.metadata or {}
        metadata_text = " ".join(
            str(metadata.get(key) or "").lower()
            for key in ("document_type", "relative_path", "source_path", "title", "section", "table_id", "table_title")
        )
        has_group = any(marker in text or marker in metadata_text for marker in ("app_ccpm_ul_cc_01", "app_ccpm_ul_cc_02", "app_ccpm_ul_cc_03"))
        has_role = any(
            marker in text or marker in metadata_text
            for marker in (
                "куратор проекта нул",
                "отвечающий за выполнение функции строительного контроля",
                "отвечающий за подачу факта",
                "роли / группы ad",
                "пользовательские роли",
            )
        )
        return has_group and has_role

    @staticmethod
    def _is_soi_ad_source(source: SearchResult) -> bool:
        metadata = source.metadata or {}
        document_type = str(metadata.get("document_type") or "")
        path = str(metadata.get("relative_path") or metadata.get("source_path") or "").lower()
        return document_type == "СоИ AD" or "сои_ad" in path or "active directory" in path

    @staticmethod
    def _result_key(source: SearchResult) -> str:
        metadata = source.metadata or {}
        return str(metadata.get("chunk_id") or metadata.get("db_id") or source.source_id)

    def _promote_ad_cc_role_mapping_sources(self, query: str, built_context: Any) -> Any:
        if not self._is_ad_cc_role_mapping_query(query):
            return built_context

        primary = list(getattr(built_context, "primary_sources", []) or [])
        supporting = list(getattr(built_context, "supporting_sources", []) or [])
        excluded = list(getattr(built_context, "excluded_sources", []) or [])
        candidates = primary + supporting + excluded
        mapping_source = next((source for source in candidates if self._is_ad_cc_role_mapping_source(source)), None)

        diagnostics = dict(getattr(built_context, "diagnostics", {}) or {})
        if mapping_source is None:
            diagnostics["ad_cc_role_mapping_promotion"] = {"applied": False, "reason": "no_mapping_source"}
            built_context.diagnostics = diagnostics
            return built_context

        mapping_key = self._result_key(mapping_source)
        moved_soi_keys: list[str] = []

        def without_mapping(items: list[SearchResult]) -> list[SearchResult]:
            return [item for item in items if self._result_key(item) != mapping_key]

        primary = without_mapping(primary)
        supporting = without_mapping(supporting)
        excluded = without_mapping(excluded)

        soi_from_primary = [item for item in primary if self._is_soi_ad_source(item)]
        if soi_from_primary:
            moved_soi_keys = [self._result_key(item) for item in soi_from_primary]
        primary = [item for item in primary if not self._is_soi_ad_source(item)]
        supporting = soi_from_primary + supporting
        primary = [mapping_source] + primary

        primary_limit = int(getattr(self.context_builder, "primary_limit", 5) or 5)
        supporting_limit = int(getattr(self.context_builder, "supporting_limit", 5) or 5)
        overflow_primary = primary[primary_limit:]
        primary = primary[:primary_limit]
        supporting = (supporting + overflow_primary)[:supporting_limit]

        diagnostics["ad_cc_role_mapping_promotion"] = {
            "applied": True,
            "promoted_key": mapping_key,
            "moved_soi_ad_from_primary_to_supporting": moved_soi_keys,
            "reason": "app_ccpm_ul_cc_role_mapping_query",
        }
        built_context.primary_sources = primary
        built_context.supporting_sources = supporting
        built_context.excluded_sources = excluded
        built_context.diagnostics = diagnostics
        return built_context

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
