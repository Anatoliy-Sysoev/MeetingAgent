from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from asu_june_bot.guardrails.project_guard import GuardDecision, ProjectGuardResult
from asu_june_bot.retrieval.models import SearchResult
from asu_june_bot.retrieval.post_rerank import RerankResult
from asu_june_bot.retrieval.query_intent import QueryIntent, QueryIntentResult
from asu_june_bot.search.models import SearchRequest
from asu_june_bot.search.service import SearchService


class FakeBuiltContext:
    diagnostics = {"builder": "fake", "primary_count": 1, "supporting_count": 0, "excluded_count": 0}

    def to_dict(self):
        return {
            "primary_sources": [{"source_id": "SRC-001", "text_preview": "primary"}],
            "supporting_sources": [],
            "excluded_sources": [],
            "diagnostics": self.diagnostics,
        }


def intent_result() -> QueryIntentResult:
    return QueryIntentResult(
        intent=QueryIntent.GENERAL_PROJECT_QUESTION,
        confidence=0.9,
        is_project_related=True,
        labels=["test"],
    )


def guard_result(decision: GuardDecision, intent: QueryIntentResult, message: str | None = None) -> ProjectGuardResult:
    return ProjectGuardResult(
        decision=decision,
        reason="test_reason",
        message=message,
        query_intent=intent,
    )


def search_result() -> SearchResult:
    return SearchResult(
        source_id="SRC-001",
        text="Тестовый проектный фрагмент",
        score=1.0,
        vector_score=None,
        bm25_score=1.0,
        metadata={"chunk_id": "chunk-1", "relative_path": "doc.md", "document_type": "ФТТ"},
        matched_by=["bm25"],
    )


def service_with_guard(guard_decision: GuardDecision):
    intent = intent_result()
    guard = MagicMock()
    guard.evaluate.return_value = guard_result(guard_decision, intent, "guard message")
    return SearchService(config={"paths": {}}, guard=guard, work_root=Path.cwd()), intent, guard


def test_refused_query_does_not_call_retrieval() -> None:
    service, intent, guard = service_with_guard(GuardDecision.REFUSE)

    with patch("asu_june_bot.search.service.classify_query_intent", return_value=intent), \
         patch("asu_june_bot.search.service.read_jsonl") as read_jsonl, \
         patch("asu_june_bot.search.service.build_hybrid_retriever") as build_retriever:
        response = service.search(SearchRequest(query="Какая погода завтра?"))

    assert response.status == "refused"
    assert response.results == []
    assert response.context["primary_sources"] == []
    assert response.to_dict()["diagnostics"]["search_service"]["retrieval_called"] is False
    guard.evaluate.assert_called_once()
    read_jsonl.assert_not_called()
    build_retriever.assert_not_called()


def test_clarify_query_does_not_call_retrieval() -> None:
    service, intent, _guard = service_with_guard(GuardDecision.CLARIFY)

    with patch("asu_june_bot.search.service.classify_query_intent", return_value=intent), \
         patch("asu_june_bot.search.service.read_jsonl") as read_jsonl, \
         patch("asu_june_bot.search.service.build_hybrid_retriever") as build_retriever:
        response = service.search(SearchRequest(query="Расскажи подробнее"))

    assert response.status == "clarify"
    assert response.results == []
    assert response.to_dict()["diagnostics"]["search_service"]["retrieval_called"] is False
    read_jsonl.assert_not_called()
    build_retriever.assert_not_called()


def test_allowed_query_calls_retrieval_rerank_and_context() -> None:
    service, intent, _guard = service_with_guard(GuardDecision.ALLOW)
    raw_result = search_result()
    retriever = MagicMock()
    retriever.search.return_value = [raw_result]
    retriever.last_warnings = []
    service.post_reranker = MagicMock()
    service.post_reranker.rerank.return_value = RerankResult(results=[raw_result], excluded=[], diagnostics={"reranker": "fake"})
    service.context_builder = MagicMock()
    service.context_builder.build.return_value = FakeBuiltContext()

    with patch("asu_june_bot.search.service.classify_query_intent", return_value=intent), \
         patch("asu_june_bot.search.service.resolve_work_path", side_effect=lambda _cfg, p: Path(p)), \
         patch("asu_june_bot.search.service.read_jsonl", return_value=[{"chunk_id": "chunk-1"}]) as read_jsonl, \
         patch("asu_june_bot.search.service.build_hybrid_retriever", return_value=retriever) as build_retriever:
        response = service.search(SearchRequest(query="СоИ AD как происходит авторизация пользователей?", mode="bm25", top_k=3))

    assert response.status == "ok"
    assert response.results[0]["source_id"] == "SRC-001"
    assert response.context["primary_sources"][0]["source_id"] == "SRC-001"
    assert response.to_dict()["diagnostics"]["search_service"]["retrieval_called"] is True
    read_jsonl.assert_called_once()
    build_retriever.assert_called_once()
    retriever.search.assert_called_once()
    service.post_reranker.rerank.assert_called_once()
    service.context_builder.build.assert_called_once()


def test_no_guard_forces_retrieval_even_when_guard_refuses() -> None:
    service, intent, _guard = service_with_guard(GuardDecision.REFUSE)
    raw_result = search_result()
    retriever = MagicMock()
    retriever.search.return_value = [raw_result]
    retriever.last_warnings = []
    service.post_reranker = MagicMock()
    service.post_reranker.rerank.return_value = RerankResult(results=[raw_result], excluded=[], diagnostics={"reranker": "fake"})
    service.context_builder = MagicMock()
    service.context_builder.build.return_value = FakeBuiltContext()

    with patch("asu_june_bot.search.service.classify_query_intent", return_value=intent), \
         patch("asu_june_bot.search.service.resolve_work_path", side_effect=lambda _cfg, p: Path(p)), \
         patch("asu_june_bot.search.service.read_jsonl", return_value=[{"chunk_id": "chunk-1"}]), \
         patch("asu_june_bot.search.service.build_hybrid_retriever", return_value=retriever):
        response = service.search(SearchRequest(query="Какая погода?", mode="bm25", top_k=3, no_guard=True))

    assert response.status == "ok"
    assert response.to_dict()["diagnostics"]["search_service"]["retrieval_called"] is True
    retriever.search.assert_called_once()
