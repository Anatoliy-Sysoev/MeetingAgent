from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from asu_june_bot import __version__
from asu_june_bot.api.dependencies import build_app_state
from asu_june_bot.api.errors import register_error_handlers
from asu_june_bot.api.host_policy import TrustedHostPolicyMiddleware, build_allowed_hosts
from asu_june_bot.api.middleware import request_context_middleware
from asu_june_bot.api.routes_admin import router as admin_router
from asu_june_bot.api.routes_review import router as review_router
from asu_june_bot.api.routes_auth import router as auth_router
from asu_june_bot.api.routes_chat import router as chat_router
from asu_june_bot.api.routes_health import router as health_router
from asu_june_bot.api.routes_ingest import router as ingest_router
from asu_june_bot.api.routes_jobs import router as jobs_router
from asu_june_bot.api.routes_meetingagent_ui import router as meetingagent_ui_router
from asu_june_bot.api.routes_meetings import router as meetings_router
from asu_june_bot.api.routes_search import router as search_router
from asu_june_bot.api.routes_ui import router as ui_router
from asu_june_bot.api.routes_workspace import router as workspace_router
from asu_june_bot.api.ui_assets import UI_ASSETS_V1_DIR
from asu_june_bot.core.config import load_config


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.asu_june_bot = build_app_state(config=app.state.startup_config)
    yield


def create_app(config: dict | None = None) -> FastAPI:
    resolved_config = load_config() if config is None else config
    app = FastAPI(
        title="Asu June Bot API",
        version=__version__,
        description="Local project-only search and chat API for Asu June Bot",
        lifespan=lifespan,
    )
    app.state.startup_config = resolved_config
    app.add_middleware(
        TrustedHostPolicyMiddleware,
        allowed_hosts=build_allowed_hosts(resolved_config),
    )
    app.middleware("http")(request_context_middleware)
    register_error_handlers(app)
    app.mount(
        "/assets/v1",
        StaticFiles(directory=UI_ASSETS_V1_DIR, check_dir=True),
        name="ui-assets-v1",
    )
    app.include_router(ui_router)
    app.include_router(meetingagent_ui_router)
    app.include_router(workspace_router)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(review_router)
    app.include_router(search_router)
    app.include_router(chat_router)
    app.include_router(ingest_router)
    app.include_router(meetings_router)
    app.include_router(jobs_router)
    return app


app = create_app()
