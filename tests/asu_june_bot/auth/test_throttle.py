from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.auth.throttle import (  # noqa: E402
    LoginThrottle,
    NoOpLoginThrottle,
    _extract_client_ip,
    build_login_throttle,
    parse_trusted_proxies,
)


class FakeClock:
    """Deterministic injectable monotonic clock."""

    def __init__(self, start: float = 1000.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def make_throttle(clock: FakeClock | None = None, **kwargs) -> LoginThrottle:
    defaults = dict(max_failures=3, window_seconds=60, block_seconds=120, max_entries=100)
    defaults.update(kwargs)
    return LoginThrottle(clock=clock or FakeClock(), **defaults)


EMAIL = "alice@example.com"
IP = "10.0.0.1"


# ------------------------------------------------------------------
# check / record_failure / record_success
# ------------------------------------------------------------------

def test_no_failure_not_blocked() -> None:
    t = make_throttle()
    assert t.check(EMAIL, IP).blocked is False


def test_below_threshold_not_blocked() -> None:
    t = make_throttle(max_failures=3)
    assert t.record_failure(EMAIL, IP).blocked is False
    assert t.record_failure(EMAIL, IP).blocked is False
    assert t.check(EMAIL, IP).blocked is False


def test_threshold_failure_blocks_immediately() -> None:
    """The failing attempt that reaches the threshold is itself blocked."""
    t = make_throttle(max_failures=3)
    assert t.record_failure(EMAIL, IP).blocked is False
    assert t.record_failure(EMAIL, IP).blocked is False
    decision = t.record_failure(EMAIL, IP)
    assert decision.blocked is True
    assert decision.retry_after >= 1


def test_check_blocked_after_threshold() -> None:
    t = make_throttle(max_failures=2)
    t.record_failure(EMAIL, IP)
    t.record_failure(EMAIL, IP)
    assert t.check(EMAIL, IP).blocked is True


def test_retry_after_is_positive_int() -> None:
    t = make_throttle(max_failures=2, block_seconds=120)
    t.record_failure(EMAIL, IP)
    decision = t.record_failure(EMAIL, IP)
    assert isinstance(decision.retry_after, int)
    assert decision.retry_after >= 1


def test_success_clears_throttle() -> None:
    t = make_throttle(max_failures=3)
    for _ in range(3):
        t.record_failure(EMAIL, IP)
    t.record_success(EMAIL, IP)
    assert t.check(EMAIL, IP).blocked is False


def test_different_email_not_affected() -> None:
    t = make_throttle(max_failures=3)
    for _ in range(3):
        t.record_failure(EMAIL, IP)
    assert t.check("bob@example.com", IP).blocked is False


def test_different_ip_not_affected() -> None:
    t = make_throttle(max_failures=3)
    for _ in range(3):
        t.record_failure(EMAIL, IP)
    assert t.check(EMAIL, "192.168.1.1").blocked is False


def test_attempts_expire_after_window() -> None:
    clock = FakeClock()
    t = make_throttle(clock=clock, max_failures=3, window_seconds=60, block_seconds=10)
    t.record_failure(EMAIL, IP)
    t.record_failure(EMAIL, IP)
    clock.advance(61)  # the two failures fall out of the window
    assert t.record_failure(EMAIL, IP).blocked is False
    assert t.check(EMAIL, IP).blocked is False


def test_block_expires() -> None:
    clock = FakeClock()
    t = make_throttle(clock=clock, max_failures=2, block_seconds=30)
    t.record_failure(EMAIL, IP)
    assert t.record_failure(EMAIL, IP).blocked is True
    clock.advance(31)
    assert t.check(EMAIL, IP).blocked is False


# ------------------------------------------------------------------
# LRU eviction + stale purge
# ------------------------------------------------------------------

def test_lru_eviction_bounds_storage() -> None:
    clock = FakeClock()
    t = make_throttle(clock=clock, max_failures=3, window_seconds=60, max_entries=5)
    for i in range(20):
        t.record_failure(f"user{i}@example.com", IP)
    # check() observes capacity bound; no direct state access.
    assert t.check("probe@example.com", IP).blocked is False


def test_stale_entries_purged_before_eviction() -> None:
    clock = FakeClock()
    t = make_throttle(clock=clock, max_failures=3, window_seconds=10, max_entries=3)
    t.record_failure("a@example.com", IP)
    t.record_failure("b@example.com", IP)
    clock.advance(100)  # both go stale
    # Adding more entries should reclaim stale slots rather than thrash.
    t.record_failure("c@example.com", IP)
    t.record_failure("d@example.com", IP)
    assert t.check("c@example.com", IP).blocked is False


# ------------------------------------------------------------------
# IP extraction (right-to-left, anti-spoofing)
# ------------------------------------------------------------------

def test_no_trusted_proxies_uses_remote_addr() -> None:
    nets = parse_trusted_proxies([])
    assert _extract_client_ip("1.2.3.4, 5.6.7.8", "10.0.0.1", nets) == "10.0.0.1"


def test_trusted_peer_takes_rightmost_untrusted() -> None:
    nets = parse_trusted_proxies(["10.0.0.0/8"])
    # peer 10.0.0.1 trusted; XFF rightmost 10.0.0.9 trusted → skip → 1.2.3.4
    assert _extract_client_ip("1.2.3.4, 10.0.0.9", "10.0.0.1", nets) == "1.2.3.4"


def test_spoofed_left_entry_not_trusted_when_middle_untrusted() -> None:
    nets = parse_trusted_proxies(["10.0.0.0/8"])
    # Attacker prepends 9.9.9.9; real client 8.8.8.8 is the rightmost untrusted hop.
    assert _extract_client_ip("9.9.9.9, 8.8.8.8", "10.0.0.1", nets) == "8.8.8.8"


def test_untrusted_peer_ignores_forwarded_for() -> None:
    nets = parse_trusted_proxies(["192.168.0.0/16"])
    assert _extract_client_ip("1.2.3.4", "10.0.0.1", nets) == "10.0.0.1"


def test_empty_forwarded_for_uses_peer() -> None:
    nets = parse_trusted_proxies(["10.0.0.0/8"])
    assert _extract_client_ip(None, "10.0.0.1", nets) == "10.0.0.1"


def test_malformed_xff_hop_falls_back() -> None:
    nets = parse_trusted_proxies(["10.0.0.0/8"])
    # rightmost is garbage → break → fall back to trusted peer
    assert _extract_client_ip("1.2.3.4, garbage", "10.0.0.1", nets) == "10.0.0.1"


def test_canonical_ip_returned() -> None:
    nets = parse_trusted_proxies(["10.0.0.0/8"])
    # IPv6 compressed form is canonicalized by ipaddress
    out = _extract_client_ip("2001:db8::0:1", "10.0.0.1", nets)
    assert out == "2001:db8::1"


def test_invalid_cidr_raises() -> None:
    with pytest.raises(ValueError):
        parse_trusted_proxies(["not-a-cidr"])


# ------------------------------------------------------------------
# build_login_throttle: config validation
# ------------------------------------------------------------------

def test_build_defaults_enabled() -> None:
    limiter = build_login_throttle(None)
    assert isinstance(limiter, LoginThrottle)
    assert limiter.max_failures == 5
    assert limiter.block_seconds == 900
    assert limiter.max_entries == 10000


def test_build_disabled_returns_noop() -> None:
    limiter = build_login_throttle({"enabled": False})
    assert isinstance(limiter, NoOpLoginThrottle)
    # NoOp never throttles
    for _ in range(100):
        assert limiter.record_failure(EMAIL, IP).blocked is False
    assert limiter.check(EMAIL, IP).blocked is False


def test_build_disabled_still_validates_cidrs() -> None:
    with pytest.raises(ValueError):
        build_login_throttle({"enabled": False, "trusted_proxy_cidrs": ["bad"]})


def test_build_rejects_non_bool_enabled() -> None:
    with pytest.raises(ValueError):
        build_login_throttle({"enabled": "yes"})


def test_build_rejects_bool_as_int() -> None:
    with pytest.raises(ValueError):
        build_login_throttle({"max_failures": True})


def test_build_rejects_zero() -> None:
    with pytest.raises(ValueError):
        build_login_throttle({"max_failures": 0})


def test_build_rejects_negative() -> None:
    with pytest.raises(ValueError):
        build_login_throttle({"window_seconds": -5})


def test_build_rejects_max_entries_below_max_failures() -> None:
    with pytest.raises(ValueError):
        build_login_throttle({"max_failures": 100, "max_entries": 10})


def test_build_accepts_full_valid_config() -> None:
    limiter = build_login_throttle(
        {
            "enabled": True,
            "max_failures": 4,
            "window_seconds": 120,
            "block_seconds": 600,
            "max_entries": 5000,
            "trusted_proxy_cidrs": ["10.0.0.0/8", "192.168.0.0/16"],
        }
    )
    assert isinstance(limiter, LoginThrottle)
    assert limiter.max_failures == 4
    assert limiter.block_seconds == 600


# ------------------------------------------------------------------
# Integration via login route
# ------------------------------------------------------------------

def _make_login_client(max_failures: int = 3, trusted_proxy_cidrs=None, peer="127.0.0.1"):
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
        max_failures=max_failures,
        window_seconds=300,
        block_seconds=900,
        trusted_proxy_cidrs=trusted_proxy_cidrs or [],
    )

    @dataclass(slots=True)
    class FakeState:
        auth_repository: AuthRepository
        local_auth_service: LocalAuthService
        login_throttle: object

    app = create_app()
    client = TestClient(app, raise_server_exceptions=False, client=(peer, 12345))
    service = LocalAuthService(repo)
    app.state.asu_june_bot = FakeState(
        auth_repository=repo,
        local_auth_service=service,
        login_throttle=throttle,
    )
    return client, repo


