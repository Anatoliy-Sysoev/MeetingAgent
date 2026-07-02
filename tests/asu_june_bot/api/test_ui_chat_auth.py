"""Tests for UI chat auth integration (MA-UI-CHAT-AUTH, #107).

The UI page must:
- expose an auth status badge and a login panel;
- send X-CSRF-Token on POST /chat (cookie-session callers);
- obtain the CSRF token via GET /auth/csrf (never from localStorage);
- show a friendly message on 401/403 instead of raw JSON;
- keep DOM/CSP hygiene: no inline event handlers, no localStorage/sessionStorage.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.api.app import create_app  # noqa: E402


@pytest.fixture(scope="module")
def ui_html() -> str:
    client = TestClient(create_app(), raise_server_exceptions=False)
    resp = client.get("/ui")
    assert resp.status_code == 200
    return resp.text


# ---------------------------------------------------------------------------
# Auth UI elements
# ---------------------------------------------------------------------------

def test_ui_has_auth_status_badge(ui_html: str) -> None:
    assert 'id="authStatus"' in ui_html


def test_ui_has_login_panel(ui_html: str) -> None:
    assert 'id="authPanel"' in ui_html
    assert 'id="loginEmail"' in ui_html
    assert 'id="loginPassword"' in ui_html
    assert 'id="loginSubmit"' in ui_html


def test_login_panel_hidden_by_default(ui_html: str) -> None:
    m = re.search(r'<div class="panel auth-panel" id="authPanel"([^>]*)>', ui_html)
    assert m is not None
    assert "hidden" in m.group(1)


def test_password_input_uses_password_type(ui_html: str) -> None:
    m = re.search(r'<input[^>]*id="loginPassword"[^>]*>', ui_html) or re.search(
        r'<input[^>]*type="password"[^>]*id="loginPassword"[^>]*>', ui_html
    )
    assert m is not None
    assert 'type="password"' in m.group(0)


# ---------------------------------------------------------------------------
# Auth JS wiring
# ---------------------------------------------------------------------------

def test_js_calls_auth_me(ui_html: str) -> None:
    assert "fetch('/auth/me')" in ui_html


def test_js_calls_local_login(ui_html: str) -> None:
    assert "fetch('/auth/local/login'" in ui_html


def test_chat_request_sends_csrf_header(ui_html: str) -> None:
    # ask() must obtain a token and attach X-CSRF-Token to POST /chat.
    assert "X-CSRF-Token" in ui_html
    ask_block = ui_html[ui_html.index("async function ask()"):]
    ask_block = ask_block[: ask_block.index("// --------------- Review tab")]
    assert "getCsrfToken()" in ask_block
    assert "X-CSRF-Token" in ask_block


def test_csrf_token_fetched_from_endpoint(ui_html: str) -> None:
    assert "fetch('/auth/csrf')" in ui_html


def test_unauthorized_chat_shows_friendly_error(ui_html: str) -> None:
    assert "войдите в систему" in ui_html


def test_throttled_chat_shows_friendly_error(ui_html: str) -> None:
    assert "Слишком много запросов" in ui_html


def test_error_body_parsed_with_safe_json(ui_html: str) -> None:
    # Non-JSON responses (e.g. reverse proxy HTML) must not break the error path.
    assert "async function safeJson(resp)" in ui_html
    ask_block = ui_html[ui_html.index("async function ask()"):]
    ask_block = ask_block[: ask_block.index("// --------------- Review tab")]
    # status is checked before any body parsing; no unguarded response.json()
    assert ask_block.index("response.ok") < ask_block.index("safeJson(response)")
    assert "await response.json()" not in ask_block


def test_login_handlers_use_add_event_listener(ui_html: str) -> None:
    assert "loginSubmit.addEventListener('click', doLogin)" in ui_html


# ---------------------------------------------------------------------------
# DOM/CSP hygiene
# ---------------------------------------------------------------------------

def test_no_inline_event_handlers(ui_html: str) -> None:
    assert not re.search(r"<[^>]+\son(click|change|submit|keydown|input)\s*=", ui_html)


def test_no_web_storage_usage(ui_html: str) -> None:
    assert "localStorage" not in ui_html
    assert "sessionStorage" not in ui_html


def test_no_secrets_in_html(ui_html: str) -> None:
    assert "MEETINGAGENT_API_TOKEN" not in ui_html
    assert "Bearer " not in ui_html
