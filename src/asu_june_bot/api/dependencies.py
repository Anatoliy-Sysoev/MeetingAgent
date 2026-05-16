from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import Request

from asu_june_bot.chat import ChatService
from asu_june_bot.core.config import load_config
from asu_june_bot.health import HealthService
from asu_june_bot.llm.ollama_openai import OllamaOpenAIClient
from asu_june_bot.observability import ChatRunsLogger
from asu_june_bot.search import SearchService


@dataclass(slots=True)
class AppState:
    config: dict[str, Any]
    search_service: SearchService
    health_service: HealthService
    chat_service: ChatService


def build_app_state() -> AppState:
    config = load_config()
    search_service = SearchService(config=config)
    ollama_cfg = config.get("ollama", {}) if isinstance(config.get("ollama"), dict) else {}
    chat_base_url = str(ollama_cfg.get("chat_base_url") or "http://127.0.0.1:11434/v1")
    chat_model = str(ollama_cfg.get("chat_model") or "qwen2.5:7b-instruct")
    return AppState(
        config=config,
        search_service=search_service,
        health_service=HealthService(config=config),
        chat_service=ChatService(
            search_service=search_service,
            llm_client=OllamaOpenAIClient(base_url=chat_base_url, model=chat_model),
            runs_logger=ChatRunsLogger(Path("data/asu_june_bot/chat_runs.jsonl")),
        ),
    )


def get_app_state(request: Request) -> AppState:
    return request.app.state.asu_june_bot


def get_search_service(request: Request) -> SearchService:
    return get_app_state(request).search_service


def get_health_service(request: Request) -> HealthService:
    return get_app_state(request).health_service


def get_chat_service(request: Request) -> ChatService:
    return get_app_state(request).chat_service
