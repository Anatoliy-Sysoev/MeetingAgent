from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.auth.throttle import (  # noqa: E402
    LoginThrottle,
    ThrottledError,
    _extract_client_ip,
    _parse_trusted_proxies,
)


def make_throttle(**kwargs) -> LoginThrottle:
    defaults = dict(max_attempts=3, window_seconds=60, block_seconds=60)
    defaults.update(kwargs)
    return LoginThrottle(**defaults)


EMAIL = "alice@example.com"
IP = "10.0.0.1"


# ------------------------------------------------------------------
# Unit: check / record_failure / record_success
# ------------------------------------------------------------------

def test_no_failure_does_not_throttle() -> None:
    t = make_throttle()
    t.check(EMAIL, IP)  # must not raise


def test_below_threshold_does_not_throttle() -> None:
    t = make_throttle(max_attempts=3)
    for _ in range(2):
        t.record_failure(EMAIL, IP)
    t.check(EMAIL, IP)  # should not raise


def test_at_threshold_throttles() -> None:
    t = make_throttle(max_attempts=3)
    for _ in range(3):
        t.record_failure(EMAIL, IP)
    with pytest.raises(ThrottledError) as exc_info:
        t.check(EMAIL, IP)
    assert exc_info.value.retry_after >= 1


def test_retry_after_is_positive_int() -> None:
    t = make_throttle(max_attempts=2, block_seconds=120)
    t.record_failure(EMAIL, IP)
    t.record_failure(EMAIL, IP)
    with pytest.raises(ThrottledError) as exc_info:
        t.check(EMAIL, IP)
    assert isinstance(exc_info.value.retry_after, int)
    assert exc_info.value.retry_after >= 1


def test_success_clears_throttle() -> None:
    t = make_throttle(max_attempts=3)
    for _ in range(3):
        t.record_failure(EMAIL, IP)
    t.record_success(EMAIL, IP)
    t.check(EMAIL, IP)  # must not raise after success


def test_different_email_not_affected() -> None:
    t = make_throttle(max_attempts=3)
    for _ in range(3):
        t.record_failure(EMAIL, IP)
    other = "bob@example.com"
    t.check(other, IP)  # different email; must not raise


def test_different_ip_not_affected() -> None:
    t = make_throttle(max_attempts=3)
    for _ in range(3):
        t.record_failure(EMAIL, IP)
    t.check(EMAIL, "192.168.1.1")  # different IP; must not raise


def test_attempts_expire_after_window() -> None:
    t = make_throttle(max_attempts=3, window_seconds=1, block_seconds=1)
    for _ in range(3):
        t.record_failure(EMAIL, IP)
    # Patch the bucket timestamps to be older than the window.
    key = list(t._buckets.keys())[0]
    t._buckets[key].attempts = [time.monotonic() - 2.0] * 3
    t._buckets[key].blocked_until = 0.0
    t.check(EMAIL, IP)  # must not raise; attempts are stale


def test_block_expires() -> None:
    t = make_throttle(max_attempts=2, block_seconds=1)
    for _ in range(2):
        t.record_failure(EMAIL, IP)
    key = list(t._buckets.keys())[0]
    # Set block to already expired
    t._buckets[key].blocked_until = time.monotonic() - 1.0
    t.check(EMAIL, IP)  # must not raise after block expired


# ------------------------------------------------------------------
# LRU eviction
# ------------------------------------------------------------------

def test_lru_eviction_bounds_storage() -> None:
    t = make_throttle(max_entries=5)
    for i in range(10):
        email = f"user{i}@example.com"
        t.record_failure(email, IP)
    assert len(t._buckets) <= 5


# ------------------------------------------------------------------
# IP extraction
# ------------------------------------------------------------------

def test_no_trusted_proxies_uses_remote_addr() -> None:
    t = make_throttle()
    ip = t.client_ip("1.2.3.4, 5.6.7.8", "10.0.0.1")
    assert ip == "10.0.0.1"


def test_trusted_proxy_uses_forwarded_for() -> None:
    t = make_throttle(trusted_proxy_cidrs=["10.0.0.0/8"])
    ip = t.client_ip("1.2.3.4, 10.0.0.99", "10.0.0.1")
    assert ip == "1.2.3.4"


def test_untrusted_proxy_ignores_forwarded_for() -> None:
    t = make_throttle(trusted_proxy_cidrs=["192.168.0.0/16"])
    ip = t.client_ip("1.2.3.4", "10.0.0.1")
    assert ip == "10.0.0.1"


def test_empty_forwarded_for_uses_remote_addr() -> None:
    t = make_throttle(trusted_proxy_cidrs=["10.0.0.0/8"])
    ip = t.client_ip(None, "10.0.0.1")
    assert ip == "10.0.0.1"


