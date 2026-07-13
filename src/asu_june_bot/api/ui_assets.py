from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Mapping


UI_ROOT = Path(__file__).resolve().with_name("ui")
UI_ASSETS_V1_DIR = UI_ROOT / "assets" / "v1"
UI_TEMPLATES_DIR = UI_ROOT / "templates"
MAX_UI_TEMPLATE_BYTES = 512 * 1024
MAX_UI_ASSET_BYTES = 1024 * 1024

_TEMPLATES = MappingProxyType(
    {
        "bot.html": UI_TEMPLATES_DIR / "bot.html",
        "admin.html": UI_TEMPLATES_DIR / "admin.html",
        "meetingagent.html": UI_TEMPLATES_DIR / "meetingagent.html",
        "workspace.html": UI_TEMPLATES_DIR / "workspace.html",
    }
)
_ASSETS = MappingProxyType(
    {
        name: UI_ASSETS_V1_DIR / name
        for name in (
            "bot.css",
            "bot.js",
            "admin.css",
            "admin.js",
            "meetingagent.css",
            "meetingagent.js",
            "workspace.css",
            "workspace.js",
        )
    }
)


@lru_cache(maxsize=len(_TEMPLATES))
def load_ui_template(name: str) -> str:
    path = _TEMPLATES.get(name)
    if path is None:
        raise ValueError(f"unknown UI template: {name}")
    raw = path.read_bytes()
    if len(raw) > MAX_UI_TEMPLATE_BYTES:
        raise ValueError(f"UI template is too large: {name}")
    return raw.decode("utf-8")


@lru_cache(maxsize=len(_ASSETS))
def load_ui_asset(name: str) -> str:
    path = _ASSETS.get(name)
    if path is None:
        raise ValueError(f"unknown UI asset: {name}")
    raw = path.read_bytes()
    if len(raw) > MAX_UI_ASSET_BYTES:
        raise ValueError(f"UI asset is too large: {name}")
    return raw.decode("utf-8")


def render_ui_template(
    name: str,
    *,
    replacements: Mapping[str, str] | None = None,
) -> str:
    rendered = load_ui_template(name)
    for marker, value in (replacements or {}).items():
        if not marker.startswith("__") or not marker.endswith("__"):
            raise ValueError("UI replacement markers must be explicit placeholders")
        rendered = rendered.replace(marker, value)
    return rendered
