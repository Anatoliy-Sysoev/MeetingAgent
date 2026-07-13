from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from .ui_assets import render_ui_template


router = APIRouter(tags=["meetingagent-ui"])


@router.get("/MeetingAgent", response_class=HTMLResponse)
async def meetingagent_home() -> HTMLResponse:
    return HTMLResponse(render_ui_template("meetingagent.html"))
