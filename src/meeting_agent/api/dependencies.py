from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import Request

from meeting_agent.api.bootstrap_policy import BootstrapPolicy, build_bootstrap_policy
from meeting_agent.auth.deployment_safety import check_and_fail_if_unsafe
from meeting_agent.auth.repository import DEFAULT_DB_PATH, AuthRepository
from meeting_agent.auth.service import (
    DEFAULT_COOKIE_NAME,
    DEFAULT_COOKIE_SECURE,
    DEFAULT_SESSION_TTL_SECONDS,
    AdminService,
    LocalAuthService,
)
from meeting_agent.auth.throttle import LoginLimiter, build_login_throttle
from meeting_agent.auth.trusted_proxy import load_trusted_proxy_cidrs
from meeting_agent.jobs.runner import JobRunner
from meeting_agent.jobs.store import JobStore
from meeting_agent.live_sessions import LiveSessionService, LiveSessionStore
from meeting_agent.live_transcription.diart_client import DiartHttpClient
from meeting_agent.meeting_work import MeetingWorkCoordinator
from meeting_agent.meetings.qa import MeetingQAService
from meeting_agent.meetings.service import (
    MeetingsService,
    parse_max_text_artifact_bytes,
    parse_max_upload_bytes,
)
from meeting_agent.shared.config import load_config, resolve_work_path
from meeting_agent.shared.llm.ollama_openai import OllamaOpenAIClient


@dataclass(slots=True)
class CoreAppState:
    config: dict[str, Any]
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


def normalize_cookie_secure(value: Any) -> str:
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


def live_settings(config: dict[str, Any]) -> dict[str, Any]:
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
    diarization = raw.get("diarization")
    if diarization is None:
        diarization = {}
    if not isinstance(diarization, dict):
        raise ValueError("Invalid live.diarization: expected a mapping")
    diarization_enabled = diarization.get("enabled", False)
    if not isinstance(diarization_enabled, bool):
        raise ValueError("Invalid live.diarization.enabled: expected a boolean")
    diarization_base_url = diarization.get("base_url", "http://127.0.0.1:8765")
    if not isinstance(diarization_base_url, str) or not diarization_base_url:
        raise ValueError("Invalid live.diarization.base_url: expected a non-empty string")
    diarization_timeout = diarization.get("timeout_seconds", 900)
    if isinstance(diarization_timeout, bool) or not isinstance(
        diarization_timeout, (int, float)
    ):
        raise ValueError("Invalid live.diarization.timeout_seconds: expected a number")
    if not 1 <= float(diarization_timeout) <= 3_600:
        raise ValueError(
            "Invalid live.diarization.timeout_seconds: expected a value in 1..3600"
        )
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
        "audio_archive_max_bytes": integer("audio_archive_max_bytes", 2_000_000_000),
        "audio_archive_min_free_bytes": integer(
            "audio_archive_min_free_bytes", 256 * 1024 * 1024
        ),
        "diarization_enabled": diarization_enabled,
        "diarization_base_url": diarization_base_url,
        "diarization_timeout_seconds": float(diarization_timeout),
    }


