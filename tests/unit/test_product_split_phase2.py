from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from meeting_agent.api.app import create_app as create_core_app


ROOT = Path(__file__).resolve().parents[2]


def _route_paths(app) -> set[str]:
    paths: set[str] = set()
    pending = list(app.routes)
    seen: set[int] = set()
    while pending:
        route = pending.pop()
        if id(route) in seen:
            continue
        seen.add(id(route))

        path = getattr(route, "path", None)
        if isinstance(path, str):
            paths.add(path)

        pending.extend(getattr(route, "routes", ()) or ())
        original_router = getattr(route, "original_router", None)
        if original_router is not None:
            pending.extend(getattr(original_router, "routes", ()) or ())
    return paths


def _core_config(tmp_path: Path) -> dict:
    return {
        "work_root_path": tmp_path,
        "paths": {
            "meetings_root": str(tmp_path / "meetings"),
            "jobs_state": str(tmp_path / "logs" / "jobs.json"),
            "live_sessions_state": str(tmp_path / "logs" / "live.json"),
            "meeting_work_lock": str(tmp_path / "logs" / "meeting_work.lock"),
            "auth_db": str(tmp_path / "data" / "auth.db"),
        },
        "live": {"model_path": str(tmp_path / "models" / "vosk")},
    }


def test_core_import_does_not_load_bot_runtime_modules() -> None:
    code = """
import sys
import meeting_agent.api.app
forbidden = (
    'asu_june_bot.search',
    'asu_june_bot.chat',
    'asu_june_bot.retrieval',
    'asu_june_bot.health',
    'asu_june_bot.telegram_bot',
)
loaded = sorted(name for name in sys.modules if name.startswith(forbidden))
assert loaded == [], loaded
"""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_core_app_starts_without_bot_routes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MEETINGAGENT_DEPLOYMENT_MODE", "local")
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", "core-test-token-32-characters-long")
    app = create_core_app(_core_config(tmp_path))

    paths = _route_paths(app)
    assert "/health" in paths
    assert "/MeetingAgent" in paths
    assert "/meetings" in paths
    assert "/search" not in paths
    assert "/chat" not in paths
    assert "/ui" not in paths

    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/health").json()["service"] == "meetingagent"
        assert client.get("/MeetingAgent").status_code == 200
        assert client.get("/meetings").status_code == 401
        assert app.state.meeting_agent is app.state.asu_june_bot


def test_relative_auth_db_resolves_under_configured_work_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import meeting_agent.api.dependencies as dependencies

    monkeypatch.setattr(dependencies, "check_and_fail_if_unsafe", lambda _config: None)
    config = _core_config(tmp_path)
    config["paths"]["auth_db"] = "runtime/auth.db"

    state = dependencies.build_core_app_state(config)
    try:
        assert state.auth_repository.db_path == (tmp_path / "runtime" / "auth.db").resolve()
        assert state.auth_repository.db_path.exists()
    finally:
        state.live_session_service.shutdown()


def test_relative_speaker_directory_resolves_under_configured_work_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import meeting_agent.api.dependencies as dependencies

    monkeypatch.setattr(dependencies, "check_and_fail_if_unsafe", lambda _config: None)
    config = _core_config(tmp_path)
    config["paths"]["speaker_directory"] = "private/speakers.json"

    state = dependencies.build_core_app_state(config)
    try:
        assert state.meetings_service.speaker_directory.path == (
            tmp_path / "private" / "speakers.json"
        ).resolve()
    finally:
        state.live_session_service.shutdown()


def test_integrated_app_adds_bot_routes() -> None:
    from asu_june_bot.api.app import create_app as create_integrated_app

    paths = _route_paths(create_integrated_app({}))
    assert {"/MeetingAgent", "/meetings", "/health", "/search", "/chat", "/ui"} <= paths


def test_legacy_packages_are_explicit_identity_preserving_shims() -> None:
    package_pairs = (
        ("asu_june_bot.auth", "meeting_agent.auth", "service"),
        ("asu_june_bot.jobs", "meeting_agent.jobs", "runner"),
        ("asu_june_bot.live_sessions", "meeting_agent.live_sessions", "service"),
        ("asu_june_bot.meetings", "meeting_agent.meetings", "service"),
    )
    for legacy_name, current_name, submodule in package_pairs:
        legacy_package = importlib.import_module(legacy_name)
        assert legacy_package.DEPRECATED_COMPATIBILITY_SHIM is True
        legacy_module = importlib.import_module(f"{legacy_name}.{submodule}")
        current_module = importlib.import_module(f"{current_name}.{submodule}")
        assert legacy_module is current_module

    legacy_api = importlib.import_module("asu_june_bot.api")
    assert legacy_api.DEPRECATED_COMPATIBILITY_SHIM is False
    assert "routes_meetings" in legacy_api.DEPRECATED_MODULE_ALIASES
    assert importlib.import_module("asu_june_bot.api.routes_meetings") is importlib.import_module(
        "meeting_agent.api.routes_meetings"
    )


def test_legacy_meeting_work_module_reexports_core_symbol() -> None:
    legacy = importlib.import_module("asu_june_bot.meeting_work")
    current = importlib.import_module("meeting_agent.meeting_work")
    assert legacy.DEPRECATED_COMPATIBILITY_SHIM is True
    assert legacy.MeetingWorkCoordinator is current.MeetingWorkCoordinator
