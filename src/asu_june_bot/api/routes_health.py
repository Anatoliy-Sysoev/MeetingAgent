from __future__ import annotations

from fastapi import APIRouter, Depends

from asu_june_bot.api.dependencies import get_health_service
from asu_june_bot.health import HealthService


router = APIRouter(tags=["health"])


@router.get("/health")
def health(service: HealthService = Depends(get_health_service)) -> dict:
    return service.check()
