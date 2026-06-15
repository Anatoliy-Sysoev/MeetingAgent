from __future__ import annotations

"""Bootstrap safety policy for self-hosted deployments.

Local requests (127.0.0.1, ::1) are always permitted for first-run bootstrap.
Non-local requests require explicit operator opt-in via:
  - MEETINGAGENT_BOOTSTRAP_ALLOW_REMOTE=true  (or auth.bootstrap.allow_remote in config)
  - MEETINGAGENT_BOOTSTRAP_SECRET=<secret>    (or auth.bootstrap.secret in config)
  - X-Bootstrap-Token: <secret> header on the request

The direct peer address (request.client.host) is used — never X-Forwarded-For,
which cannot be trusted for this security decision.
"""

import os
import secrets
from dataclasses import dataclass
from typing import Any

BOOTSTRAP_TOKEN_HEADER = "X-Bootstrap-Token"

_LOCALHOST_HOSTS: frozenset[str] = frozenset({"127.0.0.1", "::1", "::ffff:127.0.0.1"})


@dataclass(frozen=True, slots=True)
class BootstrapPolicy:
    """Immutable bootstrap safety policy loaded at startup."""

    allow_remote: bool = False
    secret: str = ""

    def is_secret_configured(self) -> bool:
        return bool(self.secret)

    def verify_secret(self, provided: str) -> bool:
        """Constant-time comparison. Returns False if no secret is configured."""
        if not self.secret:
            return False
        return secrets.compare_digest(self.secret, provided)


def is_local_request(host: str | None) -> bool:
    """Return True if the direct peer address is a loopback address.

    Never reads X-Forwarded-For or any proxy header — the caller must pass the
    raw ASGI scope client host.
    """
    return bool(host) and host in _LOCALHOST_HOSTS


def build_bootstrap_policy(auth_cfg: dict[str, Any] | None) -> BootstrapPolicy:
    """Build BootstrapPolicy from config dict and environment variable overrides.

    Environment variables override config.yaml values.
    Raises ValueError for invalid or insecure configurations (e.g. allow_remote
    without a secret), so the API fails fast at startup rather than silently
    allowing a misconfigured insecure endpoint.
    """
    bootstrap_cfg: dict[str, Any] = {}
    if isinstance(auth_cfg, dict):
        raw = auth_cfg.get("bootstrap")
        if isinstance(raw, dict):
            bootstrap_cfg = raw

    # allow_remote
    env_allow = os.environ.get("MEETINGAGENT_BOOTSTRAP_ALLOW_REMOTE", "").strip().lower()
    if env_allow in ("1", "true", "yes"):
        allow_remote = True
    elif env_allow in ("0", "false", "no"):
        allow_remote = False
    elif env_allow == "":
        cfg_val = bootstrap_cfg.get("allow_remote", False)
        if not isinstance(cfg_val, bool):
            raise ValueError(
                f"Invalid auth.bootstrap.allow_remote: {cfg_val!r} (must be a boolean)"
            )
        allow_remote = cfg_val
    else:
        raise ValueError(
            f"Invalid MEETINGAGENT_BOOTSTRAP_ALLOW_REMOTE: {env_allow!r} "
            "(accepted values: true/1/yes or false/0/no)"
        )

    # secret
    env_secret = os.environ.get("MEETINGAGENT_BOOTSTRAP_SECRET", "").strip()
    if env_secret:
        secret = env_secret
    else:
        cfg_secret = bootstrap_cfg.get("secret")
        secret = str(cfg_secret).strip() if cfg_secret is not None else ""

    # Security invariant: remote bootstrap requires a secret.
    if allow_remote and not secret:
        raise ValueError(
            "auth.bootstrap.allow_remote is true but no bootstrap secret is configured. "
            "Set MEETINGAGENT_BOOTSTRAP_SECRET or auth.bootstrap.secret in config.yaml."
        )

    return BootstrapPolicy(allow_remote=allow_remote, secret=secret)
