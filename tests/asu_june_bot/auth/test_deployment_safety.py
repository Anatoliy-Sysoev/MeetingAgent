"""Tests for deployment safety validation (MA-AUTH-DEPLOYMENT-SAFETY-V2).

Covers:
- Deployment mode resolution (env / config / default)
- Machine token checks: missing, placeholder, weak, strong
- Cookie security checks
- CORS/hosts warning
- Bootstrap policy checks
- Local vs self_hosted severity differences
- DeploymentSafetyError raised on self_hosted errors
- Secret redaction (token value never in finding messages)
- Admin /admin/security/status endpoint
- Regression: existing auth/RBAC/CSRF behavior unchanged
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.auth.deployment_safety import (  # noqa: E402
    DeploymentSafetyError,
    SafetyFinding,
    _deployment_mode,
    _is_placeholder,
    check_and_fail_if_unsafe,
    validate_deployment_safety,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

STRONG_TOKEN = "r7NQx4vP9zK2mT6aY8sD3fG5hJ1kL0pW"  # random-looking, passes entropy checks

def _env(**kwargs: str) -> dict[str, str]:
    return {k: v for k, v in kwargs.items()}

def _finding_codes(findings: list[SafetyFinding]) -> list[str]:
    return [f.code for f in findings]

def _error_codes(findings: list[SafetyFinding]) -> list[str]:
    return [f.code for f in findings if f.severity == "error"]

def _warning_codes(findings: list[SafetyFinding]) -> list[str]:
    return [f.code for f in findings if f.severity == "warning"]


# ===========================================================================
# 1. Deployment mode resolution
# ===========================================================================

def test_default_mode_is_local() -> None:
    mode = _deployment_mode({}, {})
    assert mode == "local"


def test_env_var_sets_mode() -> None:
    assert _deployment_mode({}, {"MEETINGAGENT_DEPLOYMENT_MODE": "self_hosted"}) == "self_hosted"
    assert _deployment_mode({}, {"MEETINGAGENT_DEPLOYMENT_MODE": "local"}) == "local"


def test_env_var_takes_priority_over_config() -> None:
    cfg = {"deployment": {"mode": "self_hosted"}}
    assert _deployment_mode(cfg, {"MEETINGAGENT_DEPLOYMENT_MODE": "local"}) == "local"


def test_config_key_sets_mode_when_no_env() -> None:
    cfg = {"deployment": {"mode": "self_hosted"}}
    assert _deployment_mode(cfg, {}) == "self_hosted"


def test_mode_is_normalised_lowercase() -> None:
    assert _deployment_mode({}, {"MEETINGAGENT_DEPLOYMENT_MODE": "Self_Hosted"}) == "self_hosted"


def test_unknown_mode_produces_error_finding() -> None:
    findings = validate_deployment_safety({}, {"MEETINGAGENT_DEPLOYMENT_MODE": "cloud"})
    assert "deployment_mode_unknown" in _error_codes(findings)


def test_unknown_mode_stops_further_checks() -> None:
    """When mode is unknown, no further checks run (findings list is short)."""
    env = {"MEETINGAGENT_DEPLOYMENT_MODE": "cloud", "MEETINGAGENT_API_TOKEN": ""}
    findings = validate_deployment_safety({}, env)
    # Only the unknown-mode finding, not a cascade.
    assert len(findings) == 1


# ===========================================================================
# 2. Machine token checks
# ===========================================================================

def test_missing_token_is_warning_in_local() -> None:
    findings = validate_deployment_safety({}, {})
    assert "machine_token_missing" in _warning_codes(findings)
    assert "machine_token_missing" not in _error_codes(findings)


def test_missing_token_is_error_in_self_hosted() -> None:
    env = {"MEETINGAGENT_DEPLOYMENT_MODE": "self_hosted"}
    findings = validate_deployment_safety({}, env)
    assert "machine_token_missing" in _error_codes(findings)


def test_placeholder_token_is_warning_in_local() -> None:
    env = {"MEETINGAGENT_API_TOKEN": "<strong-random>"}
    findings = validate_deployment_safety({}, env)
    assert "machine_token_weak" in _warning_codes(findings)


def test_placeholder_token_is_error_in_self_hosted() -> None:
    env = {
        "MEETINGAGENT_DEPLOYMENT_MODE": "self_hosted",
        "MEETINGAGENT_API_TOKEN": "<strong-random>",
    }
    findings = validate_deployment_safety({}, env)
    assert "machine_token_weak" in _error_codes(findings)


def test_short_token_is_error_in_self_hosted() -> None:
    env = {
        "MEETINGAGENT_DEPLOYMENT_MODE": "self_hosted",
        "MEETINGAGENT_API_TOKEN": "short",
    }
    findings = validate_deployment_safety({}, env)
    assert "machine_token_weak" in _error_codes(findings)


def test_short_token_is_warning_in_local() -> None:
    env = {"MEETINGAGENT_API_TOKEN": "short"}
    findings = validate_deployment_safety({}, env)
    assert "machine_token_weak" in _warning_codes(findings)


def test_strong_token_produces_no_token_finding() -> None:
    for mode in ("local", "self_hosted"):
        env = {
            "MEETINGAGENT_DEPLOYMENT_MODE": mode,
            "MEETINGAGENT_API_TOKEN": STRONG_TOKEN,
        }
        codes = _finding_codes(validate_deployment_safety({}, env))
        assert "machine_token_missing" not in codes
        assert "machine_token_weak" not in codes


@pytest.mark.parametrize("placeholder", [
    "<strong-random>",
    "changeme",
    "placeholder",
    "your-token",
    "your_token",
    "example",
    "secret",
    "test-token",
    "TODO",
    "fixme",
    "replace-me",
])
def test_placeholder_patterns_are_detected(placeholder: str) -> None:
    assert _is_placeholder(placeholder), f"Expected '{placeholder}' to be a placeholder"


def test_finding_message_does_not_contain_token_value() -> None:
    """Token value must never appear in finding messages."""
    token_value = "SUPER_SECRET_DO_NOT_LOG_THIS_TOKEN_VALUE_XYZ"
    for mode in ("local", "self_hosted"):
        env = {
            "MEETINGAGENT_DEPLOYMENT_MODE": mode,
            "MEETINGAGENT_API_TOKEN": token_value,
        }
        findings = validate_deployment_safety({}, env)
        for f in findings:
            assert token_value not in f.message, (
                f"Token value leaked in finding '{f.code}': {f.message}"
            )


def test_finding_setting_names_token_env_var() -> None:
    env = {"MEETINGAGENT_DEPLOYMENT_MODE": "self_hosted"}
    findings = validate_deployment_safety({}, env)
    token_findings = [f for f in findings if "token" in f.code]
    assert token_findings
    assert all(f.setting == "MEETINGAGENT_API_TOKEN" for f in token_findings)


# ===========================================================================
# 3. Cookie security checks
# ===========================================================================

def test_cookie_secure_false_is_info_in_local() -> None:
    cfg = {"auth": {"cookie_secure": "false"}}
    findings = validate_deployment_safety(cfg, {})
    assert any(f.code == "session_cookie_insecure" and f.severity == "info" for f in findings)


def test_cookie_secure_false_is_error_in_self_hosted() -> None:
    cfg = {"auth": {"cookie_secure": "false"}}
    env = {"MEETINGAGENT_DEPLOYMENT_MODE": "self_hosted", "MEETINGAGENT_API_TOKEN": STRONG_TOKEN}
    findings = validate_deployment_safety(cfg, env)
    assert "session_cookie_insecure" in _error_codes(findings)


def test_cookie_secure_auto_no_finding() -> None:
    for mode in ("local", "self_hosted"):
        cfg = {"auth": {"cookie_secure": "auto"}}
        env = {"MEETINGAGENT_DEPLOYMENT_MODE": mode, "MEETINGAGENT_API_TOKEN": STRONG_TOKEN}
        codes = _finding_codes(validate_deployment_safety(cfg, env))
        assert "session_cookie_insecure" not in codes


def test_cookie_secure_true_no_finding() -> None:
    cfg = {"auth": {"cookie_secure": "true"}}
    env = {"MEETINGAGENT_DEPLOYMENT_MODE": "self_hosted", "MEETINGAGENT_API_TOKEN": STRONG_TOKEN}
    codes = _finding_codes(validate_deployment_safety(cfg, env))
    assert "session_cookie_insecure" not in codes


# ===========================================================================
# 4. CORS / host checks
# ===========================================================================

def test_no_allowed_hosts_is_error_in_self_hosted() -> None:
    env = {"MEETINGAGENT_DEPLOYMENT_MODE": "self_hosted", "MEETINGAGENT_API_TOKEN": STRONG_TOKEN}
    findings = validate_deployment_safety({}, env)
    assert "trusted_hosts_missing" in _error_codes(findings)


def test_no_allowed_hosts_not_finding_in_local() -> None:
    findings = validate_deployment_safety({}, {"MEETINGAGENT_API_TOKEN": STRONG_TOKEN})
    codes = _finding_codes(findings)
    assert "trusted_hosts_missing" not in codes


def test_allowed_hosts_satisfies_self_hosted_policy() -> None:
    cfg = {"security": {"allowed_hosts": ["example.internal"]}}
    env = {"MEETINGAGENT_DEPLOYMENT_MODE": "self_hosted", "MEETINGAGENT_API_TOKEN": STRONG_TOKEN}
    codes = _finding_codes(validate_deployment_safety(cfg, env))
    assert "trusted_hosts_missing" not in codes


def test_allowed_origins_do_not_replace_host_policy() -> None:
    cfg = {"security": {"allowed_origins": ["https://example.internal"]}}
    env = {"MEETINGAGENT_DEPLOYMENT_MODE": "self_hosted", "MEETINGAGENT_API_TOKEN": STRONG_TOKEN}
    codes = _finding_codes(validate_deployment_safety(cfg, env))
    assert "trusted_hosts_missing" in codes


def test_allowed_hosts_environment_satisfies_self_hosted_policy() -> None:
    env = {
        "MEETINGAGENT_DEPLOYMENT_MODE": "self_hosted",
        "MEETINGAGENT_API_TOKEN": STRONG_TOKEN,
        "MEETINGAGENT_ALLOWED_HOSTS": "meeting.example",
    }

    codes = _finding_codes(validate_deployment_safety({}, env))

    assert "trusted_hosts_missing" not in codes


def test_self_hosted_without_allowed_hosts_fails_startup() -> None:
    env = {
        "MEETINGAGENT_DEPLOYMENT_MODE": "self_hosted",
        "MEETINGAGENT_API_TOKEN": STRONG_TOKEN,
    }
    cfg = {"auth": {"cookie_secure": "true"}}

    with pytest.raises(DeploymentSafetyError) as exc_info:
        check_and_fail_if_unsafe(cfg, env)

    assert "trusted_hosts_missing" in str(exc_info.value)


# ===========================================================================
# 5. Bootstrap policy checks
# ===========================================================================

def test_local_only_bootstrap_no_finding() -> None:
    findings = validate_deployment_safety({}, {})
    assert "bootstrap_policy_unsafe" not in _finding_codes(findings)


def test_allow_remote_without_secret_is_error() -> None:
    env = {"MEETINGAGENT_BOOTSTRAP_ALLOW_REMOTE": "true"}
    findings = validate_deployment_safety({}, env)
    assert "bootstrap_policy_unsafe" in _error_codes(findings)


def test_allow_remote_with_short_secret_is_error() -> None:
    env = {
        "MEETINGAGENT_BOOTSTRAP_ALLOW_REMOTE": "true",
        "MEETINGAGENT_BOOTSTRAP_SECRET": "tooshort",
    }
    findings = validate_deployment_safety({}, env)
    assert "bootstrap_policy_unsafe" in _error_codes(findings)


def test_allow_remote_with_placeholder_secret_is_error() -> None:
    env = {
        "MEETINGAGENT_BOOTSTRAP_ALLOW_REMOTE": "true",
        "MEETINGAGENT_BOOTSTRAP_SECRET": "<strong-random>",
    }
    findings = validate_deployment_safety({}, env)
    assert "bootstrap_policy_unsafe" in _error_codes(findings)


def test_allow_remote_with_strong_secret_no_bootstrap_finding() -> None:
    env = {
        "MEETINGAGENT_BOOTSTRAP_ALLOW_REMOTE": "true",
        "MEETINGAGENT_BOOTSTRAP_SECRET": "Xq2A9mP7vR4tY8nB6cD1eF3gH5jK0sLz",
    }
    findings = validate_deployment_safety({}, env)
    assert "bootstrap_policy_unsafe" not in _finding_codes(findings)


def test_bootstrap_secret_value_not_in_finding_message() -> None:
    secret_value = "BOOTSTRAP_SECRET_VALUE_DO_NOT_LOG_XYZ_123456"
    env = {
        "MEETINGAGENT_BOOTSTRAP_ALLOW_REMOTE": "true",
        "MEETINGAGENT_BOOTSTRAP_SECRET": secret_value,
    }
    findings = validate_deployment_safety({}, env)
    for f in findings:
        assert secret_value not in f.message


# ===========================================================================
# 6. check_and_fail_if_unsafe
# ===========================================================================

def test_safe_config_does_not_raise() -> None:
    env = {
        "MEETINGAGENT_DEPLOYMENT_MODE": "self_hosted",
        "MEETINGAGENT_API_TOKEN": STRONG_TOKEN,
        "MEETINGAGENT_BOOTSTRAP_ALLOW_REMOTE": "false",
    }
    cfg = {
        "auth": {"cookie_secure": "auto"},
        "security": {"allowed_hosts": ["internal.example"]},
    }
    findings = check_and_fail_if_unsafe(cfg, env)
    errors = [f for f in findings if f.severity == "error"]
    assert not errors


def test_unsafe_self_hosted_raises_deployment_safety_error() -> None:
    env = {
        "MEETINGAGENT_DEPLOYMENT_MODE": "self_hosted",
        # No token → error
    }
    with pytest.raises(DeploymentSafetyError) as exc_info:
        check_and_fail_if_unsafe({}, env)
    assert "machine_token_missing" in str(exc_info.value)


def test_deployment_safety_error_does_not_expose_secrets() -> None:
    """DeploymentSafetyError message must not include token or secret values."""
    secret = "REAL_SECRET_VALUE_DO_NOT_EXPOSE"
    env = {
        "MEETINGAGENT_DEPLOYMENT_MODE": "self_hosted",
        "MEETINGAGENT_API_TOKEN": secret,  # short token (weak) — triggers error
        "MEETINGAGENT_BOOTSTRAP_SECRET": secret,  # triggers bootstrap error
        "MEETINGAGENT_BOOTSTRAP_ALLOW_REMOTE": "true",
    }
    with pytest.raises(DeploymentSafetyError) as exc_info:
        check_and_fail_if_unsafe({}, env)
    msg = str(exc_info.value)
    assert secret not in msg


def test_unknown_mode_raises_deployment_safety_error() -> None:
    env = {
        "MEETINGAGENT_DEPLOYMENT_MODE": "cloud",
        "MEETINGAGENT_API_TOKEN": STRONG_TOKEN,
    }
    with pytest.raises(DeploymentSafetyError) as exc_info:
        check_and_fail_if_unsafe({}, env)
    msg = str(exc_info.value)
    assert "deployment_mode_unknown" in msg
    assert "cloud" not in msg  # raw mode value must not appear in exception message


def test_local_mode_never_raises_even_with_weak_config() -> None:
    """Local dev startup must not break even when config is not production-ready."""
    findings = check_and_fail_if_unsafe({}, {})  # missing token, no mode → local
    warnings = [f for f in findings if f.severity == "warning"]
    assert warnings  # findings exist, but no exception


def test_findings_are_structured() -> None:
    env = {"MEETINGAGENT_DEPLOYMENT_MODE": "self_hosted"}
    findings = validate_deployment_safety({}, env)
    assert findings
    for f in findings:
        assert isinstance(f, SafetyFinding)
        assert f.code
        assert f.severity in ("info", "warning", "error")
        assert f.message


# ===========================================================================
# 7. Admin /admin/security/status endpoint
# ===========================================================================

TOKEN = "test-deploy-safety-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}

VALID_CARD = {
    "schema_version": 1,
    "meeting_id": "2026-01-01__deploy-test",
    "title": "Deploy Test",
    "date": "2026-01-01",
    "processing_status": "new",
    "participants": [],
    "source": {"kind": "offline_record"},
    "artifacts": {},
    "classification": {},
    "links": {},
    "retention": {"policy": "default"},
    "rag": {"index_policy": "structured_artifacts_and_final_transcript"},
    "created_at": "2026-01-01T10:00:00+00:00",
    "updated_at": "2026-01-01T10:00:00+00:00",
}


@dataclass(slots=True)
class FakeState:
    config: dict
    meetings_service: object
    job_runner: object
    local_auth_service: object
    admin_service: object
    login_throttle: object = field(default_factory=object)
    search_service: object = field(default_factory=object)
    health_service: object = field(default_factory=object)
    chat_service: object = field(default_factory=object)
    meeting_qa_service: object = field(default_factory=object)
    auth_repository: object = field(default_factory=object)
    bootstrap_policy: object = field(default_factory=object)
    trusted_proxy_cidrs: list = field(default_factory=list)


def _make_admin_client(tmp_path: Path, *, config: dict | None = None) -> tuple[TestClient, object]:
    """Create a TestClient with an admin user logged in."""
    from asu_june_bot.api.app import create_app
    from asu_june_bot.auth.repository import AuthRepository
    from asu_june_bot.auth.service import AdminService, LocalAuthService
    from asu_june_bot.auth.throttle import LoginThrottle
    from asu_june_bot.meetings.service import MeetingsService
    from asu_june_bot.jobs.runner import JobRunner

    os.environ["MEETINGAGENT_API_TOKEN"] = TOKEN
    repo = AuthRepository(tmp_path / "auth.db")
    repo.initialize()
    admin_svc = AdminService(repo)
    svc = LocalAuthService(repo)
    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)
    app.state.asu_june_bot = FakeState(
        config=config or {},
        meetings_service=MeetingsService(tmp_path / "meetings"),
        job_runner=JobRunner(),
        local_auth_service=svc,
        admin_service=admin_svc,
        login_throttle=LoginThrottle(),
    )
    return client, admin_svc


def test_security_status_requires_auth(tmp_path: Path) -> None:
    client, _ = _make_admin_client(tmp_path)
    resp = client.get("/admin/security/status")
    assert resp.status_code == 401


def test_security_status_requires_admin_not_viewer(tmp_path: Path) -> None:
    client, admin_svc = _make_admin_client(tmp_path)
    admin_svc.create_user(email="viewer@example.com", password="pass12345678", roles=["viewer"], actor_id="sys")
    resp = client.post("/auth/local/login", json={"email": "viewer@example.com", "password": "pass12345678"})
    cookie = resp.cookies["ma_session"]
    resp2 = client.get("/admin/security/status", cookies={"ma_session": cookie})
    assert resp2.status_code == 403


def test_security_status_admin_can_read(tmp_path: Path) -> None:
    client, admin_svc = _make_admin_client(tmp_path)
    admin_svc.create_user(email="admin@example.com", password="pass12345678", roles=["admin"], actor_id="sys")
    resp = client.post("/auth/local/login", json={"email": "admin@example.com", "password": "pass12345678"})
    cookie = resp.cookies["ma_session"]
    resp2 = client.get("/admin/security/status", cookies={"ma_session": cookie})
    assert resp2.status_code == 200
    body = resp2.json()
    assert "deployment_mode" in body
    assert "findings" in body
    assert "error_count" in body
    assert "warning_count" in body


def test_security_status_bearer_machine_token_is_forbidden(tmp_path: Path) -> None:
    """Machine tokens cannot manage users — security/status is admin-browser-only."""
    client, _ = _make_admin_client(tmp_path)
    resp = client.get("/admin/security/status", headers=AUTH)
    assert resp.status_code == 403


def test_security_status_response_no_secrets(tmp_path: Path) -> None:
    """Response must not contain raw env values or token hashes."""
    client, admin_svc = _make_admin_client(tmp_path)
    admin_svc.create_user(email="admin2@example.com", password="pass12345678", roles=["admin"], actor_id="sys")
    resp = client.post("/auth/local/login", json={"email": "admin2@example.com", "password": "pass12345678"})
    cookie = resp.cookies["ma_session"]
    resp2 = client.get("/admin/security/status", cookies={"ma_session": cookie})
    text = resp2.text
    assert TOKEN not in text, "machine token leaked in security status response"
    assert "hash" not in text.lower() or "csrf" not in text.lower()  # no session/token hashes
    assert str(tmp_path) not in text, "absolute path leaked"


def test_security_status_findings_shape(tmp_path: Path) -> None:
    client, admin_svc = _make_admin_client(tmp_path)
    admin_svc.create_user(email="admin3@example.com", password="pass12345678", roles=["admin"], actor_id="sys")
    resp = client.post("/auth/local/login", json={"email": "admin3@example.com", "password": "pass12345678"})
    cookie = resp.cookies["ma_session"]
    resp2 = client.get("/admin/security/status", cookies={"ma_session": cookie})
    body = resp2.json()
    for f in body["findings"]:
        assert "code" in f
        assert "severity" in f
        assert "message" in f
        assert f["severity"] in ("info", "warning", "error")


# ===========================================================================
# 8. Regression: existing auth / RBAC / CSRF behavior
# ===========================================================================

def test_valid_bearer_machine_token_still_works(tmp_path: Path) -> None:
    client, _ = _make_admin_client(tmp_path)
    meetings_root = tmp_path / "meetings" / "2026-01-01__deploy-test"
    meetings_root.mkdir(parents=True)
    (meetings_root / "meeting.json").write_text(json.dumps(VALID_CARD), encoding="utf-8")
    resp = client.get("/meetings/2026-01-01__deploy-test", headers=AUTH)
    assert resp.status_code == 200


def test_invalid_bearer_does_not_fall_back_to_cookie(tmp_path: Path) -> None:
    """A wrong Bearer token with a valid cookie must still return 401."""
    client, admin_svc = _make_admin_client(tmp_path)
    admin_svc.create_user(email="user@example.com", password="pass12345678", roles=["viewer"], actor_id="sys")
    login = client.post("/auth/local/login", json={"email": "user@example.com", "password": "pass12345678"})
    cookie = login.cookies["ma_session"]
    resp = client.get(
        "/meetings",
        headers={"Authorization": "Bearer wrong-token"},
        cookies={"ma_session": cookie},
    )
    assert resp.status_code == 401


def test_csrf_endpoint_unchanged(tmp_path: Path) -> None:
    client, admin_svc = _make_admin_client(tmp_path)
    admin_svc.create_user(email="viewer2@example.com", password="pass12345678", roles=["viewer"], actor_id="sys")
    login = client.post("/auth/local/login", json={"email": "viewer2@example.com", "password": "pass12345678"})
    cookie = login.cookies["ma_session"]
    csrf = login.json()["csrf_token"]
    resp = client.get("/auth/csrf", cookies={"ma_session": cookie})
    assert resp.status_code == 200
    assert resp.json()["csrf_token"] == csrf


def test_csrf_endpoint_no_session_id_or_hash(tmp_path: Path) -> None:
    client, admin_svc = _make_admin_client(tmp_path)
    admin_svc.create_user(email="viewer3@example.com", password="pass12345678", roles=["viewer"], actor_id="sys")
    login = client.post("/auth/local/login", json={"email": "viewer3@example.com", "password": "pass12345678"})
    cookie = login.cookies["ma_session"]
    resp = client.get("/auth/csrf", cookies={"ma_session": cookie})
    body = resp.json()
    assert set(body.keys()) == {"csrf_token"}, f"unexpected keys: {set(body.keys())}"


def test_rbac_viewer_cannot_manage_users(tmp_path: Path) -> None:
    client, admin_svc = _make_admin_client(tmp_path)
    admin_svc.create_user(email="viewer4@example.com", password="pass12345678", roles=["viewer"], actor_id="sys")
    login = client.post("/auth/local/login", json={"email": "viewer4@example.com", "password": "pass12345678"})
    cookie = login.cookies["ma_session"]
    resp = client.get("/admin/users", cookies={"ma_session": cookie})
    assert resp.status_code == 403


def test_logout_invalidates_session(tmp_path: Path) -> None:
    client, admin_svc = _make_admin_client(tmp_path)
    admin_svc.create_user(email="logouttest@example.com", password="pass12345678", roles=["viewer"], actor_id="sys")
    login = client.post("/auth/local/login", json={"email": "logouttest@example.com", "password": "pass12345678"})
    cookie = login.cookies["ma_session"]
    csrf = login.json()["csrf_token"]

    # Logout with CSRF token.
    logout_resp = client.post(
        "/auth/logout",
        cookies={"ma_session": cookie},
        headers={"X-CSRF-Token": csrf},
    )
    assert logout_resp.status_code in (200, 204)

    # Session is now invalid.
    me_resp = client.get("/auth/me", cookies={"ma_session": cookie})
    assert me_resp.status_code == 401


def test_session_cookie_is_httponly(tmp_path: Path) -> None:
    client, admin_svc = _make_admin_client(tmp_path)
    admin_svc.create_user(email="ck@example.com", password="pass12345678", roles=["viewer"], actor_id="sys")
    resp = client.post("/auth/local/login", json={"email": "ck@example.com", "password": "pass12345678"})
    assert resp.status_code == 200
    set_cookie = resp.headers.get("set-cookie", "")
    assert "httponly" in set_cookie.lower()


def test_session_cookie_samesite_is_lax(tmp_path: Path) -> None:
    client, admin_svc = _make_admin_client(tmp_path)
    admin_svc.create_user(email="ck2@example.com", password="pass12345678", roles=["viewer"], actor_id="sys")
    resp = client.post("/auth/local/login", json={"email": "ck2@example.com", "password": "pass12345678"})
    set_cookie = resp.headers.get("set-cookie", "")
    assert "samesite=lax" in set_cookie.lower()


def test_session_cookie_has_finite_max_age(tmp_path: Path) -> None:
    client, admin_svc = _make_admin_client(tmp_path)
    admin_svc.create_user(email="ck3@example.com", password="pass12345678", roles=["viewer"], actor_id="sys")
    resp = client.post("/auth/local/login", json={"email": "ck3@example.com", "password": "pass12345678"})
    set_cookie = resp.headers.get("set-cookie", "")
    assert "max-age=" in set_cookie.lower()
    # Verify finite (non-zero).
    import re
    m = re.search(r"max-age=(\d+)", set_cookie.lower())
    assert m and int(m.group(1)) > 0


# ===========================================================================
# 9. Secret strength (issue #86)
# ===========================================================================

def test_self_hosted_machine_token_rejects_low_entropy_value() -> None:
    """Repeated single-char token must produce an error finding in self_hosted."""
    env = {
        "MEETINGAGENT_DEPLOYMENT_MODE": "self_hosted",
        "MEETINGAGENT_API_TOKEN": "a" * 40,
    }
    findings = validate_deployment_safety({}, env)
    assert "machine_token_weak" in _error_codes(findings)


def test_local_machine_token_low_entropy_is_warning_not_error() -> None:
    """Repeated single-char token produces only a warning in local mode."""
    env = {"MEETINGAGENT_API_TOKEN": "a" * 40}
    findings = validate_deployment_safety({}, env)
    assert "machine_token_weak" in _warning_codes(findings)
    assert "machine_token_weak" not in _error_codes(findings)


def test_self_hosted_machine_token_rejects_repeated_block() -> None:
    env = {
        "MEETINGAGENT_DEPLOYMENT_MODE": "self_hosted",
        "MEETINGAGENT_API_TOKEN": "abcabcabcabcabcabcabcabcabcabcabcabc",
    }
    findings = validate_deployment_safety({}, env)
    assert "machine_token_weak" in _error_codes(findings)


def test_bootstrap_secret_rejects_low_entropy_value() -> None:
    env = {
        "MEETINGAGENT_BOOTSTRAP_ALLOW_REMOTE": "true",
        "MEETINGAGENT_BOOTSTRAP_SECRET": "a" * 40,
    }
    findings = validate_deployment_safety({}, env)
    assert "bootstrap_policy_unsafe" in _error_codes(findings)


def test_bootstrap_secret_rejects_repeated_block() -> None:
    env = {
        "MEETINGAGENT_BOOTSTRAP_ALLOW_REMOTE": "true",
        "MEETINGAGENT_BOOTSTRAP_SECRET": "token-token-token-token-token-token-token",
    }
    findings = validate_deployment_safety({}, env)
    assert "bootstrap_policy_unsafe" in _error_codes(findings)


def test_secret_strength_errors_do_not_expose_secret_value() -> None:
    low_entropy_token = "a" * 40
    env = {
        "MEETINGAGENT_DEPLOYMENT_MODE": "self_hosted",
        "MEETINGAGENT_API_TOKEN": low_entropy_token,
    }
    findings = validate_deployment_safety({}, env)
    for f in findings:
        assert low_entropy_token not in f.message, (
            f"Low-entropy token value leaked in finding '{f.code}': {f.message!r}"
        )


def test_deployment_safety_error_does_not_expose_low_entropy_secret() -> None:
    low_entropy_secret = "abcabcabcabcabcabcabcabcabcabcabcabc"
    env = {
        "MEETINGAGENT_DEPLOYMENT_MODE": "self_hosted",
        "MEETINGAGENT_API_TOKEN": low_entropy_secret,
    }
    with pytest.raises(DeploymentSafetyError) as exc_info:
        check_and_fail_if_unsafe({}, env)
    msg = str(exc_info.value)
    assert low_entropy_secret not in msg
    assert "abcabc" not in msg


# ===========================================================================
# 10. Trusted proxy policy (issue #91)
# ===========================================================================

def test_self_hosted_auto_secure_without_trusted_proxy_policy_reports_warning() -> None:
    """cookie_secure=auto in self_hosted without trusted proxy CIDRs → warning."""
    cfg = {"auth": {"cookie_secure": "auto"}}
    env = {"MEETINGAGENT_DEPLOYMENT_MODE": "self_hosted", "MEETINGAGENT_API_TOKEN": STRONG_TOKEN}
    findings = validate_deployment_safety(cfg, env)
    assert "trusted_proxy_no_cidrs" in _warning_codes(findings)


def test_self_hosted_auto_secure_with_trusted_proxy_no_warning() -> None:
    cfg = {
        "auth": {"cookie_secure": "auto"},
        "security": {"trusted_proxy_cidrs": ["127.0.0.1/32"]},
    }
    env = {"MEETINGAGENT_DEPLOYMENT_MODE": "self_hosted", "MEETINGAGENT_API_TOKEN": STRONG_TOKEN}
    findings = validate_deployment_safety(cfg, env)
    assert "trusted_proxy_no_cidrs" not in _finding_codes(findings)


def test_self_hosted_cookie_secure_true_no_proxy_warning() -> None:
    """cookie_secure=true doesn't need proxy CIDRs — always secure regardless."""
    cfg = {"auth": {"cookie_secure": "true"}}
    env = {"MEETINGAGENT_DEPLOYMENT_MODE": "self_hosted", "MEETINGAGENT_API_TOKEN": STRONG_TOKEN}
    findings = validate_deployment_safety(cfg, env)
    assert "trusted_proxy_no_cidrs" not in _finding_codes(findings)


