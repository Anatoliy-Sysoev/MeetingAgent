from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from asu_june_bot.api.auth import require_admin_user_permission
from asu_june_bot.auth.models import Principal

from .ui_assets import render_ui_template


router = APIRouter(tags=["admin-ui"])
require_admin_page = require_admin_user_permission("users.manage")


@router.get("/admin", response_class=HTMLResponse, include_in_schema=False)
def admin_console(
    _principal: Annotated[Principal, Depends(require_admin_page)],
) -> HTMLResponse:
    return HTMLResponse(render_ui_template("admin.html"))
