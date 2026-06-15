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
    MIN_BOOTSTRAP_SECRET_LENGTH,
    BootstrapPolicy,
    build_bootstrap_policy,
    is_local_request,
)
from asu_june_bot.auth.repository import AuthRepository  # noqa: E402
from asu_june_bot.auth.service import AdminService, LocalAuthService  # noqa: E402
from asu_june_bot.auth.throttle import LoginThrottle  # noqa: E402

_BOOTSTRAP_SECRET = "safety-test-bootstrap-secret-that-is-long-enough-abcdefgh"
_STRONG_SECRET = "a" * MIN_BOOTSTRAP_SECRET_LENGTH
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
    pol = build_bootstrap_policy({"bootstrap": {"allow_remote": True, "secret": _STRONG_SECRET}})
    assert pol.allow_remote is True
    assert pol.secret == _STRONG_SECRET


def test_build_bootstrap_policy_env_overrides_config(monkeypatch: pytest.MonkeyPatch) -> None:
    env_secret = "env-secret-value-that-is-long-enough-abcdefghij"
    monkeypatch.setenv("MEETINGAGENT_BOOTSTRAP_ALLOW_REMOTE", "true")
    monkeypatch.setenv("MEETINGAGENT_BOOTSTRAP_SECRET", env_secret)
    pol = build_bootstrap_policy({"bootstrap": {"allow_remote": False, "secret": _STRONG_SECRET}})
    assert pol.allow_remote is True
    assert pol.secret == env_secret


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
    """All loopback variants are treated as local (no forwarded headers)."""
    from asu_june_bot.api.routes_admin import _enforce_bootstrap_policy

    policy = BootstrapPolicy(allow_remote=False)
    for local_host in ("127.0.0.1", "::1", "::ffff:127.0.0.1"):
        mock_request = MagicMock()
        mock_request.client.host = local_host
        mock_request.headers.get = MagicMock(return_value="")
        _enforce_bootstrap_policy(mock_request, policy)  # must not raise


# ------------------------------------------------------------------
# Regression tests: loopback peer behind reverse proxy
# ------------------------------------------------------------------

def _make_proxy_request(peer_host: str, forwarded_header: str, forwarded_value: str) -> MagicMock:
    """Build a mock request that looks like it came through a reverse proxy."""
    mock_request = MagicMock()
    mock_request.client.host = peer_host

    def headers_get(key: str, default: str = "") -> str:
        if key.lower() == forwarded_header.lower():
            return forwarded_value
        return default

    mock_request.headers.get = headers_get
    return mock_request


def test_loopback_peer_with_x_forwarded_for_is_not_local() -> None:
    """Loopback peer + X-Forwarded-For → proxy detected; local bypass suppressed."""
    from asu_june_bot.api.routes_admin import _enforce_bootstrap_policy
    from fastapi import HTTPException

    request = _make_proxy_request("127.0.0.1", "x-forwarded-for", "203.0.113.10")
    policy = BootstrapPolicy(allow_remote=False)
    with pytest.raises(HTTPException) as exc_info:
        _enforce_bootstrap_policy(request, policy)
    assert exc_info.value.status_code == 403
    assert "remote" in exc_info.value.detail.lower()


def test_loopback_peer_with_forwarded_header_is_not_local() -> None:
    """Loopback peer + Forwarded header → proxy detected; local bypass suppressed."""
    from asu_june_bot.api.routes_admin import _enforce_bootstrap_policy
    from fastapi import HTTPException

    request = _make_proxy_request("127.0.0.1", "forwarded", "for=203.0.113.10")
    policy = BootstrapPolicy(allow_remote=False)
    with pytest.raises(HTTPException) as exc_info:
        _enforce_bootstrap_policy(request, policy)
    assert exc_info.value.status_code == 403


