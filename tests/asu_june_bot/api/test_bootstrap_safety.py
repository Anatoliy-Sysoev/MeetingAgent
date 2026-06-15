"""Tests for bootstrap safety policy: local bypass, remote blocking, secret gate."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fastapi.testclient import TestClient  # noqa: E402

from asu_june_bot.api.app import create_app  # noqa: E402
from asu_june_bot.api.bootstrap_policy import (  # noqa: E402
    BOOTSTRAP_TOKEN_HEADER,
    BootstrapPolicy,
    build_bootstrap_policy,
    is_local_request,
)
from asu_june_bot.auth.repository import AuthRepository  # noqa: E402
from asu_june_bot.auth.service import AdminService, LocalAuthService  # noqa: E402
from asu_june_bot.auth.throttle import LoginThrottle  # noqa: E402

_BOOTSTRAP_SECRET = "safety-test-bootstrap-secret"
_ADMIN_EMAIL = "admin@example.com"
_ADMIN_PASS = "adminpassword1"
_PAYLOAD = {"email": _ADMIN_EMAIL, "password": _ADMIN_PASS}


@dataclass(slots=True)
class FakeState:
    auth_repository: AuthRepository
    local_auth_service: LocalAuthService
    admin_service: AdminService
    login_throttle: LoginThrottle = field(default_factory=LoginThrottle)
    bootstrap_policy: BootstrapPolicy = field(
        default_factory=lambda: BootstrapPolicy(allow_remote=False)
    )


@pytest.fixture()
def repo(tmp_path: Path) -> AuthRepository:
    r = AuthRepository(tmp_path / "auth.db")
    r.initialize()
    return r


def _make_client(repo: AuthRepository, policy: BootstrapPolicy) -> TestClient:
    os.environ["MEETINGAGENT_API_TOKEN"] = "safety-test-machine-token"
    app = create_app()
    c = TestClient(app, raise_server_exceptions=False)
    app.state.asu_june_bot = FakeState(
        auth_repository=repo,
        local_auth_service=LocalAuthService(repo),
        admin_service=AdminService(repo),
        bootstrap_policy=policy,
    )
    return c


# ------------------------------------------------------------------
# Unit tests: is_local_request
# ------------------------------------------------------------------

@pytest.mark.parametrize("host,expected", [
    ("127.0.0.1", True),
    ("::1", True),
    ("::ffff:127.0.0.1", True),
    ("192.168.1.1", False),
    ("10.0.0.1", False),
    ("testclient", False),   # TestClient default host
    ("", False),
    (None, False),
])
def test_is_local_request(host: str | None, expected: bool) -> None:
    assert is_local_request(host) is expected


# ------------------------------------------------------------------
# Unit tests: build_bootstrap_policy
# ------------------------------------------------------------------

def test_build_bootstrap_policy_defaults() -> None:
    pol = build_bootstrap_policy({})
    assert pol.allow_remote is False
    assert pol.secret == ""


def test_build_bootstrap_policy_allow_remote_from_config() -> None:
    pol = build_bootstrap_policy({"bootstrap": {"allow_remote": True, "secret": "s3cr3t"}})
    assert pol.allow_remote is True
    assert pol.secret == "s3cr3t"


def test_build_bootstrap_policy_env_overrides_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEETINGAGENT_BOOTSTRAP_ALLOW_REMOTE", "true")
    monkeypatch.setenv("MEETINGAGENT_BOOTSTRAP_SECRET", "env-secret")
    pol = build_bootstrap_policy({"bootstrap": {"allow_remote": False, "secret": "config-secret"}})
    assert pol.allow_remote is True
    assert pol.secret == "env-secret"


def test_build_bootstrap_policy_allow_remote_without_secret_raises() -> None:
    with pytest.raises(ValueError, match="secret"):
        build_bootstrap_policy({"bootstrap": {"allow_remote": True}})


def test_build_bootstrap_policy_allow_remote_without_secret_env_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEETINGAGENT_BOOTSTRAP_ALLOW_REMOTE", "true")
    monkeypatch.delenv("MEETINGAGENT_BOOTSTRAP_SECRET", raising=False)
    with pytest.raises(ValueError, match="secret"):
        build_bootstrap_policy({})


def test_build_bootstrap_policy_invalid_allow_remote_value_raises() -> None:
    with pytest.raises(ValueError, match="allow_remote"):
        build_bootstrap_policy({"bootstrap": {"allow_remote": "yes"}})


def test_build_bootstrap_policy_invalid_env_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEETINGAGENT_BOOTSTRAP_ALLOW_REMOTE", "maybe")
    with pytest.raises(ValueError, match="MEETINGAGENT_BOOTSTRAP_ALLOW_REMOTE"):
        build_bootstrap_policy({})


# ------------------------------------------------------------------
# Integration tests via TestClient
# Note: TestClient uses host="testclient" (non-local). All integration
# tests therefore exercise the non-local policy path.
# The local bypass is covered by unit tests above and route unit tests below.
# ------------------------------------------------------------------

def test_nonlocal_bootstrap_blocked_by_default(repo: AuthRepository) -> None:
    """Default policy (allow_remote=False): non-local request returns 403."""
    client = _make_client(repo, BootstrapPolicy(allow_remote=False))
    resp = client.post("/admin/bootstrap", json=_PAYLOAD)
    assert resp.status_code == 403
    assert "remote" in resp.json()["detail"].lower()


def test_nonlocal_bootstrap_missing_secret_returns_403(repo: AuthRepository) -> None:
    """allow_remote=True but no X-Bootstrap-Token header → 403."""
    client = _make_client(repo, BootstrapPolicy(allow_remote=True, secret=_BOOTSTRAP_SECRET))
    resp = client.post("/admin/bootstrap", json=_PAYLOAD)
    assert resp.status_code == 403


def test_nonlocal_bootstrap_invalid_secret_returns_403(repo: AuthRepository) -> None:
    """allow_remote=True but wrong X-Bootstrap-Token → 403."""
    client = _make_client(repo, BootstrapPolicy(allow_remote=True, secret=_BOOTSTRAP_SECRET))
    resp = client.post(
        "/admin/bootstrap",
        json=_PAYLOAD,
        headers={BOOTSTRAP_TOKEN_HEADER: "wrong-secret"},
    )
    assert resp.status_code == 403


def test_nonlocal_bootstrap_valid_secret_succeeds(repo: AuthRepository) -> None:
    """allow_remote=True and correct X-Bootstrap-Token → 201."""
    client = _make_client(repo, BootstrapPolicy(allow_remote=True, secret=_BOOTSTRAP_SECRET))
    resp = client.post(
        "/admin/bootstrap",
        json=_PAYLOAD,
        headers={BOOTSTRAP_TOKEN_HEADER: _BOOTSTRAP_SECRET},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == _ADMIN_EMAIL
    assert "admin" in body["roles"]


def test_bootstrap_conflict_still_returns_409_with_valid_secret(repo: AuthRepository) -> None:
    """Users already exist → 409, even with valid secret."""
    client = _make_client(repo, BootstrapPolicy(allow_remote=True, secret=_BOOTSTRAP_SECRET))
    hdrs = {BOOTSTRAP_TOKEN_HEADER: _BOOTSTRAP_SECRET}
    client.post("/admin/bootstrap", json=_PAYLOAD, headers=hdrs)
    resp = client.post(
        "/admin/bootstrap",
        json={"email": "other@example.com", "password": "otherpass"},
        headers=hdrs,
    )
    assert resp.status_code == 409


def test_bootstrap_response_does_not_contain_secret(repo: AuthRepository) -> None:
    """Bootstrap token must never appear in the response body."""
    client = _make_client(repo, BootstrapPolicy(allow_remote=True, secret=_BOOTSTRAP_SECRET))
    resp = client.post(
        "/admin/bootstrap",
        json=_PAYLOAD,
        headers={BOOTSTRAP_TOKEN_HEADER: _BOOTSTRAP_SECRET},
    )
    assert resp.status_code == 201
    body_text = resp.text
    assert _BOOTSTRAP_SECRET not in body_text


def test_bootstrap_error_response_does_not_echo_secret(repo: AuthRepository) -> None:
    """Even on 403, the response must not echo back the provided (wrong) token."""
    bad_token = "this-is-the-wrong-secret-value"
    client = _make_client(repo, BootstrapPolicy(allow_remote=True, secret=_BOOTSTRAP_SECRET))
    resp = client.post(
        "/admin/bootstrap",
        json=_PAYLOAD,
        headers={BOOTSTRAP_TOKEN_HEADER: bad_token},
    )
    assert resp.status_code == 403
    assert bad_token not in resp.text


# ------------------------------------------------------------------
# Unit test: _enforce_bootstrap_policy bypasses for local peer
# ------------------------------------------------------------------

def test_local_peer_bypasses_policy_entirely(repo: AuthRepository) -> None:
    """A request from 127.0.0.1 is allowed regardless of policy settings."""
    from asu_june_bot.api.routes_admin import _enforce_bootstrap_policy
    from fastapi import HTTPException

    mock_request = MagicMock()
    mock_request.client.host = "127.0.0.1"
    mock_request.headers.get = MagicMock(return_value="")

    # Even with allow_remote=False (default), local request passes
    policy = BootstrapPolicy(allow_remote=False)
    # Should not raise
    _enforce_bootstrap_policy(mock_request, policy)


def test_nonlocal_peer_with_allow_remote_false_raises(repo: AuthRepository) -> None:
    """A non-local peer with allow_remote=False raises HTTPException 403."""
    from asu_june_bot.api.routes_admin import _enforce_bootstrap_policy
    from fastapi import HTTPException

    mock_request = MagicMock()
    mock_request.client.host = "203.0.113.42"
    mock_request.headers.get = MagicMock(return_value="")

    policy = BootstrapPolicy(allow_remote=False)
    with pytest.raises(HTTPException) as exc_info:
        _enforce_bootstrap_policy(mock_request, policy)
    assert exc_info.value.status_code == 403


def test_nonlocal_loopback_variants_also_local() -> None:
    """All loopback variants are treated as local."""
    from asu_june_bot.api.routes_admin import _enforce_bootstrap_policy

    policy = BootstrapPolicy(allow_remote=False)
    for local_host in ("127.0.0.1", "::1", "::ffff:127.0.0.1"):
        mock_request = MagicMock()
        mock_request.client.host = local_host
        _enforce_bootstrap_policy(mock_request, policy)  # must not raise
