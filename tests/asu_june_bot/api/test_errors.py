from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.api.errors import _sanitize_validation_errors, register_error_handlers  # noqa: E402
from asu_june_bot.api.middleware import request_context_middleware  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_app_with_route(route_fn, path: str = "/submit", method: str = "POST") -> TestClient:
    app = FastAPI()
    app.middleware("http")(request_context_middleware)
    register_error_handlers(app)
    if method == "POST":
        app.post(path)(route_fn)
    else:
        app.get(path)(route_fn)
    return TestClient(app, raise_server_exceptions=False)


def test_unhandled_error_response_is_sanitized() -> None:
    app = FastAPI()
    app.middleware("http")(request_context_middleware)
    register_error_handlers(app)

    @app.get("/boom")
    def boom() -> dict:
        raise RuntimeError("secret local path C:/Users/local-user/Desktop/AI/MeetingAgent/.env")

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


# ---------------------------------------------------------------------------
# _sanitize_validation_errors unit tests
# ---------------------------------------------------------------------------

def test_sanitize_removes_input_field() -> None:
    errors = [{"loc": ("body", "username"), "type": "missing", "msg": "Field required", "input": {"username": None, "password": "hunter2"}}]
    result = _sanitize_validation_errors(errors)
    assert "input" not in result[0]


def test_sanitize_redacts_password_msg() -> None:
    errors = [{"loc": ("body", "password"), "type": "string_too_short", "msg": "String should have at least 8 characters", "input": "abc"}]
    result = _sanitize_validation_errors(errors)
    assert "input" not in result[0]
    assert result[0]["msg"] == "Field value redacted for security"


def test_sanitize_redacts_token_msg() -> None:
    errors = [{"loc": ("body", "token"), "type": "string_too_short", "msg": "String should have at least 32 characters", "input": "weak"}]
    result = _sanitize_validation_errors(errors)
    assert result[0]["msg"] == "Field value redacted for security"


def test_sanitize_preserves_safe_loc_msg() -> None:
    errors = [{"loc": ("body", "username"), "type": "missing", "msg": "Field required"}]
    result = _sanitize_validation_errors(errors)
    assert result[0]["msg"] == "Field required"
    assert result[0]["loc"] == ("body", "username")
    assert result[0]["type"] == "missing"


def test_sanitize_strips_ctx_actual_given_pattern() -> None:
    errors = [{"loc": ("body", "count"), "type": "int_parsing", "msg": "bad int", "ctx": {"actual": "foo", "given": "bar", "other": "keep"}}]
    result = _sanitize_validation_errors(errors)
    assert "actual" not in result[0].get("ctx", {})
    assert "given" not in result[0].get("ctx", {})
    assert result[0]["ctx"]["other"] == "keep"


def test_sanitize_redacts_secret_field() -> None:
    errors = [{"loc": ("body", "secret"), "type": "missing", "msg": "Field required", "input": "my-secret"}]
    result = _sanitize_validation_errors(errors)
    assert result[0]["msg"] == "Field value redacted for security"
    assert "input" not in result[0]


# ---------------------------------------------------------------------------
# Integration: validation error handler via TestClient
# ---------------------------------------------------------------------------

class _LoginBody(BaseModel):
    username: str
    password: str


def test_validation_error_does_not_expose_password_input() -> None:
    app = FastAPI()
    app.middleware("http")(request_context_middleware)
    register_error_handlers(app)

    @app.post("/login")
    def login(body: _LoginBody) -> dict:
        return {}

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/login", json={"username": "alice", "password": 12345})
    assert resp.status_code == 422
    body = resp.json()
    assert "details" in body
    for err in body["details"]:
        assert "input" not in err
    text = resp.text
    assert "12345" not in text


def test_validation_error_does_not_expose_token_input() -> None:
    class _TokenBody(BaseModel):
        token: str

    app = FastAPI()
    app.middleware("http")(request_context_middleware)
    register_error_handlers(app)

    @app.post("/auth")
    def auth_route(body: _TokenBody) -> dict:
        return {}

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/auth", json={"token": 9999})
    assert resp.status_code == 422
    body = resp.json()
    for err in body["details"]:
        assert "input" not in err
    assert "9999" not in resp.text


def test_validation_error_omits_pydantic_input_field() -> None:
    class _Body(BaseModel):
        name: str

    app = FastAPI()
    app.middleware("http")(request_context_middleware)
    register_error_handlers(app)

    @app.post("/items")
    def items(body: _Body) -> dict:
        return {}

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/items", json={})
    assert resp.status_code == 422
    for err in resp.json()["details"]:
        assert "input" not in err