def test_loopback_peer_with_x_real_ip_is_not_local() -> None:
    """Loopback peer + X-Real-IP → proxy detected; local bypass suppressed."""
    from asu_june_bot.api.routes_admin import _enforce_bootstrap_policy
    from fastapi import HTTPException

    request = _make_proxy_request("127.0.0.1", "x-real-ip", "203.0.113.10")
    policy = BootstrapPolicy(allow_remote=False)
    with pytest.raises(HTTPException) as exc_info:
        _enforce_bootstrap_policy(request, policy)
    assert exc_info.value.status_code == 403


def test_loopback_behind_proxy_allow_remote_valid_secret_passes() -> None:
    """Loopback peer + X-Forwarded-For + valid secret → allowed."""
    from asu_june_bot.api.routes_admin import _enforce_bootstrap_policy

    mock_request = MagicMock()
    mock_request.client.host = "127.0.0.1"

    def headers_get(key: str, default: str = "") -> str:
        if key.lower() == "x-forwarded-for":
            return "203.0.113.10"
        if key == BOOTSTRAP_TOKEN_HEADER:
            return _BOOTSTRAP_SECRET
        return default

    mock_request.headers.get = headers_get
    policy = BootstrapPolicy(allow_remote=True, secret=_BOOTSTRAP_SECRET)
    _enforce_bootstrap_policy(mock_request, policy)  # must not raise


def test_loopback_behind_proxy_allow_remote_missing_secret_returns_403() -> None:
    """Loopback peer + X-Forwarded-For + allow_remote=True but no token → 403."""
    from asu_june_bot.api.routes_admin import _enforce_bootstrap_policy
    from fastapi import HTTPException

    mock_request = MagicMock()
    mock_request.client.host = "127.0.0.1"

    def headers_get(key: str, default: str = "") -> str:
        if key.lower() == "x-forwarded-for":
            return "203.0.113.10"
        return default

    mock_request.headers.get = headers_get
    policy = BootstrapPolicy(allow_remote=True, secret=_BOOTSTRAP_SECRET)
    with pytest.raises(HTTPException) as exc_info:
        _enforce_bootstrap_policy(mock_request, policy)
    assert exc_info.value.status_code == 403


# ------------------------------------------------------------------
# build_bootstrap_policy: secret validation
# ------------------------------------------------------------------

def test_build_bootstrap_policy_secret_non_string_raises() -> None:
    """auth.bootstrap.secret must be a str, not bool or int."""
    with pytest.raises(ValueError, match="string"):
        build_bootstrap_policy({"bootstrap": {"allow_remote": True, "secret": True}})

    with pytest.raises(ValueError, match="string"):
        build_bootstrap_policy({"bootstrap": {"allow_remote": True, "secret": 1}})


def test_build_bootstrap_policy_secret_too_short_raises() -> None:
    """Secret shorter than MIN_BOOTSTRAP_SECRET_LENGTH raises ValueError."""
    with pytest.raises(ValueError, match="too short"):
        build_bootstrap_policy({"bootstrap": {"allow_remote": True, "secret": "short"}})


def test_build_bootstrap_policy_well_known_short_secrets_rejected() -> None:
    """Well-known short strings ('password', 'secret', 'true') fail the length check."""
    for weak in ("password", "secret", "changeme", "true", "false", "1"):
        with pytest.raises(ValueError, match="too short"):
            build_bootstrap_policy({"bootstrap": {"allow_remote": True, "secret": weak}})


def test_build_bootstrap_policy_env_secret_too_short_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MEETINGAGENT_BOOTSTRAP_SECRET shorter than minimum raises ValueError."""
    monkeypatch.setenv("MEETINGAGENT_BOOTSTRAP_ALLOW_REMOTE", "true")
    monkeypatch.setenv("MEETINGAGENT_BOOTSTRAP_SECRET", "short")
    with pytest.raises(ValueError, match="too short"):
        build_bootstrap_policy({})


def test_build_bootstrap_policy_strong_secret_ok() -> None:
    """A strong secret of sufficient length is accepted."""
    pol = build_bootstrap_policy({"bootstrap": {"allow_remote": True, "secret": _STRONG_SECRET}})
    assert pol.allow_remote is True
    assert pol.secret == _STRONG_SECRET
