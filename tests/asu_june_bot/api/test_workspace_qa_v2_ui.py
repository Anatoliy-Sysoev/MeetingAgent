"""Tests for Workspace Q&A v2 UI additions (MA-WORKSPACE-QA-V2-UI, #113)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.api.ui_assets import load_ui_asset, load_ui_template  # noqa: E402


@pytest.fixture(scope="module")
def html() -> str:
    return load_ui_template("workspace.html") + load_ui_asset("workspace.js")


def test_retrieval_mode_elements_present(html: str) -> None:
    assert 'id="qa-chat-mode"' in html
    assert 'id="qa-search-mode"' in html


def test_retrieval_mode_labels(html: str) -> None:
    assert 'qaModeLabel' in html
    assert 'поиск: семантический (vector)' in html
    assert 'поиск: лексический' in html
    # mode is set from the API field, not guessed
    assert 'qaModeLabel(data.retrieval_mode)' in html


def test_citation_label_preferred(html: str) -> None:
    # qaCiteLine prefers the backend citation_label "[00:12:34, Speaker]"
    assert 'src.citation_label' in html


def test_mode_cleared_before_request(html: str) -> None:
    assert 'setText("qa-chat-mode", "")' in html
    assert 'setText("qa-search-mode", "")' in html


def test_no_inline_event_handlers(html: str) -> None:
    assert not re.search(r"<[^>]+\son(click|change|submit|keydown|input)\s*=", html)


def test_no_web_storage(html: str) -> None:
    assert "localStorage" not in html
    assert "sessionStorage" not in html
