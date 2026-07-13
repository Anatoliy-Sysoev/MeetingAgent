from __future__ import annotations

from html import escape

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from asu_june_bot.meetings.service import _safe_meeting_id

from .ui_assets import render_ui_template


router = APIRouter(tags=["workspace"])


@router.get("/meetings/{meeting_id}/workspace", response_class=HTMLResponse)
def meeting_workspace(meeting_id: str, request: Request) -> HTMLResponse:  # noqa: ARG001
    """Serve the public shell; API calls enforce auth and hide card existence."""
    if not _safe_meeting_id(meeting_id):
        raise HTTPException(status_code=404, detail="Meeting not found")
    html = render_ui_template(
        "workspace.html",
        replacements={"__MEETING_ID__": escape(meeting_id, quote=True)},
    )
    return HTMLResponse(content=html)
