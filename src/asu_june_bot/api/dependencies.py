from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import Request

from asu_june_bot.auth.deployment_safety import check_and_fail_if_unsafe
from asu_june_bot.auth.repository import DEFAULT_DB_PATH, AuthRepository
from asu_june_bot.auth.trusted_proxy import load_trusted_proxy_cidrs
from asu_june_bot.auth.service import (
    DEFAULT_COOKIE_NAME,
    DEFAULT_COOKIE_SECURE,
    DEFAULT_SESSION_TTL_SECONDS,
    AdminService,
    LocalAuthService,
)
from asu_june_bot.auth.throttle import LoginLimiter, build_login_throttle
from asu_june_bot.api.bootstrap_policy import BootstrapPolicy, build_bootstrap_policy
from asu_june_bot.chat import ChatService
from asu_june_bot.core.config import load_config, resolve_work_path
from asu_june_bot.health import HealthService
from asu_june_bot.jobs.runner import JobRunner
from asu_june_bot.live_sessions import LiveSessionService
from asu_june_bot.llm.ollama_openai import OllamaOpenAIClient
from asu_june_bot.meetings.qa import MeetingQAService
from asu_june_bot.meetings.service import (
    MeetingsService,
    parse_max_text_artifact_bytes,
    parse_max_upload_bytes,
)
from asu_june_bot.observability import ChatRunsLogger
from asu_june_bot.observability.review_queue import ReviewQueue
from asu_june_bot.search import SearchService


@dataclass(slots=True)
class AppState:
    config: dict[str, Any]
    search_service: SearchService
    health_service: HealthService
    chat_service: ChatService
    meetings_service: MeetingsService
    meeting_qa_service: MeetingQAService
    job_runner: JobRunner
    live_session_service: LiveSessionService
    auth_repository: AuthRepository
    local_auth_service: LocalAuthService
    admin_service: AdminService
    login_throttle: LoginLimiter
    bootstrap_policy: BootstrapPolicy
    trusted_proxy_cidrs: list[str]
    review_queue: ReviewQueue


def _normalize_cookie_secure(value: Any) -> str:
    """Accept YAML bool or string auto|true|false; reject anything else."""
    if value is None:
        return DEFAULT_COOKIE_SECURE
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ("auto", "true", "false"):
            return normalized
    raise ValueError(
        f"Invalid auth.cookie_secure: {value!r} (expected auto, true, or false)"
    )


