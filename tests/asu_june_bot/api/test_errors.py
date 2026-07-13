from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, model_validator

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


def test_sanitize_redacts_access_token_substring() -> None:
    errors = [{"loc": ("body", "access_token"), "type": "string_too_short", "msg": "String too short", "input": "x"}]
    result = _sanitize_validation_errors(errors)
    assert result[0]["msg"] == "Field value redacted for security"


def test_sanitize_redacts_csrf_token_substring() -> None:
    errors = [{"loc": ("body", "csrf_token"), "type": "missing", "msg": "Field required", "input": "bad"}]
    result = _sanitize_validation_errors(errors)
    assert result[0]["msg"] == "Field value redacted for security"


def test_sanitize_redacts_new_password_substring() -> None:
    errors = [{"loc": ("body", "new_password"), "type": "string_too_short", "msg": "min length 8", "input": "short"}]
    result = _sanitize_validation_errors(errors)
    assert result[0]["msg"] == "Field value redacted for security"


def test_sanitize_redacts_bootstrap_secret_substring() -> None:
    errors = [{"loc": ("body", "bootstrap_secret"), "type": "missing", "msg": "Field required", "input": "x"}]
    result = _sanitize_validation_errors(errors)
    assert result[0]["msg"] == "Field value redacted for security"


def test_sanitize_redacts_nested_sensitive_field() -> None:
    errors = [{"loc": ("body", "auth", "api_key"), "type": "missing", "msg": "Field required", "input": None}]
    result = _sanitize_validation_errors(errors)
    assert result[0]["msg"] == "Field value redacted for security"


def test_sanitize_ctx_recursively_drops_exceptions_paths_and_sensitive_values() -> None:
    nested: dict[str, object] = {
        "limits": [1, 2, {"note": "safe", "token": "TOP-SECRET"}],
        "error": ValueError("TOP-SECRET at C:/Users/private/.env"),
        "source_path": "C:/Users/private/.env",
        "not_finite": float("nan"),
        "opaque": object(),
    }
    nested["cycle"] = nested
    errors = [
        {
            "loc": ("body",),
            "type": "value_error",
            "msg": "Value error, TOP-SECRET at C:/Users/private/.env",
            "ctx": {"nested": nested, "other": "keep"},
        }
    ]

    result = _sanitize_validation_errors(errors)
    serialized = json.dumps(result, allow_nan=False)

    assert result[0]["msg"] == "Value does not satisfy validation rules"
    assert result[0]["ctx"]["other"] == "keep"
    assert result[0]["ctx"]["nested"]["limits"] == [1, 2, {"note": "safe"}]
    assert "TOP-SECRET" not in serialized
    assert "Users/private" not in serialized
    assert "source_path" not in serialized
    assert "not_finite" not in serialized
    assert "opaque" not in serialized
    assert "cycle" not in serialized


def test_sanitize_ctx_bounds_nested_collections() -> None:
    errors = [
        {
            "loc": ("body", "items"),
            "type": "too_many",
            "msg": "Too many values",
            "ctx": {"items": list(range(100))},
        }
    ]

    result = _sanitize_validation_errors(errors)

    assert result[0]["ctx"]["items"] == list(range(32))


def test_safe_builtin_validation_context_and_message_remain_compatible() -> None:
    errors = [
        {
            "loc": ("body", "count"),
            "type": "greater_than",
            "msg": "Input should be greater than 3",
            "ctx": {"gt": 3},
        }
    ]

    result = _sanitize_validation_errors(errors)

    assert result == [
        {
            "loc": ("body", "count"),
            "type": "greater_than",
            "msg": "Input should be greater than 3",
            "ctx": {"gt": 3},
        }
    ]


def test_sensitive_custom_ctx_cannot_leak_through_formatted_message() -> None:
    errors = [
        {
            "loc": ("body", "profile"),
            "type": "custom_policy_error",
            "msg": "Policy rejected TOP-SECRET-CUSTOM-VALUE",
            "ctx": {
                "metadata": {
                    "api_key": "TOP-SECRET-CUSTOM-VALUE",
                    "policy": "public-policy",
                }
            },
        }
    ]

    result = _sanitize_validation_errors(errors)
    serialized = json.dumps(result)

    assert result[0]["msg"] == "Value does not satisfy validation rules"
    assert result[0]["ctx"] == {"metadata": {"policy": "public-policy"}}
    assert "TOP-SECRET-CUSTOM-VALUE" not in serialized


# ---------------------------------------------------------------------------
# Integration: validation error handler via TestClient
# ---------------------------------------------------------------------------

class _LoginBody(BaseModel):
    username: str
    password: str


class _ModelValidatorSecretBody(BaseModel):
    secret: str

    @model_validator(mode="after")
    def reject_secret(self) -> "_ModelValidatorSecretBody":
        raise ValueError(f"rejected {self.secret} at C:/Users/private/.env")


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


def test_model_validator_value_error_returns_secret_free_422() -> None:
    app = FastAPI()
    app.middleware("http")(request_context_middleware)
    register_error_handlers(app)

    @app.post("/model-validator")
    def model_validator_route(body: _ModelValidatorSecretBody) -> dict:
        return {}

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/model-validator",
        json={"secret": "TOP-SECRET-MODEL-VALUE"},
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["error_code"] == "validation_error"
    assert payload["details"][0]["msg"] == "Value does not satisfy validation rules"
    assert "input" not in payload["details"][0]
    assert "error" not in payload["details"][0].get("ctx", {})
    assert "TOP-SECRET-MODEL-VALUE" not in response.text
    assert "Users/private" not in response.text
