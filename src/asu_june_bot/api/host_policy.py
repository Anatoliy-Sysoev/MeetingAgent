from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlsplit

from starlette.datastructures import Headers
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send


ALLOWED_HOSTS_ENV = "MEETINGAGENT_ALLOWED_HOSTS"
DEFAULT_ALLOWED_HOSTS: tuple[str, ...] = (
    "localhost",
    "127.0.0.1",
    "::1",
    "::ffff:127.0.0.1",
    "testserver",
)
LOCAL_BOOTSTRAP_HOSTS: frozenset[str] = frozenset(
    {"localhost", "127.0.0.1", "::1", "::ffff:127.0.0.1"}
)


def normalize_host_header(value: str | None) -> str | None:
    """Return a lowercase hostname without port, or None for invalid Host syntax."""
    raw = str(value or "").strip()
    if not raw or len(raw) > 512:
        return None
    if any(char in raw for char in ("/", "\\", "@", "\r", "\n", "\0")):
        return None
    if any(char.isspace() for char in raw):
        return None

    # A bare IPv6 literal is useful in direct unit/config calls. HTTP Host
    # normally uses brackets, which urlsplit handles below.
    bare_ipv6 = raw.lower().rstrip(".")
    if bare_ipv6 in {"::1", "::ffff:127.0.0.1"}:
        return bare_ipv6

    try:
        parsed = urlsplit(f"//{raw}")
        _ = parsed.port  # validate that a supplied port is numeric/in range
    except ValueError:
        return None
    if parsed.username is not None or parsed.password is not None:
        return None
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        return None
    hostname = parsed.hostname
    if not hostname:
        return None
    return hostname.lower().rstrip(".")


def is_local_host_header(value: str | None) -> bool:
    host = normalize_host_header(value)
    return host in LOCAL_BOOTSTRAP_HOSTS if host else False


def _normalize_allowed_pattern(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("security.allowed_hosts entries must be strings")
    raw = value.strip().lower()
    if not raw:
        raise ValueError("security.allowed_hosts entries must not be empty")
    if raw == "*":
        raise ValueError("security.allowed_hosts must not contain the wildcard '*'")
    if raw not in {"::1", "::ffff:127.0.0.1"}:
        try:
            if urlsplit(f"//{raw}").port is not None:
                raise ValueError("security.allowed_hosts entries must not include ports")
        except ValueError as exc:
            raise ValueError(f"Invalid allowed host: {value!r}") from exc
    if raw.startswith("*."):
        suffix = normalize_host_header(raw[2:])
        if not suffix or ":" in suffix:
            raise ValueError(f"Invalid allowed host pattern: {value!r}")
        return f"*.{suffix}"
    if "*" in raw:
        raise ValueError(f"Invalid allowed host wildcard: {value!r}")
    normalized = normalize_host_header(raw)
    if not normalized:
        raise ValueError(f"Invalid allowed host: {value!r}")
    return normalized


def build_allowed_hosts(
    config: Mapping[str, Any] | None,
    env: Mapping[str, str] | None = None,
) -> list[str]:
    """Build a validated host allowlist from safe local defaults plus config/env."""
    env = os.environ if env is None else env
    security_cfg: Mapping[str, Any] = {}
    if config is not None:
        raw_security = config.get("security")
        if raw_security is not None and not isinstance(raw_security, Mapping):
            raise ValueError("security config must be a mapping")
        security_cfg = raw_security or {}

    env_value = str(env.get(ALLOWED_HOSTS_ENV) or "").strip()
    if env_value:
        configured: Sequence[Any] = [part.strip() for part in env_value.split(",")]
    else:
        raw_hosts = security_cfg.get("allowed_hosts")
        if raw_hosts is None:
            configured = []
        elif isinstance(raw_hosts, Sequence) and not isinstance(raw_hosts, (str, bytes)):
            configured = raw_hosts
        else:
            raise ValueError("security.allowed_hosts must be a list of hostnames")

    result: list[str] = list(DEFAULT_ALLOWED_HOSTS)
    for item in configured:
        normalized = _normalize_allowed_pattern(item)
        if normalized not in result:
            result.append(normalized)
    return result


def host_is_allowed(host: str, allowed_hosts: Sequence[str]) -> bool:
    for pattern in allowed_hosts:
        if pattern.startswith("*."):
            suffix = pattern[1:]
            if host.endswith(suffix) and host != suffix[1:]:
                return True
        elif host == pattern:
            return True
    return False


class TrustedHostPolicyMiddleware:
    """Reject missing, duplicate, malformed, or non-allowlisted Host headers."""

    def __init__(self, app: ASGIApp, allowed_hosts: Sequence[str]) -> None:
        self.app = app
        self.allowed_hosts = tuple(allowed_hosts)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        host_values = Headers(scope=scope).getlist("host")
        host = normalize_host_header(host_values[0]) if len(host_values) == 1 else None
        if host is None or not host_is_allowed(host, self.allowed_hosts):
            response = PlainTextResponse("Invalid host header", status_code=400)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