def _live_settings(config: dict[str, Any]) -> dict[str, Any]:
    raw = config.get("live")
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("Invalid live config: expected a mapping")

    def integer(key: str, default: int) -> int:
        value = raw.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"Invalid live.{key}: expected an integer")
        return value

    def number(key: str, default: float) -> float:
        value = raw.get(key, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Invalid live.{key}: expected a number")
        return float(value)

    vad = raw.get("vad", "silero")
    model_path = raw.get("model_path", "models/vosk/vosk-model-small-ru-0.22")
    if not isinstance(vad, str) or not vad:
        raise ValueError("Invalid live.vad: expected a non-empty string")
    if not isinstance(model_path, str) or not model_path:
        raise ValueError("Invalid live.model_path: expected a non-empty string")
    return {
        "model_path": model_path,
        "vad": vad,
        "sample_rate": integer("sample_rate", 16_000),
        "block_ms": integer("block_ms", 300),
        "mic_queue_max_blocks": integer("mic_queue_max_blocks", 32),
        "partials_max": integer("partials_max", 1_000),
        "events_max": integer("events_max", 500),
        "sessions_max": integer("sessions_max", 50),
        "active_sessions_max": integer("active_sessions_max", 2),
        "max_state_bytes": integer("max_state_bytes", 4 * 1024 * 1024),
        "stop_timeout_seconds": number("stop_timeout_seconds", 15.0),
    }


def build_app_state(config: dict[str, Any] | None = None) -> AppState:
    config = load_config() if config is None else config
    check_and_fail_if_unsafe(config)  # fails closed in self_hosted mode on unsafe config
    search_service = SearchService(config=config)
    ollama_cfg = config.get("ollama", {}) if isinstance(config.get("ollama"), dict) else {}
    chat_base_url = str(ollama_cfg.get("chat_base_url") or "http://127.0.0.1:11434/v1")
    chat_model = str(ollama_cfg.get("chat_model") or "qwen3.5:4b")
    meetings_root = (config.get("paths") or {}).get("meetings_root") or "meetings"
    jobs_state_path = resolve_work_path(
        config,
        (config.get("paths") or {}).get("jobs_state") or "logs/jobs_state.json",
    )
    max_text_artifact_bytes = parse_max_text_artifact_bytes(config)
    max_upload_bytes = parse_max_upload_bytes(config)
    auth_db_path = Path((config.get("paths") or {}).get("auth_db") or DEFAULT_DB_PATH)
    auth_repository = AuthRepository(auth_db_path)
    auth_repository.initialize()
    auth_cfg = config.get("auth") or {}
    session_ttl = int(auth_cfg.get("session_ttl_seconds") or DEFAULT_SESSION_TTL_SECONDS)
    cookie_name = str(auth_cfg.get("cookie_name") or DEFAULT_COOKIE_NAME)
    cookie_secure = _normalize_cookie_secure(auth_cfg.get("cookie_secure"))
    login_throttle = build_login_throttle(auth_cfg.get("login_throttle"))
    bootstrap_policy = build_bootstrap_policy(auth_cfg)
    trusted_proxy_cidrs = load_trusted_proxy_cidrs(config)
    meetings_service = MeetingsService(
        meetings_root=meetings_root,
        max_text_artifact_bytes=max_text_artifact_bytes,
        max_upload_bytes=max_upload_bytes,
    )
    live_cfg = _live_settings(config)
    live_state_path = resolve_work_path(
        config,
        (config.get("paths") or {}).get("live_sessions_state")
        or "logs/live_sessions_state.json",
    )
    live_model_path = resolve_work_path(
        config,
        live_cfg["model_path"],
    )
    _runs_path = Path("data/asu_june_bot/chat_runs.jsonl")
    _labels_path = Path("data/asu_june_bot/chat_run_labels.jsonl")
    return AppState(
        config=config,
        search_service=search_service,
        health_service=HealthService(config=config),
        chat_service=ChatService(
            search_service=search_service,
            llm_client=OllamaOpenAIClient(base_url=chat_base_url, model=chat_model),
            runs_logger=ChatRunsLogger(Path("data/asu_june_bot/chat_runs.jsonl")),
        ),
        meetings_service=meetings_service,
        meeting_qa_service=MeetingQAService(
            config=config,
            meetings_service=meetings_service,
            llm_client=OllamaOpenAIClient(base_url=chat_base_url, model=chat_model),
        ),
        job_runner=JobRunner(
            state_path=jobs_state_path,
            meetings_root=meetings_root,
        ),
        live_session_service=LiveSessionService(
            meetings_root=meetings_service.root,
            state_path=live_state_path,
            model_path=live_model_path,
            vad=live_cfg["vad"],
            sample_rate=live_cfg["sample_rate"],
            block_ms=live_cfg["block_ms"],
            mic_queue_max_blocks=live_cfg["mic_queue_max_blocks"],
            partials_max=live_cfg["partials_max"],
            events_max=live_cfg["events_max"],
            sessions_max=live_cfg["sessions_max"],
            active_sessions_max=live_cfg["active_sessions_max"],
            max_state_bytes=live_cfg["max_state_bytes"],
            stop_timeout_seconds=live_cfg["stop_timeout_seconds"],
        ),
        auth_repository=auth_repository,
        local_auth_service=LocalAuthService(
            auth_repository,
            session_ttl_seconds=session_ttl,
            cookie_name=cookie_name,
            cookie_secure=cookie_secure,  # type: ignore[arg-type]
        ),
        admin_service=AdminService(auth_repository),
        login_throttle=login_throttle,
        bootstrap_policy=bootstrap_policy,
        trusted_proxy_cidrs=trusted_proxy_cidrs,
        review_queue=ReviewQueue(runs_path=_runs_path, labels_path=_labels_path),
    )


def get_app_state(request: Request) -> AppState:
    return request.app.state.asu_june_bot


def get_search_service(request: Request) -> SearchService:
    return get_app_state(request).search_service


def get_health_service(request: Request) -> HealthService:
    return get_app_state(request).health_service


def get_chat_service(request: Request) -> ChatService:
    return get_app_state(request).chat_service


def get_meeting_qa_service(request: Request) -> MeetingQAService:
    return get_app_state(request).meeting_qa_service


def get_local_auth_service(request: Request) -> LocalAuthService:
    return get_app_state(request).local_auth_service


def get_login_throttle(request: Request) -> LoginLimiter:
    return get_app_state(request).login_throttle


def get_admin_service(request: Request) -> AdminService:
    return get_app_state(request).admin_service
