from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.api.errors import register_error_handlers  # noqa: E402
from asu_june_bot.api.middleware import request_context_middleware  # noqa: E402


def test_unhandled_error_response_is_sanitized() -> None:
    app = FastAPI()
    app.middleware("http")(request_context_middleware)
    register_error_handlers(app)

    @app.get("/boom")
    def boom() -> dict:
        raise RuntimeError("secret local path C:/Users/Сотрудник/Desktop/AI/MeetingAgent/.env")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/boom", headers={"X-Request-Id": "err-001"})

    assert response.status_code == 500
    data = response.json()
    assert data["status"] == "error"
    assert data["error_code"] == "internal_error"
    assert data["request_id"] == "err-001"
    assert data["error"] == "Внутренняя ошибка API. Передайте request_id для диагностики."
    assert "secret" not in response.text
    assert "MeetingAgent" not in response.text
    assert ".env" not in response.text
