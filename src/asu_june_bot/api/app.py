from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from asu_june_bot.api.dependencies import build_app_state
from asu_june_bot.api.routes_review import router as review_router
from asu_june_bot.api.routes_chat import router as chat_router
from asu_june_bot.api.routes_health import router as bot_health_router
from asu_june_bot.api.routes_search import router as search_router
from asu_june_bot.api.routes_ui import router as ui_router
from meeting_agent import __version__
from meeting_agent.api.app import (
    bind_core_state,
    include_core_product_routes,
    install_core_infrastructure,
)
from meeting_agent.shared.config import load_config


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    state = build_app_state(config=app.state.startup_config)
    bind_core_state(app, state)
    try:
        yield
    finally:
        await asyncio.to_thread(state.live_session_service.shutdown)


def create_app(config: dict | None = None) -> FastAPI:
    resolved_config = load_config() if config is None else config
    app = FastAPI(
        title="Asu June Bot API",
        version=__version__,
        description="Local project-only search and chat API for Asu June Bot",
        lifespan=lifespan,
    )
    app.state.startup_config = resolved_config
    install_core_infrastructure(app, resolved_config)
    app.include_router(ui_router)
    include_core_product_routes(app)
    app.include_router(bot_health_router)
    app.include_router(review_router)
    app.include_router(search_router)
    app.include_router(chat_router)
    return app


app = create_app()
