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


class FakeHealthService:
    def check(self) -> dict:
        return {
            "status": "ok",
            "service": "asu_june_bot",
            "corpus_ready": True,
            "bm25_ready": True,
            "vector_ready": True,
            "guard_v2_ready": True,
        }


class FakeSearchService:
    pass


@dataclass(slots=True)
class FakeState:
    health_service: FakeHealthService
    search_service: FakeSearchService


def test_health_endpoint_returns_payload_and_request_id_header() -> None:
    app = create_app()
    with TestClient(app) as client:
        app.state.asu_june_bot = FakeState(health_service=FakeHealthService(), search_service=FakeSearchService())
        response = client.get("/health", headers={"X-Request-Id": "test-request-id"})

    assert response.status_code == 200
    assert response.headers["X-Request-Id"] == "test-request-id"
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "asu_june_bot"
    assert data["bm25_ready"] is True
    assert data["vector_ready"] is True
    assert data["guard_v2_ready"] is True
