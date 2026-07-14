from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from .ui_assets import render_ui_template


router = APIRouter(tags=["meetingagent-ui"])


def _render_home(initial_section: str) -> HTMLResponse:
    return HTMLResponse(
        render_ui_template(
            "meetingagent.html",
            replacements={"__INITIAL_SECTION__": initial_section},
        )
    )


@router.get("/MeetingAgent", response_class=HTMLResponse)
async def meetingagent_home() -> HTMLResponse:
    return _render_home("meetings")


@router.get("/MeetingAgent/new", response_class=HTMLResponse)
async def meetingagent_new() -> HTMLResponse:
    return _render_home("new-meeting")


@router.get("/MeetingAgent/processing", response_class=HTMLResponse)
async def meetingagent_processing() -> HTMLResponse:
    return _render_home("operations")
