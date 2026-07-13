from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from meeting_agent.api.auth import require_admin_user_permission
from asu_june_bot.api.dependencies import get_health_service
from meeting_agent.auth.models import Principal
from asu_june_bot.health import HealthService


router = APIRouter(tags=["health"])
_require_diagnostics_read = require_admin_user_permission("users.manage")


@router.get("/admin/diagnostics/health")
def detailed_health(
    service: Annotated[HealthService, Depends(get_health_service)],
    _principal: Annotated[Principal, Depends(_require_diagnostics_read)],
) -> dict:
    """Return corpus and model diagnostics to an authenticated admin user."""
    return service.check()
