from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.auth.models import (  # noqa: E402
    Principal,
    User,
    normalize_email,
)
from asu_june_bot.auth.permissions import (  # noqa: E402
    ADMIN_PERMISSIONS,
    EDITOR_PERMISSIONS,
    VIEWER_PERMISSIONS,
    permissions_for_roles,
)


# ------------------------------------------------------------------
# Permissions inheritance
# ------------------------------------------------------------------

def test_editor_includes_viewer() -> None:
    assert VIEWER_PERMISSIONS < EDITOR_PERMISSIONS


def test_admin_includes_editor() -> None:
    assert EDITOR_PERMISSIONS < ADMIN_PERMISSIONS


def test_viewer_cannot_start_jobs() -> None:
    assert "jobs.start" not in VIEWER_PERMISSIONS
    assert "jobs.start" in EDITOR_PERMISSIONS


def test_editor_cannot_manage_users() -> None:
    assert "users.manage" not in EDITOR_PERMISSIONS
    assert "users.manage" in ADMIN_PERMISSIONS


def test_unknown_role_grants_nothing() -> None:
    assert permissions_for_roles(frozenset({"superuser"})) == frozenset()


def test_mixed_known_unknown_roles() -> None:
    perms = permissions_for_roles(frozenset({"viewer", "nonexistent"}))
    assert perms == VIEWER_PERMISSIONS


# ------------------------------------------------------------------
# Principal
# ------------------------------------------------------------------

def test_principal_permission_checks() -> None:
    p = Principal.for_user("u-1", "local", frozenset({"editor"}))
    assert p.has_role("editor")
    assert not p.has_role("admin")
    assert p.has_permission("jobs.start")
    assert not p.has_permission("users.manage")


def test_principal_invalid_type_rejected() -> None:
    with pytest.raises(ValueError):
        Principal(principal_type="alien", principal_id="x", provider="local")


def test_machine_principal() -> None:
    p = Principal(
        principal_type="machine",
        principal_id="bootstrap",
        provider="machine",
        permissions=frozenset({"meetings.upload"}),
    )
    assert p.has_permission("meetings.upload")
    assert not p.has_permission("users.manage")


# ------------------------------------------------------------------
# User / email
# ------------------------------------------------------------------

def test_email_normalization() -> None:
    assert normalize_email("  User@Example.COM ") == "user@example.com"


def test_invalid_email_rejected() -> None:
    with pytest.raises(ValueError):
        normalize_email("not-an-email")
    with pytest.raises(ValueError):
        normalize_email("   ")


def test_user_normalizes_email_on_init() -> None:
    u = User(user_id="u-1", email="  A@B.COM ")
    assert u.email == "a@b.com"


def test_user_invalid_status_rejected() -> None:
    with pytest.raises(ValueError):
        User(user_id="u-1", email="a@b.com", status="banned")


# ------------------------------------------------------------------
# Principal RBAC invariants
# ------------------------------------------------------------------

def test_user_principal_unknown_role_raises() -> None:
    with pytest.raises(ValueError):
        Principal.for_user("u-1", "local", frozenset({"superuser"}))


def test_user_principal_mixed_known_unknown_raises() -> None:
    with pytest.raises(ValueError):
        Principal.for_user("u-1", "local", frozenset({"viewer", "hacker"}))


def test_user_principal_injected_permission_raises() -> None:
    with pytest.raises(ValueError):
        Principal(
            principal_type="user",
            principal_id="u-1",
            provider="local",
            roles=frozenset({"viewer"}),
            permissions=frozenset({"users.manage"}),
        )


def test_valid_principal_for_user_all_roles() -> None:
    for role in ("viewer", "editor", "admin"):
        p = Principal.for_user("u-1", "local", frozenset({role}))
        assert p.has_role(role)


def test_machine_principal_explicit_permissions_allowed() -> None:
    p = Principal(
        principal_type="machine",
        principal_id="cli",
        provider="machine",
        permissions=frozenset({"meetings.upload", "jobs.start"}),
    )
    assert p.has_permission("meetings.upload")
    assert not p.has_permission("users.manage")
