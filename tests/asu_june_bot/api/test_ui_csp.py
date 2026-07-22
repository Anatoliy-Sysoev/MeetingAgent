"""Security contract for the versioned product UI assets and templates."""
from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.api.app import create_app  # noqa: E402
from asu_june_bot.api.middleware import CONTENT_SECURITY_POLICY  # noqa: E402
from asu_june_bot.api.ui_assets import (  # noqa: E402
    load_ui_asset,
    load_ui_template,
    render_ui_template,
)


PRODUCT_PAGES = (
    "/",
    "/ui",
    "/MeetingAgent",
    "/MeetingAgent/new",
    "/MeetingAgent/processing",
    "/meetings/2026-07-12__csp-test/workspace",
)
ASSET_NAMES = (
    "bot.css",
    "bot.js",
    "admin.css",
    "admin.js",
    "meetingagent.css",
    "meetingagent.js",
    "workspace.css",
    "workspace.js",
)
ASSET_PATHS = (
    *(f"/assets/v1/{name}" for name in ("bot.css", "bot.js", "admin.css", "admin.js")),
    *(f"/assets/v3/{name}" for name in ("meetingagent.css", "meetingagent.js")),
    *(f"/assets/v5/{name}" for name in ("workspace.css", "workspace.js")),
)


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.mark.parametrize("path", PRODUCT_PAGES)
def test_product_page_has_restrictive_csp(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 200
    policy = response.headers.get("content-security-policy")
    assert policy == CONTENT_SECURITY_POLICY
    assert "'unsafe-inline'" not in policy
    assert "'unsafe-eval'" not in policy
    assert "default-src 'none'" in policy
    assert "script-src 'self'" in policy
    assert "style-src 'self'" in policy
    assert "frame-ancestors 'none'" in policy
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_admin_page_has_restrictive_csp_for_authenticated_admin() -> None:
    from asu_june_bot.api.routes_admin_ui import require_admin_page

    app = create_app()
    app.dependency_overrides[require_admin_page] = lambda: object()
    admin_client = TestClient(app, raise_server_exceptions=False)
    response = admin_client.get("/admin")
    assert response.status_code == 200
    assert response.headers["content-security-policy"] == CONTENT_SECURITY_POLICY
    assert "'unsafe-inline'" not in response.headers["content-security-policy"]


def test_admin_page_contains_only_external_scripts_and_styles() -> None:
    from asu_june_bot.api.routes_admin_ui import require_admin_page

    app = create_app()
    app.dependency_overrides[require_admin_page] = lambda: object()
    admin_client = TestClient(app, raise_server_exceptions=False)
    html = admin_client.get("/admin").text
    assert "<style" not in html.lower()
    assert not re.search(r"<script(?![^>]*\ssrc=)[^>]*>", html, re.IGNORECASE)
    assert not re.search(r"\sstyle\s*=", html, re.IGNORECASE)
    assert not re.search(r"\son[a-z]+\s*=", html, re.IGNORECASE)


@pytest.mark.parametrize("path", PRODUCT_PAGES)
def test_product_page_contains_only_external_scripts_and_styles(
    client: TestClient,
    path: str,
) -> None:
    html = client.get(path).text
    assert "<style" not in html.lower()
    assert not re.search(r"<script(?![^>]*\ssrc=)[^>]*>", html, re.IGNORECASE)
    assert not re.search(r"\sstyle\s*=", html, re.IGNORECASE)
    assert not re.search(r"\son[a-z]+\s*=", html, re.IGNORECASE)
    assert re.search(r'<link[^>]+href="/assets/v[12345]/[^\"]+\.css"', html)
    assert re.search(r'<script[^>]+src="/assets/v[12345]/[^\"]+\.js"[^>]*></script>', html)


@pytest.mark.parametrize("path", ASSET_PATHS)
def test_versioned_asset_is_servable_and_immutable(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 200
    assert response.content
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert response.headers["x-content-type-options"] == "nosniff"
    expected_type = "javascript" if path.endswith(".js") else "css"
    assert expected_type in response.headers["content-type"]


def test_unknown_asset_is_not_servable(client: TestClient) -> None:
    response = client.get("/assets/v1/not-allowlisted.js")
    assert response.status_code == 404
    response = client.get("/assets/v2/not-allowlisted.js")
    assert response.status_code == 404
    response = client.get("/assets/v3/not-allowlisted.js")
    assert response.status_code == 404
    response = client.get("/assets/v4/not-allowlisted.js")
    assert response.status_code == 404
    response = client.get("/assets/v5/not-allowlisted.js")
    assert response.status_code == 404


def test_api_docs_are_not_broken_by_product_csp(client: TestClient) -> None:
    response = client.get("/docs")
    assert response.status_code == 200
    assert "content-security-policy" not in response.headers


def test_template_placeholders_are_resolved_in_responses(client: TestClient) -> None:
    bot = client.get("/ui").text
    meetingagent = client.get("/MeetingAgent/new").text
    workspace = client.get("/meetings/2026-07-12__csp-test/workspace").text
    assert "__MAX_QUERY_CHARS__" not in bot
    assert "__INITIAL_SECTION__" not in meetingagent
    assert 'data-initial-section="new-meeting"' in meetingagent
    assert "__MEETING_ID__" not in workspace
    assert 'data-meeting-id="2026-07-12__csp-test"' in workspace


@pytest.mark.parametrize("name", ASSET_NAMES)
def test_javascript_and_css_assets_have_no_inline_dom_escape_hatches(name: str) -> None:
    content = load_ui_asset(name)
    assert "localStorage" not in content
    assert "sessionStorage" not in content
    if name.endswith(".js"):
        assert "innerHTML" not in content
        assert not re.search(r"\.style(?:\.|\s*=)", content)
        assert "eval(" not in content
        assert "new Function" not in content


@pytest.mark.parametrize(
    ("loader", "name"),
    (
        (load_ui_template, "../templates/bot.html"),
        (load_ui_template, "missing.html"),
        (load_ui_asset, "../templates/bot.html"),
        (load_ui_asset, "missing.js"),
    ),
)
def test_ui_loader_rejects_unknown_or_traversal_names(loader, name: str) -> None:
    with pytest.raises(ValueError, match="unknown UI"):
        loader(name)


def test_template_renderer_rejects_implicit_replacement_marker() -> None:
    with pytest.raises(ValueError, match="explicit placeholders"):
        render_ui_template("bot.html", replacements={"MAX_QUERY_CHARS": "1"})


def test_ui_templates_and_assets_are_declared_as_wheel_package_data() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    patterns = set(config["tool"]["setuptools"]["package-data"]["meeting_agent.api"])
    assert patterns == {
        "ui/templates/*.html",
        "ui/assets/v1/*.css",
        "ui/assets/v1/*.js",
        "ui/assets/v2/*.css",
        "ui/assets/v2/*.js",
        "ui/assets/v3/*.css",
        "ui/assets/v3/*.js",
        "ui/assets/v4/*.css",
        "ui/assets/v4/*.js",
        "ui/assets/v5/*.css",
        "ui/assets/v5/*.js",
    }
