from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from docker_entrypoint import _is_loopback_bind, validate_publish_policy  # noqa: E402


def test_dockerfile_uses_explicit_copy_and_non_root_runtime() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "COPY . /app" not in dockerfile
    assert "COPY src /app/src" in dockerfile
    assert "COPY scripts /app/scripts" in dockerfile
    assert "USER meetingagent:meetingagent" in dockerfile
    assert "ENV HOME=/app/data/home" in dockerfile
    assert 'ENTRYPOINT ["python", "scripts/docker_entrypoint.py"]' in dockerfile


def test_dockerignore_is_deny_by_default_with_runtime_allowlist() -> None:
    lines = [
        line.strip()
        for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]

    assert lines[0] == "**"
    assert "!src/**/*.py" in lines
    assert "!scripts/**/*.py" in lines
    assert "!configs/**/*.yaml" in lines
    assert "configs/asu_june_bot/*.local.yaml" in lines
    assert "!.env" not in lines


def test_runtime_requirements_exclude_test_tools() -> None:
    runtime = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    dev = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8").lower()

    assert "pytest" not in runtime
    assert "pytest" in dev
    assert "-r requirements.txt" in dev


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "::1", "[::1]"])
def test_loopback_publish_hosts_are_local(host: str) -> None:
    assert _is_loopback_bind(host) is True
    validate_publish_policy({"MEETINGAGENT_BIND_HOST": host})


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.20", "meeting.internal"])
def test_non_loopback_publish_requires_self_hosted_mode(host: str) -> None:
    with pytest.raises(RuntimeError, match="self_hosted"):
        validate_publish_policy(
            {
                "MEETINGAGENT_BIND_HOST": host,
                "MEETINGAGENT_DEPLOYMENT_MODE": "local",
            }
        )


def test_non_loopback_publish_is_allowed_only_after_explicit_opt_in() -> None:
    validate_publish_policy(
        {
            "MEETINGAGENT_BIND_HOST": "0.0.0.0",
            "MEETINGAGENT_DEPLOYMENT_MODE": "self_hosted",
        }
    )


def test_compose_binds_localhost_and_hardens_services() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "${MEETINGAGENT_BIND_HOST:-127.0.0.1}" in compose
    assert compose.count("read_only: true") == 3
    assert compose.count("no-new-privileges:true") == 3
    assert compose.count("cap_drop:") == 3
    assert "container_name:" not in compose
