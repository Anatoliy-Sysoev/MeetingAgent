"""Trusted reverse-proxy policy for secure cookie resolution.

The cookie_secure=auto mode should only trust X-Forwarded-Proto: https
when the request arrives from a known trusted reverse proxy.  Trusting
forwarded headers from arbitrary clients allows spoofing.

Usage::

    cidrs = ["127.0.0.1/32", "10.0.0.0/8"]
    trusted = is_trusted_proxy(request.client.host, cidrs)
    secure = resolve_cookie_secure(
        configured="auto",
        request_scheme=request.url.scheme,
        forwarded_proto=request.headers.get("x-forwarded-proto"),
        client_host=request.client.host,
        trusted_proxy_cidrs=cidrs,
    )

Configuration::

    # config.yaml
    security:
      trusted_proxy_cidrs:
        - 127.0.0.1/32
        - 10.0.0.0/8

    # or env override (comma-separated)
    MEETINGAGENT_TRUSTED_PROXY_CIDRS=127.0.0.1/32,10.0.0.0/8
"""
from __future__ import annotations

import ipaddress
import os
from collections.abc import Mapping, Sequence
from typing import Any


def is_trusted_proxy(client_host: str | None, trusted_cidrs: Sequence[str]) -> bool:
    """Return True if *client_host* falls within any of *trusted_cidrs*.

    Returns False for empty/None host or empty CIDR list.
    Invalid CIDRs in *trusted_cidrs* are silently skipped.
    """
    if not trusted_cidrs or not client_host:
        return False
    try:
        addr = ipaddress.ip_address(client_host)
    except ValueError:
        return False
    for cidr in trusted_cidrs:
        try:
            if addr in ipaddress.ip_network(cidr, strict=False):
                return True
        except ValueError:
            continue
    return False


def resolve_cookie_secure(
    *,
    configured: str,
    request_scheme: str,
    forwarded_proto: str | None,
    client_host: str | None,
    trusted_proxy_cidrs: Sequence[str],
) -> bool:
    """Return True if the Secure cookie flag should be set.

    configured values: "true" | "false" | "auto"

    For "auto":
      - Returns True when the direct TLS scheme is https.
      - Returns True when X-Forwarded-Proto is https AND the client is a
        trusted proxy (client_host in trusted_proxy_cidrs).
      - Otherwise returns False.

    Forwarded-proto from an untrusted client is always ignored.
    """
    if configured == "true":
        return True
    if configured == "false":
        return False
    # auto
    if request_scheme == "https":
        return True
    if (
        forwarded_proto
        and forwarded_proto.strip().lower() == "https"
        and is_trusted_proxy(client_host, trusted_proxy_cidrs)
    ):
        return True
    return False


def parse_trusted_proxy_cidrs(
    config_value: object,
    env_value: str = "",
) -> list[str]:
    """Parse trusted_proxy_cidrs from config dict value or env string.

    Env (comma-separated) takes priority over config list.
    Returns an empty list when neither is provided.
    """
    if env_value.strip():
        return [c.strip() for c in env_value.split(",") if c.strip()]
    if isinstance(config_value, list):
        return [str(c).strip() for c in config_value if str(c).strip()]
    if isinstance(config_value, str) and config_value.strip():
        return [c.strip() for c in config_value.split(",") if c.strip()]
    return []


def validate_trusted_proxy_cidrs(cidrs: list[str]) -> list[str]:
    """Return list of invalid (unparseable) CIDR strings."""
    bad = []
    for cidr in cidrs:
        try:
            ipaddress.ip_network(cidr, strict=False)
        except ValueError:
            bad.append(cidr)
    return bad


def load_trusted_proxy_cidrs(
    config: dict[str, Any],
    env: Mapping[str, str] | None = None,
) -> list[str]:
    """Load trusted proxy CIDRs from config + env, in that priority order.

    Args:
        config: Loaded application config dict.
        env:    Environment mapping to read MEETINGAGENT_TRUSTED_PROXY_CIDRS from.
                Defaults to os.environ when None (runtime startup path).
    """
    if env is None:
        env = os.environ
    env_val = env.get("MEETINGAGENT_TRUSTED_PROXY_CIDRS", "")
    cfg_val = (config.get("security") or {}).get("trusted_proxy_cidrs")
    return parse_trusted_proxy_cidrs(cfg_val, env_val)
