from __future__ import annotations

"""In-memory login throttle for brute-force protection.

Storage is bounded to ``max_entries`` via LRU eviction (stale entries are
purged first). All operations are guarded by a single ``threading.Lock``,
making this safe for both sync and asyncio contexts (the lock is held only
for O(1)/O(window) dict work, never across awaits).

The limiter takes an injectable monotonic ``clock`` so behaviour is fully
deterministic under test without touching internal state or sleeping.
"""

import hashlib
import ipaddress
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Callable, Protocol

IpNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network
IpAddress = ipaddress.IPv4Address | ipaddress.IPv6Address

# Defaults aligned with issue #51 card.
DEFAULT_ENABLED = True
DEFAULT_MAX_FAILURES = 5
DEFAULT_WINDOW_SECONDS = 300
DEFAULT_BLOCK_SECONDS = 900
DEFAULT_MAX_ENTRIES = 10000


@dataclass(frozen=True)
class ThrottleDecision:
    """Result of a throttle check or recorded failure."""

    blocked: bool
    retry_after: int = 0


@dataclass
class _Bucket:
    attempts: list[float] = field(default_factory=list)  # monotonic timestamps
    blocked_until: float = 0.0


class LoginLimiter(Protocol):
    """Interface used by the login route; allows a NoOp disabled mode."""

    def client_ip(self, forwarded_for: str | None, remote_addr: str) -> str: ...
    def check(self, email: str, ip: str) -> ThrottleDecision: ...
    def record_failure(self, email: str, ip: str) -> ThrottleDecision: ...
    def record_success(self, email: str, ip: str) -> None: ...


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _email_key(email: str) -> str:
    normalized = email.strip().lower()
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def _throttle_key(email: str, ip: str) -> str:
    return f"{_email_key(email)}:{ip}"


def _is_trusted(ip: IpAddress, trusted: list[IpNetwork]) -> bool:
    return any(ip in net for net in trusted)


def _extract_client_ip(
    forwarded_for: str | None,
    remote_addr: str,
    trusted_proxies: list[IpNetwork],
) -> str:
    """Resolve the real client IP, robust against client-supplied spoofing.

    The rightmost entry of ``X-Forwarded-For`` is the address seen by the
    closest proxy and is therefore the only one we can begin to trust. We
    walk the chain right-to-left, skipping addresses that fall inside a
    configured trusted-proxy CIDR, and return the first *untrusted* valid
    address — that is the furthest hop we can still vouch for. A client can
    prepend arbitrary left-hand entries, so those are never trusted unless
    every proxy between them and us is trusted.

    Falls back to ``remote_addr`` whenever the direct peer is not itself a
    trusted proxy, or when the header is absent/malformed.
    """
    try:
        remote = ipaddress.ip_address(remote_addr)
    except ValueError:
        return remote_addr
    # The immediate peer must be a trusted proxy before we trust any XFF.
    if not trusted_proxies or not _is_trusted(remote, trusted_proxies):
        return str(remote)
    chain = (
        [p.strip() for p in forwarded_for.split(",") if p.strip()]
        if forwarded_for
        else []
    )
    for candidate in reversed(chain):
        try:
            ip = ipaddress.ip_address(candidate)
        except ValueError:
            # Malformed hop: cannot trust anything further left.
            break
        if _is_trusted(ip, trusted_proxies):
            continue
        return str(ip)
    # Whole chain trusted (or empty/malformed): best we can vouch for is peer.
    return str(remote)


def parse_trusted_proxies(cidrs: list[str]) -> list[IpNetwork]:
    result: list[IpNetwork] = []
    for cidr in cidrs:
        if not isinstance(cidr, str):
            raise ValueError(f"Trusted proxy CIDR must be a string, got {cidr!r}")
        try:
            result.append(ipaddress.ip_network(cidr, strict=False))
        except ValueError as exc:
            raise ValueError(f"Invalid trusted proxy CIDR {cidr!r}: {exc}") from exc
    return result


# ------------------------------------------------------------------
# Limiters
# ------------------------------------------------------------------

class NoOpLoginThrottle:
    """Disabled limiter — never throttles. Used when enabled=false."""

    def client_ip(self, forwarded_for: str | None, remote_addr: str) -> str:
        return remote_addr

    def check(self, email: str, ip: str) -> ThrottleDecision:
        return ThrottleDecision(blocked=False)

    def record_failure(self, email: str, ip: str) -> ThrottleDecision:
        return ThrottleDecision(blocked=False)

    def record_success(self, email: str, ip: str) -> None:
        return None


