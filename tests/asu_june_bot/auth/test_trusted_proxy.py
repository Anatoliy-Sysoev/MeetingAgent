"""Tests for trusted_proxy helper (MA-AUTH-SECRET-STRENGTH-AND-TRUSTED-PROXY #91)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.auth.trusted_proxy import (  # noqa: E402
    is_trusted_proxy,
    parse_trusted_proxy_cidrs,
    resolve_cookie_secure,
    validate_trusted_proxy_cidrs,
)


# ---------------------------------------------------------------------------
# is_trusted_proxy
# ---------------------------------------------------------------------------

def test_is_trusted_proxy_localhost_in_loopback_cidr() -> None:
    assert is_trusted_proxy("127.0.0.1", ["127.0.0.1/32"])


def test_is_trusted_proxy_private_in_10_block() -> None:
    assert is_trusted_proxy("10.0.0.1", ["10.0.0.0/8"])


def test_is_trusted_proxy_not_in_cidr() -> None:
    assert not is_trusted_proxy("8.8.8.8", ["10.0.0.0/8", "192.168.0.0/16"])


def test_is_trusted_proxy_empty_cidrs() -> None:
    assert not is_trusted_proxy("127.0.0.1", [])


def test_is_trusted_proxy_none_host() -> None:
    assert not is_trusted_proxy(None, ["127.0.0.1/32"])


def test_is_trusted_proxy_invalid_host() -> None:
    assert not is_trusted_proxy("not-an-ip", ["127.0.0.1/32"])


def test_is_trusted_proxy_invalid_cidr_skipped() -> None:
    # Bad CIDR is skipped; valid match should still work.
    assert is_trusted_proxy("10.0.0.1", ["not-a-cidr", "10.0.0.0/8"])


# ---------------------------------------------------------------------------
# resolve_cookie_secure
# ---------------------------------------------------------------------------

def test_cookie_secure_true_always_sets_secure_cookie() -> None:
    assert resolve_cookie_secure(
        configured="true",
        request_scheme="http",
        forwarded_proto=None,
        client_host="8.8.8.8",
        trusted_proxy_cidrs=[],
    )


def test_cookie_secure_false_does_not_set_secure_cookie() -> None:
    assert not resolve_cookie_secure(
        configured="false",
        request_scheme="https",
        forwarded_proto="https",
        client_host="127.0.0.1",
        trusted_proxy_cidrs=["127.0.0.1/32"],
    )


def test_cookie_secure_auto_direct_https() -> None:
    assert resolve_cookie_secure(
        configured="auto",
        request_scheme="https",
        forwarded_proto=None,
        client_host=None,
        trusted_proxy_cidrs=[],
    )


def test_cookie_secure_auto_trusts_x_forwarded_proto_from_trusted_proxy() -> None:
    assert resolve_cookie_secure(
        configured="auto",
        request_scheme="http",
        forwarded_proto="https",
        client_host="10.0.0.1",
        trusted_proxy_cidrs=["10.0.0.0/8"],
    )


def test_cookie_secure_auto_ignores_x_forwarded_proto_from_untrusted_client() -> None:
    assert not resolve_cookie_secure(
        configured="auto",
        request_scheme="http",
        forwarded_proto="https",
        client_host="8.8.8.8",
        trusted_proxy_cidrs=["10.0.0.0/8"],
    )


def test_cookie_secure_auto_no_proxy_no_forwarded_no_https() -> None:
    assert not resolve_cookie_secure(
        configured="auto",
        request_scheme="http",
        forwarded_proto=None,
        client_host="127.0.0.1",
        trusted_proxy_cidrs=[],
    )


def test_cookie_secure_auto_empty_forwarded_proto_ignored() -> None:
    assert not resolve_cookie_secure(
        configured="auto",
        request_scheme="http",
        forwarded_proto="",
        client_host="127.0.0.1",
        trusted_proxy_cidrs=["127.0.0.1/32"],
    )


def test_cookie_secure_auto_http_forwarded_proto_from_trusted_proxy_is_false() -> None:
    # Proto is "http", not "https" — so not secure even from a trusted proxy.
    assert not resolve_cookie_secure(
        configured="auto",
        request_scheme="http",
        forwarded_proto="http",
        client_host="10.0.0.1",
        trusted_proxy_cidrs=["10.0.0.0/8"],
    )


# ---------------------------------------------------------------------------
# validate_trusted_proxy_cidrs
# ---------------------------------------------------------------------------

def test_invalid_trusted_proxy_cidr_is_detected() -> None:
    bad = validate_trusted_proxy_cidrs(["not-a-cidr", "127.0.0.1/32"])
    assert bad == ["not-a-cidr"]


def test_valid_cidrs_produce_no_errors() -> None:
    bad = validate_trusted_proxy_cidrs(["127.0.0.1/32", "10.0.0.0/8", "192.168.1.0/24"])
    assert bad == []


def test_empty_cidr_list_is_valid() -> None:
    assert validate_trusted_proxy_cidrs([]) == []


# ---------------------------------------------------------------------------
# parse_trusted_proxy_cidrs
# ---------------------------------------------------------------------------

def test_parse_from_env_string_comma_separated() -> None:
    result = parse_trusted_proxy_cidrs(None, "127.0.0.1/32,10.0.0.0/8")
    assert result == ["127.0.0.1/32", "10.0.0.0/8"]


def test_parse_from_config_list() -> None:
    result = parse_trusted_proxy_cidrs(["127.0.0.1/32", "10.0.0.0/8"], "")
    assert result == ["127.0.0.1/32", "10.0.0.0/8"]


def test_parse_env_takes_priority_over_config() -> None:
    result = parse_trusted_proxy_cidrs(["192.168.0.0/16"], "127.0.0.1/32")
    assert result == ["127.0.0.1/32"]


def test_parse_empty_returns_empty() -> None:
    assert parse_trusted_proxy_cidrs(None, "") == []
    assert parse_trusted_proxy_cidrs([], "") == []