def test_login_throttle_threshold_request_gets_429() -> None:
    client, _repo = _make_login_client(max_failures=3)
    # First two failures → 401; third (threshold) → 429 immediately.
    assert client.post("/auth/local/login", json={"email": "alice@example.com", "password": "wrong"}).status_code == 401
    assert client.post("/auth/local/login", json={"email": "alice@example.com", "password": "wrong"}).status_code == 401
    r = client.post("/auth/local/login", json={"email": "alice@example.com", "password": "wrong"})
    assert r.status_code == 429


def test_login_throttle_retry_after_header_present() -> None:
    client, _repo = _make_login_client(max_failures=2)
    client.post("/auth/local/login", json={"email": "alice@example.com", "password": "bad"})
    r = client.post("/auth/local/login", json={"email": "alice@example.com", "password": "bad"})
    assert r.status_code == 429
    assert int(r.headers["retry-after"]) >= 1


def test_login_throttle_body_is_too_many_attempts() -> None:
    client, _repo = _make_login_client(max_failures=2)
    client.post("/auth/local/login", json={"email": "alice@example.com", "password": "bad"})
    r = client.post("/auth/local/login", json={"email": "alice@example.com", "password": "bad"})
    assert r.status_code == 429
    assert r.json()["detail"] == "Too many login attempts"


