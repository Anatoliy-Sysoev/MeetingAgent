"""Deployment safety validation for self-hosted MeetingAgent instances.

Validates runtime configuration before the app begins serving requests.
In ``self_hosted`` mode, any ``error``-severity finding raises
``DeploymentSafetyError`` to fail the app startup closed.

Usage::

    findings = validate_deployment_safety(config, os.environ)
    # or let build_app_state() call it automatically.

Deployment modes
----------------
local
    Suitable for a single developer on a local machine.
    Missing/weak settings produce ``warning`` findings but do not block startup.

self_hosted
    LAN, intranet, or public internet exposure.
    Missing/weak required settings produce ``error`` findings and block startup.

Finding codes
-------------
deployment_mode_unknown          Unknown value for deployment mode.
machine_token_missing            MEETINGAGENT_API_TOKEN not set.
machine_token_weak               MEETINGAGENT_API_TOKEN present but too short, placeholder, or low-entropy.
session_cookie_insecure          cookie_secure explicitly set to "false" in self_hosted mode.
trusted_hosts_missing            No explicit self-hosted Host allowlist configured.
bootstrap_policy_unsafe          allow_remote=true but weak/missing bootstrap secret.
trusted_proxy_no_cidrs           cookie_secure=auto in self_hosted but no trusted proxy CIDRs configured.
invalid_trusted_proxy_cidrs      One or more configured trusted_proxy_cidrs are not valid CIDR notation.
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from asu_june_bot.auth.secret_strength import (
    is_placeholder as _is_placeholder,  # noqa: F401 - backward-compatible re-export
    validate_secret_strength,
)
from asu_june_bot.auth.trusted_proxy import (
    load_trusted_proxy_cidrs,
    validate_trusted_proxy_cidrs,
)


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

_Severity = Literal["info", "warning", "error"]

_MIN_TOKEN_BYTES = 32

VALID_MODES = frozenset({"local", "self_hosted"})


@dataclass(frozen=True)
class SafetyFinding:
    """One structured finding from the deployment safety validator."""

    code: str
    severity: _Severity
    message: str
    setting: str | None = None


class DeploymentSafetyError(RuntimeError):
    """Raised at startup when one or more error-severity findings exist.

    The message lists finding codes only — no secret values.
    """

    def __init__(self, findings: list[SafetyFinding]) -> None:
        codes = ", ".join(f.code for f in findings if f.severity == "error")
        super().__init__(
            f"Unsafe deployment configuration — cannot start in self_hosted mode. "
            f"Error finding codes: {codes}. "
            f"Review your .env / config.yaml and correct the highlighted settings."
        )
        self.findings = findings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _deployment_mode(config: dict[str, Any], env: Mapping[str, str]) -> str:
    """Resolve deployment mode: env var > config key > default 'local'."""
    from_env = env.get("MEETINGAGENT_DEPLOYMENT_MODE", "").strip().lower()
    if from_env:
        return from_env
    from_cfg = (config.get("deployment") or {}).get("mode", "")
    if isinstance(from_cfg, str) and from_cfg.strip():
        return from_cfg.strip().lower()
    return "local"


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def _check_mode(mode: str) -> list[SafetyFinding]:
    if mode not in VALID_MODES:
        return [SafetyFinding(
            code="deployment_mode_unknown",
            severity="error",
            message=(
                f"Unknown deployment mode '{mode}'. "
                f"Set MEETINGAGENT_DEPLOYMENT_MODE to 'local' or 'self_hosted'."
            ),
            setting="MEETINGAGENT_DEPLOYMENT_MODE",
        )]
    return []


def _check_machine_token(
    env: Mapping[str, str], mode: str
) -> list[SafetyFinding]:
    findings: list[SafetyFinding] = []
    token = env.get("MEETINGAGENT_API_TOKEN", "").strip()

    if not token:
        sev: _Severity = "error" if mode == "self_hosted" else "warning"
        findings.append(SafetyFinding(
            code="machine_token_missing",
            severity=sev,
            message=(
                "MEETINGAGENT_API_TOKEN is not set. "
                "Machine API access will be unavailable or insecure."
            ),
            setting="MEETINGAGENT_API_TOKEN",
        ))
        return findings

    strength = validate_secret_strength(token, min_length=_MIN_TOKEN_BYTES)
    if not strength.ok:
        sev = "error" if mode == "self_hosted" else "warning"
        findings.append(SafetyFinding(
            code="machine_token_weak",
            severity=sev,
            # Never include the token value in the message.
            message=(
                f"MEETINGAGENT_API_TOKEN does not meet security requirements. "
                f"{strength.reason} "
                f"Set a strong random token of at least {_MIN_TOKEN_BYTES} characters."
            ),
            setting="MEETINGAGENT_API_TOKEN",
        ))

    return findings


def _check_cookie_security(
    config: dict[str, Any], mode: str
) -> list[SafetyFinding]:
    findings: list[SafetyFinding] = []
    auth_cfg = config.get("auth") or {}
    cookie_secure = str(auth_cfg.get("cookie_secure") or "auto").strip().lower()

    if cookie_secure == "false" and mode == "self_hosted":
        findings.append(SafetyFinding(
            code="session_cookie_insecure",
            severity="error",
            message=(
                "auth.cookie_secure is set to 'false' in self_hosted mode. "
                "Browser sessions will not use the Secure cookie flag. "
                "Set cookie_secure to 'auto' (HTTPS-detected) or 'true'."
            ),
            setting="auth.cookie_secure",
        ))
    elif cookie_secure == "false" and mode == "local":
        findings.append(SafetyFinding(
            code="session_cookie_insecure",
            severity="info",
            message=(
                "auth.cookie_secure is 'false'. "
                "Acceptable for local development; not safe for self-hosted."
            ),
            setting="auth.cookie_secure",
        ))

    return findings


def _check_cors_hosts(
    config: dict[str, Any], env: Mapping[str, str], mode: str
) -> list[SafetyFinding]:
    """Require an explicit TrustedHost policy for self-hosted deployments."""
    findings: list[SafetyFinding] = []
    security_cfg = config.get("security") or {}
    has_hosts = bool(
        security_cfg.get("allowed_hosts")
        or str(env.get("MEETINGAGENT_ALLOWED_HOSTS") or "").strip()
    )

    if mode == "self_hosted" and not has_hosts:
        findings.append(SafetyFinding(
            code="trusted_hosts_missing",
            severity="error",
            message=(
                "No security.allowed_hosts or MEETINGAGENT_ALLOWED_HOSTS are configured. "
                "Self-hosted mode requires an explicit host allowlist in addition to "
                "the built-in localhost defaults."
            ),
            setting="security.allowed_hosts / MEETINGAGENT_ALLOWED_HOSTS",
        ))

    return findings


def _check_bootstrap_policy(
    config: dict[str, Any], env: Mapping[str, str], mode: str
) -> list[SafetyFinding]:
    findings: list[SafetyFinding] = []
    auth_cfg = config.get("auth") or {}
    bootstrap_cfg = auth_cfg.get("bootstrap") or {}

    allow_remote_cfg = bootstrap_cfg.get("allow_remote", False)
    allow_remote_env = env.get("MEETINGAGENT_BOOTSTRAP_ALLOW_REMOTE", "").strip().lower()
    allow_remote = allow_remote_env in ("1", "true", "yes") or bool(allow_remote_cfg)

    if not allow_remote:
        return findings  # local-only bootstrap is safe by default

    secret = env.get("MEETINGAGENT_BOOTSTRAP_SECRET", "").strip()
    if not secret:
        findings.append(SafetyFinding(
            code="bootstrap_policy_unsafe",
            severity="error",
            message=(
                "Remote bootstrap is enabled (MEETINGAGENT_BOOTSTRAP_ALLOW_REMOTE=true) "
                "but MEETINGAGENT_BOOTSTRAP_SECRET is not set. "
                "Any remote caller could create the first admin account."
            ),
            setting="MEETINGAGENT_BOOTSTRAP_SECRET",
        ))
    else:
        # Use validate_secret_strength for full low-entropy detection.
        strength = validate_secret_strength(secret, min_length=32)
        if not strength.ok:
            findings.append(SafetyFinding(
                code="bootstrap_policy_unsafe",
                severity="error",
                # Never include the secret value in the message.
                message=(
                    f"Remote bootstrap is enabled but MEETINGAGENT_BOOTSTRAP_SECRET "
                    f"does not meet security requirements. {strength.reason} "
                    "Set a strong random value of at least 32 characters."
                ),
                setting="MEETINGAGENT_BOOTSTRAP_SECRET",
            ))

    return findings


def _check_trusted_proxy_policy(
    config: dict[str, Any], env: Mapping[str, str], mode: str
) -> list[SafetyFinding]:
    """Warn when cookie_secure=auto without trusted proxy CIDRs in self_hosted.

    Also raise an error for invalid CIDR notation in any mode.
    """
    findings: list[SafetyFinding] = []

    cidrs = load_trusted_proxy_cidrs(config, env)

    bad_cidrs = validate_trusted_proxy_cidrs(cidrs)
    if bad_cidrs:
        findings.append(SafetyFinding(
            code="invalid_trusted_proxy_cidrs",
            severity="error",
            message=(
                f"security.trusted_proxy_cidrs contains {len(bad_cidrs)} invalid "
                "CIDR notation value(s). Correct or remove them before starting."
            ),
            setting="security.trusted_proxy_cidrs",
        ))
        return findings

    if mode != "self_hosted":
        return findings

    auth_cfg = config.get("auth") or {}
    cookie_secure = str(auth_cfg.get("cookie_secure") or "auto").strip().lower()

    if cookie_secure == "auto" and not cidrs:
        findings.append(SafetyFinding(
            code="trusted_proxy_no_cidrs",
            severity="warning",
            message=(
                "auth.cookie_secure is 'auto' in self_hosted mode but no "
                "security.trusted_proxy_cidrs are configured. "
                "X-Forwarded-Proto from untrusted clients will be ignored. "
                "Configure trusted_proxy_cidrs to enable HTTPS detection via reverse proxy, "
                "or set auth.cookie_secure to 'true' for always-Secure cookies."
            ),
            setting="security.trusted_proxy_cidrs",
        ))

    return findings


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------

def validate_deployment_safety(
    config: dict[str, Any],
    env: Mapping[str, str] | None = None,
) -> list[SafetyFinding]:
    """Return all safety findings for the given config + environment.

    Does not raise.  The caller is responsible for deciding whether to
    fail startup based on the returned findings.

    Args:
        config: Loaded application config dict (from load_config()).
        env:    Environment mapping (default: ``os.environ``).

    Returns:
        Ordered list of ``SafetyFinding`` objects.
    """
    if env is None:
        env = os.environ

    findings: list[SafetyFinding] = []
    mode = _deployment_mode(config, env)

    findings.extend(_check_mode(mode))
    # If mode is unknown, skip further checks (they'd all be based on the wrong mode).
    if any(f.code == "deployment_mode_unknown" for f in findings):
        return findings

    findings.extend(_check_machine_token(env, mode))
    findings.extend(_check_cookie_security(config, mode))
    findings.extend(_check_cors_hosts(config, env, mode))
    findings.extend(_check_bootstrap_policy(config, env, mode))
    findings.extend(_check_trusted_proxy_policy(config, env, mode))

    return findings


def check_and_fail_if_unsafe(
    config: dict[str, Any],
    env: Mapping[str, str] | None = None,
) -> list[SafetyFinding]:
    """Run validation and raise ``DeploymentSafetyError`` if any errors exist.

    In ``self_hosted`` mode, error-severity findings abort startup.
    In ``local`` mode, findings are returned for logging but never raise.
    Always safe to call — exceptions are only raised on genuine misconfig.
    """
    if env is None:
        env = os.environ

    findings = validate_deployment_safety(config, env)
    mode = _deployment_mode(config, env)

    errors = [f for f in findings if f.severity == "error"]
    has_unknown_mode = any(f.code == "deployment_mode_unknown" for f in findings)
    if has_unknown_mode or (errors and mode == "self_hosted"):
        raise DeploymentSafetyError(findings)

    return findings
