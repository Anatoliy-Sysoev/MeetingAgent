from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from meeting_agent import __version__
from meeting_agent.api.dependencies import CoreAppState, build_core_app_state
from meeting_agent.api.errors import register_error_handlers
from meeting_agent.api.host_policy import TrustedHostPolicyMiddleware, build_allowed_hosts
from meeting_agent.api.middleware import request_context_middleware
from meeting_agent.api.routes_admin import router as admin_router
from meeting_agent.api.routes_admin_ui import router as admin_ui_router
from meeting_agent.api.routes_auth import router as auth_router
from meeting_agent.api.routes_health import router as health_router
from meeting_agent.api.routes_ingest import router as ingest_router
from meeting_agent.api.routes_jobs import router as jobs_router
from meeting_agent.api.routes_live import router as live_router
from meeting_agent.api.routes_meetingagent_ui import router as meetingagent_ui_router
from meeting_agent.api.routes_meetings import router as meetings_router
from meeting_agent.api.routes_workspace import router as workspace_router
from meeting_agent.api.ui_assets import UI_ASSETS_V1_DIR, UI_ASSETS_V2_DIR
from meeting_agent.shared.config import load_config


def install_core_infrastructure(app: FastAPI, config: dict) -> None:
    app.add_middleware(
        TrustedHostPolicyMiddleware,
        allowed_hosts=build_allowed_hosts(config),
    )
    app.middleware("http")(request_context_middleware)
    register_error_handlers(app)
    app.mount(
        "/assets/v1",
        StaticFiles(directory=UI_ASSETS_V1_DIR, check_dir=True),
        name="ui-assets-v1",
    )
    app.mount(
        "/assets/v2",
        StaticFiles(directory=UI_ASSETS_V2_DIR, check_dir=True),
        name="ui-assets-v2",
    )


def include_core_product_routes(app: FastAPI) -> None:
    app.include_router(meetingagent_ui_router)
    app.include_router(workspace_router)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(admin_ui_router)
    app.include_router(admin_router)
    app.include_router(ingest_router)
    app.include_router(meetings_router)
    app.include_router(jobs_router)
    app.include_router(live_router)


def bind_core_state(app: FastAPI, state: CoreAppState) -> None:
    app.state.meeting_agent = state
    # Temporary bridge for callers/tests that still address the old state name.
    app.state.asu_june_bot = state


def create_app(config: dict | None = None) -> FastAPI:
    resolved_config = load_config() if config is None else config

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        state = build_core_app_state(config=app.state.startup_config)
        bind_core_state(app, state)
        try:
            yield
        finally:
            await asyncio.to_thread(state.live_session_service.shutdown)

    app = FastAPI(
        title="MeetingAgent Core API",
        version=__version__,
        description="Local-first meeting lifecycle, processing and artifacts API",
        lifespan=lifespan,
    )
    app.state.startup_config = resolved_config
    install_core_infrastructure(app, resolved_config)
    include_core_product_routes(app)
    return app


app = create_app()
