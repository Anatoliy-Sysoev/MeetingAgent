from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import Request

from asu_june_bot.health import HealthService
from asu_june_bot.search import SearchService
from asu_june_bot.core.config import load_config


@dataclass(slots=True)
class AppState:
    config: dict[str, Any]
    search_service: SearchService
    health_service: HealthService


def build_app_state() -> AppState:
    config = load_config()
    return AppState(
        config=config,
        search_service=SearchService(config=config),
        health_service=HealthService(config=config),
    )


def get_app_state(request: Request) -> AppState:
    return request.app.state.asu_june_bot


def get_search_service(request: Request) -> SearchService:
    return get_app_state(request).search_service


def get_health_service(request: Request) -> HealthService:
    return get_app_state(request).health_service
