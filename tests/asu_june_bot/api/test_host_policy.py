from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.api.app import create_app  # noqa: E402
from asu_june_bot.api.host_policy import (  # noqa: E402
    build_allowed_hosts,
    host_is_allowed,
    is_local_host_header,
    normalize_host_header,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("localhost", "localhost"),
        ("LOCALHOST:8000", "localhost"),
        ("localhost.", "localhost"),
        ("127.0.0.1:8000", "127.0.0.1"),
        ("[::1]:8000", "::1"),
        ("::1", "::1"),
        ("[::ffff:127.0.0.1]", "::ffff:127.0.0.1"),
    ],
)
def test_normalize_host_header(raw: str, expected: str) -> None:
    assert normalize_host_header(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "attacker.example/path",
        "user@localhost",
        "localhost:bad-port",
        "localhost\r\nX-Evil: yes",
        "local host",
    ],
)
def test_normalize_host_header_rejects_invalid_values(raw: str) -> None:
    assert normalize_host_header(raw) is None


@pytest.mark.parametrize(
    "raw",
    ["localhost", "localhost:8000", "127.0.0.1", "[::1]:8000", "::ffff:127.0.0.1"],
)
def test_local_host_header_accepts_only_loopback_names(raw: str) -> None:
    assert is_local_host_header(raw) is True


@pytest.mark.parametrize("raw", ["attacker.example", "127.0.0.1.evil", "testserver", None])
def test_local_host_header_rejects_nonlocal_values(raw: str | None) -> None:
    assert is_local_host_header(raw) is False


def test_build_allowed_hosts_includes_defaults_and_configured_hosts() -> None:
    hosts = build_allowed_hosts(
        {"security": {"allowed_hosts": ["app.example", "*.internal.example"]}},
        {},
    )

    assert "localhost" in hosts
    assert "::1" in hosts
    assert "app.example" in hosts
    assert "*.internal.example" in hosts
    assert host_is_allowed("node.internal.example", hosts) is True
    assert host_is_allowed("internal.example", hosts) is False


def test_environment_allowed_hosts_override_config() -> None:
    hosts = build_allowed_hosts(
        {"security": {"allowed_hosts": ["config.example"]}},
        {"MEETINGAGENT_ALLOWED_HOSTS": "env.example, *.svc.example"},
    )

    assert "env.example" in hosts
    assert "*.svc.example" in hosts
    assert "config.example" not in hosts


@pytest.mark.parametrize(
    "configured",
    ["*", "bad/path", "localhost:8000", "foo.*.example", 123, ""],
)
def test_build_allowed_hosts_rejects_unsafe_entries(configured) -> None:
    with pytest.raises(ValueError):
        build_allowed_hosts({"security": {"allowed_hosts": [configured]}}, {})


def test_middleware_rejects_host_not_in_allowlist() -> None:
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.get("/", headers={"Host": "attacker.example"})

    assert response.status_code == 400
    assert response.text == "Invalid host header"


def test_middleware_rejects_duplicate_host_headers() -> None:
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.get(
        "/",
        headers=[("Host", "localhost"), ("Host", "attacker.example")],
    )

    assert response.status_code == 400


@pytest.mark.parametrize("host", ["localhost:8000", "127.0.0.1:8000", "[::1]:8000"])
def test_middleware_accepts_local_hosts_with_ports(host: str) -> None:
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.get("/", headers={"Host": host})

    assert response.status_code == 200


def test_middleware_accepts_configured_self_hosted_host() -> None:
    client = TestClient(
        create_app(config={"security": {"allowed_hosts": ["meeting.example"]}}),
        raise_server_exceptions=False,
    )

    response = client.get("/", headers={"Host": "meeting.example"})

    assert response.status_code == 200