def test_local_mode_no_trusted_proxy_warning() -> None:
    """Local mode should not warn about missing proxy CIDRs."""
    cfg = {"auth": {"cookie_secure": "auto"}}
    env = {"MEETINGAGENT_API_TOKEN": STRONG_TOKEN}
    findings = validate_deployment_safety(cfg, env)
    assert "trusted_proxy_no_cidrs" not in _finding_codes(findings)


def test_invalid_trusted_proxy_cidr_is_error() -> None:
    cfg = {"security": {"trusted_proxy_cidrs": ["not-a-cidr", "also-bad"]}}
    findings = validate_deployment_safety(cfg, {})
    assert "invalid_trusted_proxy_cidrs" in _error_codes(findings)


def test_invalid_trusted_proxy_cidr_aborts_startup_in_self_hosted() -> None:
    cfg = {"security": {"trusted_proxy_cidrs": ["not-a-cidr"]}}
    env = {"MEETINGAGENT_DEPLOYMENT_MODE": "self_hosted", "MEETINGAGENT_API_TOKEN": STRONG_TOKEN}
    with pytest.raises(DeploymentSafetyError) as exc_info:
        check_and_fail_if_unsafe(cfg, env)
    assert "invalid_trusted_proxy_cidrs" in str(exc_info.value)


