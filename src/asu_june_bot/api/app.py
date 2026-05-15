from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI

from asu_june_bot.api.dependencies import build_app_state
from asu_june_bot.api.errors import register_error_handlers
from asu_june_bot.api.middleware import request_context_middleware
from asu_june_bot.api.routes_health import router as health_router
from asu_june_bot.api.routes_search import router as search_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.asu_june_bot = build_app_state()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Asu June Bot API",
        version="0.2.0",
        description="Local project-only search API for Asu June Bot",
        lifespan=lifespan,
    )
    app.middleware("http")(request_context_middleware)
    register_error_handlers(app)
    app.include_router(health_router)
    app.include_router(search_router)
    return app


app = create_app()