def test_invalid_cidr_raises_value_error() -> None:
    with pytest.raises(ValueError):
        LoginThrottle(trusted_proxy_cidrs=["not-a-cidr"])


def test_invalid_ip_in_forwarded_for_falls_back_to_remote() -> None:
    t = make_throttle(trusted_proxy_cidrs=["10.0.0.0/8"])
    ip = t.client_ip("not-an-ip", "10.0.0.1")
    assert ip == "10.0.0.1"


# ------------------------------------------------------------------
# Integration via login route
# ------------------------------------------------------------------

def _make_login_client(max_attempts: int = 3, trusted_proxy_cidrs=None):
    from asu_june_bot.api.app import create_app
    from asu_june_bot.auth.passwords import hash_password
    from asu_june_bot.auth.repository import AuthRepository
    from asu_june_bot.auth.service import LocalAuthService
    import tempfile

    td = tempfile.mkdtemp()
    repo = AuthRepository(Path(td) / "auth.db")
    repo.initialize()
    user = repo.create_user(email="alice@example.com", display_name="Alice")
    repo.create_local_credential(user.user_id, hash_password("correct-password"))
    repo.set_user_roles(user.user_id, {"editor"})

    throttle = LoginThrottle(
        max_attempts=max_attempts,
        window_seconds=300,
        block_seconds=300,
        trusted_proxy_cidrs=trusted_proxy_cidrs or [],
    )

    @dataclass(slots=True)
    class FakeState:
        auth_repository: AuthRepository
        local_auth_service: LocalAuthService
        login_throttle: LoginThrottle

    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)
    app.state.asu_june_bot = FakeState(
        auth_repository=repo,
        local_auth_service=LocalAuthService(repo),
        login_throttle=throttle,
    )
    return client


def test_login_throttle_triggers_429() -> None:
    client = _make_login_client(max_attempts=3)
    for _ in range(3):
        r = client.post("/auth/local/login", json={"email": "alice@example.com", "password": "wrong"})
        assert r.status_code == 401
    r = client.post("/auth/local/login", json={"email": "alice@example.com", "password": "wrong"})
    assert r.status_code == 429


def test_login_throttle_retry_after_header_present() -> None:
    client = _make_login_client(max_attempts=2)
    for _ in range(2):
        client.post("/auth/local/login", json={"email": "alice@example.com", "password": "bad"})
    r = client.post("/auth/local/login", json={"email": "alice@example.com", "password": "bad"})
    assert r.status_code == 429
    assert "retry-after" in {k.lower() for k in r.headers}
    assert int(r.headers["retry-after"]) >= 1


def test_login_throttle_unknown_email_also_throttled() -> None:
    """Unknown email and wrong password follow same throttle path — no enumeration."""
    client = _make_login_client(max_attempts=3)
    for _ in range(3):
        client.post("/auth/local/login", json={"email": "unknown@example.com", "password": "x"})
    r = client.post("/auth/local/login", json={"email": "unknown@example.com", "password": "x"})
    assert r.status_code == 429


def test_successful_login_clears_throttle() -> None:
    client = _make_login_client(max_attempts=3)
    for _ in range(2):
        client.post("/auth/local/login", json={"email": "alice@example.com", "password": "wrong"})
    r = client.post("/auth/local/login", json={"email": "alice@example.com", "password": "correct-password"})
    assert r.status_code == 200
    # After success, failures are cleared; can try again without 429.
    r2 = client.post("/auth/local/login", json={"email": "alice@example.com", "password": "wrong"})
    assert r2.status_code == 401  # not 429


def test_throttle_response_body_does_not_leak_reason() -> None:
    """Response body must be the generic error string regardless of throttle or bad creds."""
    client = _make_login_client(max_attempts=2)
    client.post("/auth/local/login", json={"email": "alice@example.com", "password": "wrong"})
    client.post("/auth/local/login", json={"email": "alice@example.com", "password": "wrong"})
    r = client.post("/auth/local/login", json={"email": "alice@example.com", "password": "wrong"})
    assert r.status_code == 429
    assert r.json()["detail"] == "Invalid email or password"


def test_throttle_trusted_proxy_cidr() -> None:
    client = _make_login_client(
        max_attempts=3, trusted_proxy_cidrs=["10.0.0.0/8"]
    )
    # All requests come from the same forwarded IP; they should share throttle state.
    for _ in range(3):
        r = client.post(
            "/auth/local/login",
            json={"email": "alice@example.com", "password": "wrong"},
            headers={"X-Forwarded-For": "1.2.3.4"},
        )
        assert r.status_code == 401
    r = client.post(
        "/auth/local/login",
        json={"email": "alice@example.com", "password": "wrong"},
        headers={"X-Forwarded-For": "1.2.3.4"},
    )
    assert r.status_code == 429
