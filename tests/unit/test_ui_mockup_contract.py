from __future__ import annotations

import re
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROTOTYPE = ROOT / "docs" / "ui-prototype" / "meetingagent-v2.html"
PROTOTYPE_CSS = ROOT / "docs" / "ui-prototype" / "meetingagent-v2.css"
PROTOTYPE_JS = ROOT / "docs" / "ui-prototype" / "meetingagent-v2.js"
DOC_EN = ROOT / "docs" / "en" / "ui_interaction_model.md"
DOC_RU = ROOT / "docs" / "ru" / "ui_interaction_model.md"
SCREENSHOTS = ROOT / "docs" / "assets" / "ui-mockups"


def _png_size(path: Path) -> tuple[int, int]:
    raw = path.read_bytes()[:24]
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", raw[16:24])


def test_mockup_has_all_target_surfaces_and_product_boundary() -> None:
    html = PROTOTYPE.read_text(encoding="utf-8")

    for screen in ("registry", "create", "processing", "workspace"):
        assert f'data-screen="{screen}"' in html
        assert f'data-screen-link="{screen}"' in html
    assert 'data-create-mode="upload"' in html
    assert 'data-create-mode="live"' in html
    assert 'href="/ui"' in html
    assert "Project Knowledge Bot" in html


def test_mockup_is_csp_safe_and_has_external_assets() -> None:
    html = PROTOTYPE.read_text(encoding="utf-8")

    assert not re.search(r"\s(?:on[a-z]+|style)=", html, re.IGNORECASE)
    assert '<script src="meetingagent-v2.js" defer></script>' in html
    assert '<link rel="stylesheet" href="meetingagent-v2.css" />' in html
    assert "<script>" not in html
    assert "<style" not in html


def test_mockup_has_keyboard_focus_and_role_contract() -> None:
    html = PROTOTYPE.read_text(encoding="utf-8")
    css = PROTOTYPE_CSS.read_text(encoding="utf-8")
    js = PROTOTYPE_JS.read_text(encoding="utf-8")

    assert 'class="skip-link"' in html
    assert ":focus-visible" in css
    assert ".skip-link:focus" in css
    assert "ArrowDown" in js and "ArrowUp" in js
    assert 'data-min-role="editor"' in html
    assert 'data-min-role="admin"' in html
    assert "viewer" in js and "editor" in js and "admin" in js


def test_mockup_has_narrow_screen_layout_contract() -> None:
    css = PROTOTYPE_CSS.read_text(encoding="utf-8")
    html = PROTOTYPE.read_text(encoding="utf-8")

    assert "@media (max-width: 700px)" in css
    assert ".mobile-nav" in css
    assert 'class="mobile-nav"' in html
    assert "min-height: 42px" in css
    assert "grid-template-columns: 88px minmax(0, 1fr)" in css


def test_ui_docs_cover_all_user_facing_api_families() -> None:
    required = (
        "/auth/me",
        "/auth/local/login",
        "/auth/csrf",
        "/meetings/ingest",
        "/meetings/live",
        "pipeline/readiness",
        "/jobs/{job_id}",
        "/live/preflight",
        "/live/sessions",
        "/live/timeline",
        "/live/refinement",
        "/search",
        "/chat",
    )

    for path in (DOC_EN, DOC_RU):
        text = path.read_text(encoding="utf-8")
        for marker in required:
            assert marker in text, f"{path.name} does not document {marker}"
        assert all(code in text for code in ("401", "403", "409", "422", "429", "503"))


def test_desktop_and_narrow_screenshots_exist_for_each_surface() -> None:
    stems = ("registry", "create-upload", "create-live", "processing", "workspace")

    for stem in stems:
        desktop = SCREENSHOTS / f"{stem}-desktop.png"
        narrow = SCREENSHOTS / f"{stem}-narrow.png"
        assert desktop.stat().st_size > 10_000
        assert narrow.stat().st_size > 10_000
        expected_desktop = (1440, 900) if stem == "create-live" else (1440, 1000)
        assert _png_size(desktop) == expected_desktop
        assert _png_size(narrow) == (390, 844)


def test_public_mockups_contain_no_local_absolute_paths() -> None:
    public_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (PROTOTYPE, PROTOTYPE_CSS, PROTOTYPE_JS, DOC_EN, DOC_RU)
    )

    assert "C:\\Users\\" not in public_text
    assert "/Users/" not in public_text
    assert "file://" not in public_text.lower()