class LoginThrottle:
    """Bounded in-memory rate limiter keyed on email-hash + client IP."""

    def __init__(
        self,
        max_failures: int = DEFAULT_MAX_FAILURES,
        window_seconds: int = DEFAULT_WINDOW_SECONDS,
        block_seconds: int = DEFAULT_BLOCK_SECONDS,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        trusted_proxy_cidrs: list[str] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self.block_seconds = block_seconds
        self.max_entries = max_entries
        self._trusted = parse_trusted_proxies(trusted_proxy_cidrs or [])
        self._clock = clock
        self._buckets: OrderedDict[str, _Bucket] = OrderedDict()
        self._lock = threading.Lock()

    def client_ip(self, forwarded_for: str | None, remote_addr: str) -> str:
        return _extract_client_ip(forwarded_for, remote_addr, self._trusted)

    def _purge_stale(self, now: float) -> None:
        cutoff = now - self.window_seconds
        stale = [
            key
            for key, bucket in self._buckets.items()
            if bucket.blocked_until <= now
            and (not bucket.attempts or max(bucket.attempts) <= cutoff)
        ]
        for key in stale:
            del self._buckets[key]

    def _get_or_create(self, key: str, now: float) -> _Bucket:
        existing = self._buckets.get(key)
        if existing is not None:
            self._buckets.move_to_end(key)
            return existing
        if len(self._buckets) >= self.max_entries:
            self._purge_stale(now)
        if len(self._buckets) >= self.max_entries:
            self._buckets.popitem(last=False)  # evict LRU
        bucket = _Bucket()
        self._buckets[key] = bucket
        return bucket

    def _decision_if_blocked(self, bucket: _Bucket, now: float) -> ThrottleDecision:
        if bucket.blocked_until > now:
            retry_after = max(1, int(bucket.blocked_until - now) + 1)
            return ThrottleDecision(blocked=True, retry_after=retry_after)
        return ThrottleDecision(blocked=False)

    def check(self, email: str, ip: str) -> ThrottleDecision:
        """Return the current throttle decision without recording an attempt."""
        key = _throttle_key(email, ip)
        now = self._clock()
        with self._lock:
            bucket = self._get_or_create(key, now)
            decision = self._decision_if_blocked(bucket, now)
            if decision.blocked:
                return decision
            cutoff = now - self.window_seconds
            bucket.attempts = [t for t in bucket.attempts if t > cutoff]
            return ThrottleDecision(blocked=False)

    def record_failure(self, email: str, ip: str) -> ThrottleDecision:
        """Record a failed attempt; return a blocked decision if the threshold
        is reached *by this attempt*, so the caller can fail it with 429."""
        key = _throttle_key(email, ip)
        now = self._clock()
        with self._lock:
            bucket = self._get_or_create(key, now)
            if bucket.blocked_until > now:
                return self._decision_if_blocked(bucket, now)
            cutoff = now - self.window_seconds
            bucket.attempts = [t for t in bucket.attempts if t > cutoff]
            bucket.attempts.append(now)
            if len(bucket.attempts) >= self.max_failures:
                bucket.blocked_until = now + self.block_seconds
                return self._decision_if_blocked(bucket, now)
            return ThrottleDecision(blocked=False)

    def record_success(self, email: str, ip: str) -> None:
        key = _throttle_key(email, ip)
        with self._lock:
            self._buckets.pop(key, None)


# ------------------------------------------------------------------
# Config-driven construction with strict validation
# ------------------------------------------------------------------

def _require_bool(value: object, name: str, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ValueError(f"auth.login_throttle.{name} must be a boolean, got {value!r}")
    return value


def _require_positive_int(value: object, name: str, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        raise ValueError(f"auth.login_throttle.{name} must be an integer, not bool")
    if not isinstance(value, int):
        raise ValueError(f"auth.login_throttle.{name} must be an integer, got {value!r}")
    if value <= 0:
        raise ValueError(f"auth.login_throttle.{name} must be a positive integer, got {value}")
    return value


def build_login_throttle(
    config: dict | None,
    clock: Callable[[], float] = time.monotonic,
) -> LoginLimiter:
    """Build a limiter from ``auth.login_throttle`` config with strict validation.

    Raises ValueError on any invalid setting so misconfiguration fails at
    startup rather than silently degrading protection. All fields are validated
    even when ``enabled: false`` so a misconfigured-but-disabled section is
    caught before the service starts.
    """
    if config is None:
        cfg: dict = {}
    elif not isinstance(config, dict):
        raise ValueError(f"auth.login_throttle must be a mapping, got {config!r}")
    else:
        cfg = config

    enabled = _require_bool(cfg.get("enabled"), "enabled", DEFAULT_ENABLED)

    raw_cidrs = cfg.get("trusted_proxy_cidrs")
    if raw_cidrs is None:
        raw_cidrs = []
    elif not isinstance(raw_cidrs, (list, tuple)):
        raise ValueError(
            f"auth.login_throttle.trusted_proxy_cidrs must be a list, got {raw_cidrs!r}"
        )
    # Validate CIDRs eagerly so any bad CIDR surfaces regardless of enabled.
    parse_trusted_proxies(list(raw_cidrs))

    # Validate numeric settings unconditionally — a misconfigured-but-disabled
    # section must still fail at startup.
    max_failures = _require_positive_int(cfg.get("max_failures"), "max_failures", DEFAULT_MAX_FAILURES)
    window_seconds = _require_positive_int(cfg.get("window_seconds"), "window_seconds", DEFAULT_WINDOW_SECONDS)
    block_seconds = _require_positive_int(cfg.get("block_seconds"), "block_seconds", DEFAULT_BLOCK_SECONDS)
    max_entries = _require_positive_int(cfg.get("max_entries"), "max_entries", DEFAULT_MAX_ENTRIES)
    if max_entries < max_failures:
        raise ValueError(
            f"auth.login_throttle.max_entries ({max_entries}) must be >= max_failures ({max_failures})"
        )

    if not enabled:
        return NoOpLoginThrottle()

    return LoginThrottle(
        max_failures=max_failures,
        window_seconds=window_seconds,
        block_seconds=block_seconds,
        max_entries=max_entries,
        trusted_proxy_cidrs=list(raw_cidrs),
        clock=clock,
    )
