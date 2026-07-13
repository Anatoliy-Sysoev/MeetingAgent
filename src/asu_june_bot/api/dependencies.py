from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

from fastapi import Request

from asu_june_bot.chat import ChatService
from asu_june_bot.health import HealthService
from asu_june_bot.observability import ChatRunsLogger
from asu_june_bot.observability.review_queue import ReviewQueue
from asu_june_bot.search import SearchService
from meeting_agent.api.dependencies import (
    CoreAppState,
    build_core_app_state,
    get_admin_service,
    get_app_state as get_core_app_state,
    get_local_auth_service,
    get_login_throttle,
    get_meeting_qa_service,
    live_settings,
    normalize_cookie_secure,
)
from meeting_agent.shared.llm.ollama_openai import OllamaOpenAIClient


@dataclass(slots=True)
class AppState(CoreAppState):
    """Integrated runtime state: MeetingAgent Core plus the optional bot layer."""

    search_service: SearchService
    health_service: HealthService
    chat_service: ChatService
    review_queue: ReviewQueue


# Backward-compatible names for callers that imported the old private helpers.
_normalize_cookie_secure = normalize_cookie_secure
_live_settings = live_settings


def build_app_state(config: dict | None = None) -> AppState:
    core = build_core_app_state(config=config)
    resolved_config = core.config
    search_service = SearchService(config=resolved_config)
    ollama_cfg = (
        resolved_config.get("ollama", {})
        if isinstance(resolved_config.get("ollama"), dict)
        else {}
    )
    chat_base_url = str(
        ollama_cfg.get("chat_base_url") or "http://127.0.0.1:11434/v1"
    )
    chat_model = str(ollama_cfg.get("chat_model") or "qwen3.5:4b")
    runs_path = Path("data/asu_june_bot/chat_runs.jsonl")
    labels_path = Path("data/asu_june_bot/chat_run_labels.jsonl")
    return AppState(
        config=core.config,
        meetings_service=core.meetings_service,
        meeting_qa_service=core.meeting_qa_service,
        job_runner=core.job_runner,
        live_session_service=core.live_session_service,
        auth_repository=core.auth_repository,
        local_auth_service=core.local_auth_service,
        admin_service=core.admin_service,
        login_throttle=core.login_throttle,
        bootstrap_policy=core.bootstrap_policy,
        trusted_proxy_cidrs=core.trusted_proxy_cidrs,
        search_service=search_service,
        health_service=HealthService(config=resolved_config),
        chat_service=ChatService(
            search_service=search_service,
            llm_client=OllamaOpenAIClient(base_url=chat_base_url, model=chat_model),
            runs_logger=ChatRunsLogger(runs_path),
        ),
        review_queue=ReviewQueue(runs_path=runs_path, labels_path=labels_path),
    )


def get_app_state(request: Request) -> AppState:
    return cast(AppState, get_core_app_state(request))


def get_search_service(request: Request) -> SearchService:
    return get_app_state(request).search_service


def get_health_service(request: Request) -> HealthService:
    return get_app_state(request).health_service


def get_chat_service(request: Request) -> ChatService:
    return get_app_state(request).chat_service


__all__ = [
    "AppState",
    "build_app_state",
    "get_admin_service",
    "get_app_state",
    "get_chat_service",
    "get_health_service",
    "get_local_auth_service",
    "get_login_throttle",
    "get_meeting_qa_service",
    "get_search_service",
]
