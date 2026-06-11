from __future__ import annotations

"""In-memory login throttle for brute-force protection.

Storage is bounded to MAX_ENTRIES via LRU eviction. All operations are
protected by a single threading.Lock, making this safe for both sync and
asyncio contexts (no await needed; lock held only for O(1) dict ops).
"""

import hashlib
import ipaddress
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field


DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_WINDOW_SECONDS = 300       # 5 min rolling window
DEFAULT_BLOCK_SECONDS = 300        # 5 min block after limit exceeded
DEFAULT_MAX_ENTRIES = 4096         # LRU cap
DEFAULT_TRUSTED_PROXIES: list[str] = []


class ThrottledError(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__(f"Too many attempts. Retry after {retry_after}s.")
        self.retry_after = retry_after


@dataclass
class _Bucket:
    attempts: list[float] = field(default_factory=list)  # attempt timestamps
    blocked_until: float = 0.0


def _email_key(email: str) -> str:
    normalized = email.strip().lower()
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def _ip_key(ip: str) -> str:
    return ip


def _throttle_key(email: str, ip: str) -> str:
    return f"{_email_key(email)}:{_ip_key(ip)}"


def _extract_client_ip(
    forwarded_for: str | None,
    remote_addr: str,
    trusted_proxies: list[ipaddress.IPv4Network | ipaddress.IPv6Network],
) -> str:
    """Return the client IP.

    Trusts X-Forwarded-For only when the direct connection comes from a
    configured trusted proxy CIDR. Falls back to the remote address.
    """
    if not forwarded_for or not trusted_proxies:
        return remote_addr
    try:
        remote = ipaddress.ip_address(remote_addr)
    except ValueError:
        return remote_addr
    trusted = any(remote in net for net in trusted_proxies)
    if not trusted:
        return remote_addr
    # Take the leftmost entry (original client) from the header.
    parts = [p.strip() for p in forwarded_for.split(",") if p.strip()]
    if not parts:
        return remote_addr
    try:
        ipaddress.ip_address(parts[0])
    except ValueError:
        return remote_addr
    return parts[0]


def _parse_trusted_proxies(
    cidrs: list[str],
) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    result: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for cidr in cidrs:
        try:
            result.append(ipaddress.ip_network(cidr, strict=False))
        except ValueError as exc:
            raise ValueError(f"Invalid trusted proxy CIDR {cidr!r}: {exc}") from exc
    return result


class LoginThrottle:
    """Bounded in-memory rate limiter keyed on email-hash + client IP."""

    def __init__(
        self,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        window_seconds: int = DEFAULT_WINDOW_SECONDS,
        block_seconds: int = DEFAULT_BLOCK_SECONDS,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        trusted_proxy_cidrs: list[str] | None = None,
    ) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.block_seconds = block_seconds
        self.max_entries = max_entries
        self._trusted: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = (
            _parse_trusted_proxies(trusted_proxy_cidrs or [])
        )
        self._buckets: OrderedDict[str, _Bucket] = OrderedDict()
        self._lock = threading.Lock()

    def client_ip(self, forwarded_for: str | None, remote_addr: str) -> str:
        return _extract_client_ip(forwarded_for, remote_addr, self._trusted)

    def _get_or_create(self, key: str) -> _Bucket:
        if key in self._buckets:
            self._buckets.move_to_end(key)
            return self._buckets[key]
        if len(self._buckets) >= self.max_entries:
            self._buckets.popitem(last=False)  # evict LRU
        bucket = _Bucket()
        self._buckets[key] = bucket
        return bucket

    def check(self, email: str, ip: str) -> None:
        """Raise ThrottledError if the limit is currently exceeded.

        Call *before* credential verification so both known and unknown emails
        are rejected at the same point.
        """
        key = _throttle_key(email, ip)
        now = time.monotonic()
        with self._lock:
            bucket = self._get_or_create(key)
            if bucket.blocked_until > now:
                retry_after = max(1, int(bucket.blocked_until - now) + 1)
                raise ThrottledError(retry_after)
            # Trim expired attempts from rolling window.
            cutoff = now - self.window_seconds
            bucket.attempts = [t for t in bucket.attempts if t > cutoff]

    def record_failure(self, email: str, ip: str) -> None:
        """Record a failed attempt and set a block if the threshold is exceeded."""
        key = _throttle_key(email, ip)
        now = time.monotonic()
        with self._lock:
            bucket = self._get_or_create(key)
            cutoff = now - self.window_seconds
            bucket.attempts = [t for t in bucket.attempts if t > cutoff]
            bucket.attempts.append(now)
            if len(bucket.attempts) >= self.max_attempts:
                bucket.blocked_until = now + self.block_seconds

    def record_success(self, email: str, ip: str) -> None:
        """Clear throttle state for this key on successful login."""
        key = _throttle_key(email, ip)
        with self._lock:
            self._buckets.pop(key, None)
