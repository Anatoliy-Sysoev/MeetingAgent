from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.api.app import create_app  # noqa: E402
from asu_june_bot.core.limits import MAX_QUERY_CHARS  # noqa: E402
from asu_june_bot.search.models import SearchResponse  # noqa: E402


class FakeHealthService:
    def check(self) -> dict:
        return {"status": "ok"}


class FakeSearchService:
    def __init__(self) -> None:
        self.last_request = None

    def search(self, request):
        self.last_request = request
        if "погода" in request.query.lower():
            return SearchResponse(
                {
                    "status": "refused",
                    "query": request.query,
                    "mode": request.mode,
                    "answer": "refused",
                    "guard": {"decision": "refuse", "allowed": False},
                    "context": {"primary_sources": [], "supporting_sources": [], "excluded_sources": [], "diagnostics": {}},
                    "results": [],
                    "diagnostics": {"search_service": {"retrieval_called": False}},
                }
            )
        return SearchResponse(
            {
                "status": "ok",
                "query": request.query,
                "mode": request.mode,
                "guard": {"decision": "allow", "allowed": True},
                "context": {
                    "primary_sources": [{"source_id": "SRC-001"}],
                    "supporting_sources": [],
                    "excluded_sources": [],
                    "diagnostics": {},
                },
                "results": [{"source_id": "SRC-001"}],
                "diagnostics": {"search_service": {"retrieval_called": True}},
            }
        )


@dataclass(slots=True)
class FakeState:
    health_service: FakeHealthService
    search_service: FakeSearchService


def build_client():
    app = create_app()
    client = TestClient(app)
    client.__enter__()
    fake_search = FakeSearchService()
    app.state.asu_june_bot = FakeState(health_service=FakeHealthService(), search_service=fake_search)
    return client, fake_search


def test_search_endpoint_project_query() -> None:
    client, fake_search = build_client()
    try:
        response = client.post(
            "/search",
            json={"query": "СоИ AD как происходит авторизация пользователей?", "mode": "hybrid", "top_k": 8},
            headers={"X-Request-Id": "search-project"},
        )
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 200
    assert response.headers["X-Request-Id"] == "search-project"
    data = response.json()
    assert data["status"] == "ok"
    assert data["diagnostics"]["search_service"]["retrieval_called"] is True
    assert data["context"]["primary_sources"]
    assert data["results"]
    assert data["diagnostics"]["request_id"] == "search-project"
    assert fake_search.last_request.query == "СоИ AD как происходит авторизация пользователей?"
    assert fake_search.last_request.mode == "hybrid"
    assert fake_search.last_request.top_k == 8
    assert fake_search.last_request.no_guard is False


def test_search_endpoint_refused_query() -> None:
    client, _fake_search = build_client()
    try:
        response = client.post("/search", json={"query": "Какая погода завтра в Москве?", "mode": "hybrid", "top_k": 8})
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "refused"
    assert data["diagnostics"]["search_service"]["retrieval_called"] is False
    assert data["context"]["primary_sources"] == []
    assert data["results"] == []


def test_search_endpoint_rejects_public_no_guard_bypass() -> None:
    client, _fake_search = build_client()
    try:
        response = client.post("/search", json={"query": "Какая погода завтра в Москве?", "no_guard": True})
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 422
    data = response.json()
    assert data["status"] == "error"
    assert data["error_code"] == "validation_error"


def test_search_endpoint_validation_error_on_unknown_field() -> None:
    client, _fake_search = build_client()
    try:
        response = client.post("/search", json={"query": "test", "unknown": "field"})
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 422
    data = response.json()
    assert data["status"] == "error"
    assert data["error_code"] == "validation_error"


def test_search_endpoint_rejects_too_long_query() -> None:
    client, _fake_search = build_client()
    try:
        response = client.post("/search", json={"query": "x" * (MAX_QUERY_CHARS + 1)})
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 422
    data = response.json()
    assert data["status"] == "error"
    assert data["error_code"] == "validation_error"
