from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from asu_june_bot.core.limits import MAX_QUERY_CHARS

from .ui_assets import render_ui_template


router = APIRouter(tags=["ui"])


def _bot_html() -> str:
    return render_ui_template(
        "bot.html",
        replacements={"__MAX_QUERY_CHARS__": str(MAX_QUERY_CHARS)},
    )


@router.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(_bot_html())


@router.get("/ui", response_class=HTMLResponse)
def ui() -> HTMLResponse:
    return HTMLResponse(_bot_html())