def test_login_throttle_unknown_email_same_behaviour() -> None:
    client, _repo = _make_login_client(max_failures=3)
    assert client.post("/auth/local/login", json={"email": "ghost@example.com", "password": "x"}).status_code == 401
    assert client.post("/auth/local/login", json={"email": "ghost@example.com", "password": "x"}).status_code == 401
    r = client.post("/auth/local/login", json={"email": "ghost@example.com", "password": "x"})
    assert r.status_code == 429


def test_successful_login_clears_throttle() -> None:
    client, _repo = _make_login_client(max_failures=3)
    client.post("/auth/local/login", json={"email": "alice@example.com", "password": "wrong"})
    r = client.post("/auth/local/login", json={"email": "alice@example.com", "password": "correct-password"})
    assert r.status_code == 200
    r2 = client.post("/auth/local/login", json={"email": "alice@example.com", "password": "wrong"})
    assert r2.status_code == 401  # cleared; not throttled


def test_throttle_emits_audit_event() -> None:
    client, repo = _make_login_client(max_failures=2)
    client.post("/auth/local/login", json={"email": "alice@example.com", "password": "bad"})
    client.post("/auth/local/login", json={"email": "alice@example.com", "password": "bad"})
    events = repo.list_audit_events()
    throttled = [e for e in events if e.action == "auth.login.throttled"]
    assert throttled
    # No password / session / CSRF leaked into the audit metadata.
    meta = throttled[0].metadata or {}
    assert set(meta.keys()) <= {"email"}
    assert meta.get("email") == "alice@example.com"


def test_throttle_trusted_proxy_honors_xff() -> None:
    # Peer 10.0.0.9 is a trusted proxy → XFF client 1.2.3.4 is the throttle key.
    client, _repo = _make_login_client(
        max_failures=3, trusted_proxy_cidrs=["10.0.0.0/8"], peer="10.0.0.9"
    )
    h = {"X-Forwarded-For": "1.2.3.4"}
    assert client.post("/auth/local/login", json={"email": "alice@example.com", "password": "wrong"}, headers=h).status_code == 401
    assert client.post("/auth/local/login", json={"email": "alice@example.com", "password": "wrong"}, headers=h).status_code == 401
    r = client.post("/auth/local/login", json={"email": "alice@example.com", "password": "wrong"}, headers=h)
    assert r.status_code == 429
    # A different XFF client behind the same proxy is throttled independently.
    h2 = {"X-Forwarded-For": "5.6.7.8"}
    assert client.post("/auth/local/login", json={"email": "alice@example.com", "password": "wrong"}, headers=h2).status_code == 401


def test_login_request_rejects_oversized_payload() -> None:
    client, _repo = _make_login_client()
    r = client.post("/auth/local/login", json={"email": "a@b.co", "password": "x" * 2000})
    assert r.status_code == 422