def test_admin_security_status_includes_trusted_proxy_policy(tmp_path: Path) -> None:
    client, admin_svc = _make_admin_client(tmp_path)
    admin_svc.create_user(email="admin-tp@example.com", password="pass12345678", roles=["admin"], actor_id="sys")
    resp = client.post("/auth/local/login", json={"email": "admin-tp@example.com", "password": "pass12345678"})
    cookie = resp.cookies["ma_session"]
    resp2 = client.get("/admin/security/status", cookies={"ma_session": cookie})
    body = resp2.json()
    assert "trusted_proxy_policy" in body
    tpp = body["trusted_proxy_policy"]
    assert "configured" in tpp
    assert "count" in tpp
    assert isinstance(tpp["configured"], bool)
    assert isinstance(tpp["count"], int)


def test_self_hosted_auto_secure_with_trusted_proxy_from_env_no_warning() -> None:
    cfg = {"auth": {"cookie_secure": "auto"}}
    env = {
        "MEETINGAGENT_DEPLOYMENT_MODE": "self_hosted",
        "MEETINGAGENT_API_TOKEN": STRONG_TOKEN,
        "MEETINGAGENT_TRUSTED_PROXY_CIDRS": "10.0.0.0/8",
    }
    findings = validate_deployment_safety(cfg, env)
    assert "trusted_proxy_no_cidrs" not in _finding_codes(findings)
    assert "invalid_trusted_proxy_cidrs" not in _finding_codes(findings)


def test_invalid_trusted_proxy_cidr_from_env_is_error() -> None:
    cfg = {}
    env = {
        "MEETINGAGENT_DEPLOYMENT_MODE": "self_hosted",
        "MEETINGAGENT_API_TOKEN": STRONG_TOKEN,
        "MEETINGAGENT_TRUSTED_PROXY_CIDRS": "not-a-cidr",
    }
    findings = validate_deployment_safety(cfg, env)
    assert "invalid_trusted_proxy_cidrs" in _error_codes(findings)


def test_admin_security_status_does_not_expose_raw_proxy_cidrs(tmp_path: Path) -> None:
    cidr = "10.0.0.0/8"
    client, admin_svc = _make_admin_client(tmp_path, config={"security": {"trusted_proxy_cidrs": [cidr]}})
    admin_svc.create_user(email="admin-tp2@example.com", password="pass12345678", roles=["admin"], actor_id="sys")
    resp = client.post("/auth/local/login", json={"email": "admin-tp2@example.com", "password": "pass12345678"})
    cookie = resp.cookies["ma_session"]
    resp2 = client.get("/admin/security/status", cookies={"ma_session": cookie})
    text = resp2.text
    assert cidr not in text, f"Raw CIDR {cidr!r} leaked in security status response"
