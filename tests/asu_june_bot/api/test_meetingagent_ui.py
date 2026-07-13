from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from asu_june_bot.api.app import create_app
from asu_june_bot.api.ui_assets import load_ui_asset, load_ui_template


@pytest.fixture(scope="module")
def html() -> str:
    return load_ui_template("meetingagent.html") + load_ui_asset("meetingagent.js")


def test_meetingagent_route_returns_main_ui() -> None:
    client = TestClient(create_app(), raise_server_exceptions=False)
    resp = client.get("/MeetingAgent")
    assert resp.status_code == 200
    assert "MeetingAgent" in resp.text
    assert "Новая запись" in resp.text


def test_meetingagent_ui_links_to_june_bot(html: str) -> None:
    assert 'href="/ui"' in html
    assert "Джун бот" in html


def test_meetingagent_ui_lists_and_uploads_meetings(html: str) -> None:
    assert 'apiFetch("/meetings?limit=200")' in html
    assert 'apiFetch("/meetings/ingest"' in html
    assert 'name="file"' in html
    assert 'id="uploadForm"' in html


def test_meetingagent_ui_creates_live_meeting_and_opens_workspace(html: str) -> None:
    assert 'id="liveMeetingForm"' in html
    assert 'apiFetch("/meetings/live"' in html
    assert '"X-CSRF-Token": state.csrf' in html
    assert "window.location.assign(workspaceUrl)" in html
    assert 'id="liveMeetingLanguage"' in html


def test_meetingagent_ui_starts_pipeline_profiles(html: str) -> None:
    assert "/jobs/pipeline" in html
    assert "transcript_only" in html
    assert '"full"' in html
    assert "large-v3-turbo" in html
    assert 'id="asrEngine"' in html
    assert 'value="faster-whisper"' in html
    assert 'value="gigaam"' in html
    assert "asr_engine: selectedAsrEngine()" in html


def test_meetingagent_ui_uses_csrf_for_mutating_requests(html: str) -> None:
    for endpoint in ("/meetings/ingest", "/meetings/live", "/jobs/pipeline"):
        idx = html.index(endpoint)
        context = html[max(0, idx - 850): idx + 500]
        assert "X-CSRF-Token" in context, context
    assert "getCsrfToken()" in html


def test_meetingagent_ui_has_no_inline_handlers(html: str) -> None:
    assert not re.search(r"<[^>]+\son(click|change|submit|keydown|input)\s*=", html)


def test_meetingagent_ui_uses_dom_api_for_dynamic_content(html: str) -> None:
    assert "replaceChildren" in html
    assert "textContent" in html
    assert ".innerHTML" not in html
    assert "innerHTML" not in html


def test_meetingagent_ui_does_not_use_browser_storage(html: str) -> None:
    assert "localStorage" not in html
    assert "sessionStorage" not in html


def test_meetingagent_ui_renders_bounded_machine_conflict_message(html: str) -> None:
    assert 'typeof data.detail.message === "string"' in html
    assert "data.detail.message.slice(0, 240)" in html
