from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot import __version__  # noqa: E402
from asu_june_bot.api.app import create_app  # noqa: E402
from asu_june_bot.auth.repository import AuthRepository  # noqa: E402
from asu_june_bot.auth.service import AdminService, LocalAuthService  # noqa: E402
from asu_june_bot.auth.throttle import LoginThrottle  # noqa: E402
from asu_june_bot.health.service import check_ollama  # noqa: E402

TOKEN = "test-machine-token"


class FakeHealthService:
    def __init__(self) -> None:
        self.calls = 0

    def check(self) -> dict:
        self.calls += 1
        return {
            "status": "ok",
            "service": "asu_june_bot",
            "corpus_ready": True,
            "bm25_ready": True,
            "vector_ready": True,
            "guard_v2_ready": True,
            "paths": {"chunks_v2": "C:/private/corpus/chunks.jsonl"},
            "ollama": {
                "base_url": "http://127.0.0.1:11434",
                "models": ["private-model:latest"],
            },
        }


class FakeSearchService:
    pass


@dataclass(slots=True)
class FakeState:
    health_service: FakeHealthService
    search_service: FakeSearchService
    local_auth_service: LocalAuthService
    admin_service: AdminService
    auth_repository: AuthRepository
    login_throttle: LoginThrottle = field(default_factory=LoginThrottle)


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, FakeHealthService, AdminService]:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    repository = AuthRepository(tmp_path / "auth.db")
    repository.initialize()
    health_service = FakeHealthService()
    admin_service = AdminService(repository)
    state = FakeState(
        health_service=health_service,
        search_service=FakeSearchService(),
        local_auth_service=LocalAuthService(repository),
        admin_service=admin_service,
        auth_repository=repository,
    )
    app = create_app()
    app.state.asu_june_bot = state
    return TestClient(app, raise_server_exceptions=False), health_service, admin_service


def _login(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/auth/local/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return {"ma_session": response.cookies["ma_session"]}


def test_public_health_is_minimal_and_does_not_run_diagnostics(
    client: tuple[TestClient, FakeHealthService, AdminService],
) -> None:
    http, health_service, _ = client
    response = http.get("/health", headers={"X-Request-Id": "test-request-id"})

    assert response.status_code == 200
    assert response.headers["X-Request-Id"] == "test-request-id"
    assert response.json() == {
        "status": "ok",
        "service": "meetingagent",
        "version": __version__,
    }
    assert health_service.calls == 0
    body = response.text.lower()
    for forbidden in ("path", "corpus", "ollama", "model", "count", "ready", "error"):
        assert forbidden not in body


def test_diagnostics_require_auth(
    client: tuple[TestClient, FakeHealthService, AdminService],
) -> None:
    http, health_service, _ = client
    response = http.get("/admin/diagnostics/health")

    assert response.status_code == 401
    assert health_service.calls == 0


def test_diagnostics_reject_machine_token(
    client: tuple[TestClient, FakeHealthService, AdminService],
) -> None:
    http, health_service, _ = client
    response = http.get(
        "/admin/diagnostics/health",
        headers={"Authorization": f"Bearer {TOKEN}"},
    )

    assert response.status_code == 403
    assert health_service.calls == 0


def test_diagnostics_reject_viewer(
    client: tuple[TestClient, FakeHealthService, AdminService],
) -> None:
    http, health_service, admin_service = client
    admin_service.create_user(
        email="viewer@example.com",
        password="viewer-password",
        roles=["viewer"],
        actor_id="test",
    )
    cookies = _login(http, "viewer@example.com", "viewer-password")

    response = http.get("/admin/diagnostics/health", cookies=cookies)

    assert response.status_code == 403
    assert health_service.calls == 0


def test_admin_can_read_detailed_diagnostics(
    client: tuple[TestClient, FakeHealthService, AdminService],
) -> None:
    http, health_service, admin_service = client
    admin_service.create_user(
        email="admin@example.com",
        password="admin-password",
        roles=["admin"],
        actor_id="test",
    )
    cookies = _login(http, "admin@example.com", "admin-password")

    response = http.get("/admin/diagnostics/health", cookies=cookies)

    assert response.status_code == 200
    assert response.json()["paths"]["chunks_v2"] == "C:/private/corpus/chunks.jsonl"
    assert response.json()["ollama"]["models"] == ["private-model:latest"]
    assert health_service.calls == 1


def test_ollama_failure_does_not_echo_exception_details(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "http://proxy-user:proxy-password@internal-host:11434/private"

    def _raise(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError(secret)

    monkeypatch.setattr("asu_june_bot.health.service.requests.get", _raise)

    result = check_ollama("http://127.0.0.1:11434", "bge-m3", 1)

    assert result["error"] == "ollama_unavailable"
    assert secret not in str(result)
