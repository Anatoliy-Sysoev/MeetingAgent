from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from asu_june_bot.api.app import create_app
from asu_june_bot.api.bootstrap_policy import BootstrapPolicy
from asu_june_bot.api.ui_assets import load_ui_asset, load_ui_template
from asu_june_bot.auth.repository import AuthRepository
from asu_june_bot.auth.service import AdminService, LocalAuthService
from asu_june_bot.auth.throttle import LoginThrottle


ADMIN_PASSWORD = "adminpassword1"
MACHINE_TOKEN = "admin-ui-machine-token"


@dataclass(slots=True)
class FakeState:
    config: dict
    auth_repository: AuthRepository
    local_auth_service: LocalAuthService
    admin_service: AdminService
    login_throttle: LoginThrottle = field(default_factory=LoginThrottle)
    bootstrap_policy: BootstrapPolicy = field(default_factory=BootstrapPolicy)
    trusted_proxy_cidrs: list[str] = field(default_factory=list)


@pytest.fixture()
def admin_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, AdminService]:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", MACHINE_TOKEN)
    repository = AuthRepository(tmp_path / "auth.db")
    repository.initialize()
    service = AdminService(repository)
    app = create_app({})
    client = TestClient(app, raise_server_exceptions=False)
    app.state.asu_june_bot = FakeState(
        config={},
        auth_repository=repository,
        local_auth_service=LocalAuthService(repository),
        admin_service=service,
    )
    return client, service


def create_user(service: AdminService, email: str, role: str) -> None:
    service.create_user(
        email=email,
        password=ADMIN_PASSWORD,
        display_name=email.split("@", 1)[0],
        roles=[role],
        actor_id="test",
    )


def login(client: TestClient, email: str) -> None:
    response = client.post(
        "/auth/local/login",
        json={"email": email, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.json()


def test_admin_page_requires_local_admin_session(
    admin_client: tuple[TestClient, AdminService],
) -> None:
    client, service = admin_client
    assert client.get("/admin").status_code == 401
    assert client.get(
        "/admin",
        headers={"Authorization": f"Bearer {MACHINE_TOKEN}"},
    ).status_code == 403

    create_user(service, "viewer@example.com", "viewer")
    login(client, "viewer@example.com")
    assert client.get("/admin").status_code == 403


def test_admin_page_is_served_to_admin_with_packaged_assets(
    admin_client: tuple[TestClient, AdminService],
) -> None:
    client, service = admin_client
    create_user(service, "admin@example.com", "admin")
    login(client, "admin@example.com")
    response = client.get("/admin")
    assert response.status_code == 200
    assert "MeetingAgent Admin" in response.text
    assert 'href="/assets/v1/admin.css"' in response.text
    assert 'src="/assets/v1/admin.js"' in response.text
    assert "content-security-policy" in response.headers


def test_security_status_exposes_only_safe_bootstrap_flags(
    admin_client: tuple[TestClient, AdminService],
) -> None:
    client, service = admin_client
    create_user(service, "admin@example.com", "admin")
    secret = "x" * 40
    client.app.state.asu_june_bot.bootstrap_policy = BootstrapPolicy(
        allow_remote=True,
        secret=secret,
    )
    login(client, "admin@example.com")
    response = client.get("/admin/security/status")
    assert response.status_code == 200
    policy = response.json()["bootstrap_policy"]
    assert policy == {
        "remote_allowed": True,
        "secret_configured": True,
        "first_admin_created": True,
    }
    assert secret not in response.text
    assert str(client.app.state.asu_june_bot.auth_repository.db_path) not in response.text


def test_admin_ui_uses_existing_user_and_security_apis() -> None:
    content = load_ui_template("admin.html") + load_ui_asset("admin.js")
    for endpoint in (
        "/auth/me",
        "/auth/csrf",
        "/auth/logout",
        "/admin/security/status",
        "/admin/users",
    ):
        assert endpoint in content
    assert 'action.enable ? "enable" : "disable"' in content
    assert "encodeURIComponent(action.userId)" in content
    assert '"PATCH"' in content
    assert '"POST"' in content
    assert '"X-CSRF-Token"' in content


def test_admin_ui_has_explicit_status_confirmation_and_bounded_pagination() -> None:
    html = load_ui_template("admin.html")
    script = load_ui_asset("admin.js")
    assert 'id="status-dialog"' in html
    assert 'id="status-confirm-btn"' in html
    assert "PAGE_SIZE = 25" in script
    assert "offset + PAGE_SIZE" in script
    assert "showModal()" in script


def test_admin_ui_dynamic_content_uses_dom_apis_only() -> None:
    html = load_ui_template("admin.html")
    script = load_ui_asset("admin.js")
    assert not re.search(r"<[^>]+\son[a-z]+\s*=", html, re.IGNORECASE)
    assert "textContent" in script
    assert "replaceChildren" in script
    assert "innerHTML" not in script
    assert "localStorage" not in script
    assert "sessionStorage" not in script
    assert not re.search(r"\.style(?:\.|\s*=)", script)


def test_product_navigation_starts_hidden_and_is_permission_gated() -> None:
    meetingagent = load_ui_template("meetingagent.html") + load_ui_asset("meetingagent.js")
    bot = load_ui_template("bot.html") + load_ui_asset("bot.js")
    workspace = load_ui_template("workspace.html") + load_ui_asset("workspace.js")
    for content in (meetingagent, bot, workspace):
        assert 'href="/admin"' in content
        assert "users.manage" in content
        assert "hidden" in content


def test_admin_ui_source_contains_no_secret_or_absolute_path() -> None:
    content = load_ui_template("admin.html") + load_ui_asset("admin.js")
    assert "MEETINGAGENT_BOOTSTRAP_SECRET" not in content
    assert "password_hash" not in content
    assert "C:\\Users\\" not in content
    assert "C:/Users/" not in content
