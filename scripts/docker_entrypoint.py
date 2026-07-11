from __future__ import annotations

import ipaddress
import os
import sys


def _is_loopback_bind(value: str) -> bool:
    host = value.strip().strip("[]").lower()
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def validate_publish_policy(env: dict[str, str] | None = None) -> None:
    """Require fail-closed application policy before Compose exposes a LAN port."""
    values = os.environ if env is None else env
    bind_host = values.get("MEETINGAGENT_BIND_HOST", "127.0.0.1").strip()
    deployment_mode = values.get("MEETINGAGENT_DEPLOYMENT_MODE", "local").strip().lower()
    if not _is_loopback_bind(bind_host) and deployment_mode != "self_hosted":
        raise RuntimeError(
            "Non-loopback MEETINGAGENT_BIND_HOST requires "
            "MEETINGAGENT_DEPLOYMENT_MODE=self_hosted"
        )


def main(argv: list[str] | None = None) -> int:
    command = list(sys.argv[1:] if argv is None else argv)
    if not command:
        raise SystemExit("Container command is required")
    try:
        validate_publish_policy()
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    os.execvp(command[0], command)
    return 0  # pragma: no cover - os.execvp replaces the process


if __name__ == "__main__":
    raise SystemExit(main())