def build_core_app_state(config: dict[str, Any] | None = None) -> CoreAppState:
    config = load_config() if config is None else config
    check_and_fail_if_unsafe(config)
    ollama_cfg = config.get("ollama", {}) if isinstance(config.get("ollama"), dict) else {}
    chat_base_url = str(ollama_cfg.get("chat_base_url") or "http://127.0.0.1:11434/v1")
    chat_model = str(ollama_cfg.get("chat_model") or "qwen3.5:4b")
    paths = config.get("paths") if isinstance(config.get("paths"), dict) else {}
    meetings_root = paths.get("meetings_root") or "meetings"
    jobs_state_path = resolve_work_path(
        config,
        paths.get("jobs_state") or "logs/jobs_state.json",
    )
    auth_db_path = Path(paths.get("auth_db") or DEFAULT_DB_PATH)
    auth_repository = AuthRepository(auth_db_path)
    auth_repository.initialize()
    auth_cfg = config.get("auth") if isinstance(config.get("auth"), dict) else {}
    session_ttl = int(auth_cfg.get("session_ttl_seconds") or DEFAULT_SESSION_TTL_SECONDS)
    cookie_name = str(auth_cfg.get("cookie_name") or DEFAULT_COOKIE_NAME)
    cookie_secure = normalize_cookie_secure(auth_cfg.get("cookie_secure"))
    login_throttle = build_login_throttle(auth_cfg.get("login_throttle"))
    bootstrap_policy = build_bootstrap_policy(auth_cfg)
    trusted_proxy_cidrs = load_trusted_proxy_cidrs(config)

    meetings_service = MeetingsService(
        meetings_root=meetings_root,
        max_text_artifact_bytes=parse_max_text_artifact_bytes(config),
        max_upload_bytes=parse_max_upload_bytes(config),
    )
    live_cfg = live_settings(config)
    live_state_path = resolve_work_path(
        config,
        paths.get("live_sessions_state") or "logs/live_sessions_state.json",
    )
    live_model_path = resolve_work_path(config, live_cfg["model_path"])
    diart_client = (
        DiartHttpClient(
            live_cfg["diarization_base_url"],
            timeout_seconds=live_cfg["diarization_timeout_seconds"],
        )
        if live_cfg["diarization_enabled"]
        else None
    )
    meeting_work_lock_path = resolve_work_path(
        config,
        paths.get("meeting_work_lock") or "logs/meeting_work.lock",
    )
    job_store = JobStore(jobs_state_path)
    live_store = LiveSessionStore(
        live_state_path,
        sessions_max=live_cfg["sessions_max"],
        active_sessions_max=live_cfg["active_sessions_max"],
        events_max=live_cfg["events_max"],
        max_state_bytes=live_cfg["max_state_bytes"],
    )
    coordinator = MeetingWorkCoordinator(
        meeting_work_lock_path,
        job_store=job_store,
        live_store=live_store,
    )
    job_runner = JobRunner(
        store=job_store,
        coordinator=coordinator,
        meetings_root=meetings_root,
    )
    live_session_service = LiveSessionService(
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
        audio_archive_max_bytes=live_cfg["audio_archive_max_bytes"],
        audio_archive_min_free_bytes=live_cfg["audio_archive_min_free_bytes"],
        diarizer=diart_client.diarize if diart_client is not None else None,
        store=live_store,
        coordinator=coordinator,
    )
    return CoreAppState(
        config=config,
        meetings_service=meetings_service,
        meeting_qa_service=MeetingQAService(
            config=config,
            meetings_service=meetings_service,
            llm_client=OllamaOpenAIClient(base_url=chat_base_url, model=chat_model),
        ),
        job_runner=job_runner,
        live_session_service=live_session_service,
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
    )


def get_app_state(request: Request) -> CoreAppState:
    state = getattr(request.app.state, "meeting_agent", None)
    legacy_state = getattr(request.app.state, "asu_june_bot", None)
    # Existing integrations and tests may replace only the legacy attribute.
    # A distinct legacy object is therefore treated as an explicit override
    # until the compatibility bridge is removed in Phase 5.
    if legacy_state is not None and legacy_state is not state:
        state = legacy_state
    elif state is None:
        state = legacy_state
    if state is None:
        raise RuntimeError("MeetingAgent application state is not initialized")
    return state


def get_meeting_qa_service(request: Request) -> MeetingQAService:
    return get_app_state(request).meeting_qa_service


def get_local_auth_service(request: Request) -> LocalAuthService:
    return get_app_state(request).local_auth_service


def get_login_throttle(request: Request) -> LoginLimiter:
    return get_app_state(request).login_throttle


def get_admin_service(request: Request) -> AdminService:
    return get_app_state(request).admin_service
