from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import Request

from asu_june_bot.auth.repository import DEFAULT_DB_PATH, AuthRepository
from asu_june_bot.auth.service import LocalAuthService
from asu_june_bot.chat import ChatService
from asu_june_bot.core.config import load_config
from asu_june_bot.health import HealthService
from asu_june_bot.jobs.runner import JobRunner
from asu_june_bot.llm.ollama_openai import OllamaOpenAIClient
from asu_june_bot.meetings.service import MeetingsService
from asu_june_bot.observability import ChatRunsLogger
from asu_june_bot.search import SearchService


@dataclass(slots=True)
class AppState:
    config: dict[str, Any]
    search_service: SearchService
    health_service: HealthService
    chat_service: ChatService
    meetings_service: MeetingsService
    job_runner: JobRunner
    auth_repository: AuthRepository
    local_auth_service: LocalAuthService


def build_app_state() -> AppState:
    config = load_config()
    search_service = SearchService(config=config)
    ollama_cfg = config.get("ollama", {}) if isinstance(config.get("ollama"), dict) else {}
    chat_base_url = str(ollama_cfg.get("chat_base_url") or "http://127.0.0.1:11434/v1")
    chat_model = str(ollama_cfg.get("chat_model") or "qwen3.5:4b")
    meetings_root = (config.get("paths") or {}).get("meetings_root") or "meetings"
    auth_db_path = Path((config.get("paths") or {}).get("auth_db") or DEFAULT_DB_PATH)
    auth_repository = AuthRepository(auth_db_path)
    auth_repository.initialize()
    return AppState(
        config=config,
        search_service=search_service,
        health_service=HealthService(config=config),
        chat_service=ChatService(
            search_service=search_service,
            llm_client=OllamaOpenAIClient(base_url=chat_base_url, model=chat_model),
            runs_logger=ChatRunsLogger(Path("data/asu_june_bot/chat_runs.jsonl")),
        ),
        meetings_service=MeetingsService(meetings_root=meetings_root),
        job_runner=JobRunner(),
        auth_repository=auth_repository,
        local_auth_service=LocalAuthService(auth_repository),
    )


def get_app_state(request: Request) -> AppState:
    return request.app.state.asu_june_bot


def get_search_service(request: Request) -> SearchService:
    return get_app_state(request).search_service


def get_health_service(request: Request) -> HealthService:
    return get_app_state(request).health_service


def get_chat_service(request: Request) -> ChatService:
    return get_app_state(request).chat_service


def get_local_auth_service(request: Request) -> LocalAuthService:
    return get_app_state(request).local_auth_service
