"""Tests for AdminService: bootstrap, user management, last-admin protection."""
from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.auth.passwords import hash_password, verify_password  # noqa: E402
from asu_june_bot.auth.repository import AuthRepository  # noqa: E402
from asu_june_bot.auth.service import (  # noqa: E402
    AdminService,
    AdminUserNotFoundError,
    BootstrapConflictError,
    DuplicateUserError,
    InvalidRolesError,
    InvalidCredentialsError,
    LastAdminError,
    LocalAuthService,
)


@pytest.fixture()
def repo(tmp_path: Path) -> AuthRepository:
    r = AuthRepository(tmp_path / "auth.db")
    r.initialize()
    return r


@pytest.fixture()
def svc(repo: AuthRepository) -> AdminService:
    return AdminService(repo)


@pytest.fixture()
def auth_svc(repo: AuthRepository) -> LocalAuthService:
    return LocalAuthService(repo)


# ------------------------------------------------------------------
# 1. Bootstrap creates first active admin
# ------------------------------------------------------------------

def test_bootstrap_creates_first_admin(svc: AdminService, repo: AuthRepository) -> None:
    result = svc.bootstrap_admin("admin@example.com", "strongpass1")
    assert result["email"] == "admin@example.com"
    assert result["status"] == "active"
    assert "admin" in result["roles"]
    assert repo.count_users() == 1


# ------------------------------------------------------------------
# 2. Bootstrap stores Argon2id hash, not plaintext
# ------------------------------------------------------------------

def test_bootstrap_stores_hash_not_plaintext(svc: AdminService, repo: AuthRepository) -> None:
    password = "strongpass2"
    result = svc.bootstrap_admin("admin@example.com", password)
    user_id = result["user_id"]
    cred = repo.get_local_credential(user_id)
    assert cred is not None
    assert cred.password_hash != password
    assert cred.password_hash.startswith("$argon2")
    assert verify_password(cred.password_hash, password)


# ------------------------------------------------------------------
# 3. Bootstrap assigns admin role
# ------------------------------------------------------------------

def test_bootstrap_assigns_admin_role(svc: AdminService, repo: AuthRepository) -> None:
    result = svc.bootstrap_admin("admin@example.com", "strongpass3")
    roles = repo.get_user_roles(result["user_id"])
    assert "admin" in roles


# ------------------------------------------------------------------
# 4. Bootstrap rejected when any user exists
# ------------------------------------------------------------------

def test_bootstrap_rejected_when_user_exists(svc: AdminService, repo: AuthRepository) -> None:
    svc.bootstrap_admin("admin@example.com", "strongpass4")
    with pytest.raises(BootstrapConflictError):
        svc.bootstrap_admin("other@example.com", "strongpass5")


# ------------------------------------------------------------------
# 5. Concurrent bootstrap creates exactly one admin
# ------------------------------------------------------------------

def test_concurrent_bootstrap_creates_exactly_one_admin(tmp_path: Path) -> None:
    repo = AuthRepository(tmp_path / "auth.db")
    repo.initialize()
    svc = AdminService(repo)

    successes: list[dict] = []
    conflicts: list[BootstrapConflictError] = []
    lock = threading.Lock()

    def try_bootstrap(i: int) -> None:
        try:
            result = svc.bootstrap_admin(f"admin{i}@example.com", "strongpass")
            with lock:
                successes.append(result)
        except BootstrapConflictError as exc:
            with lock:
                conflicts.append(exc)

    threads = [threading.Thread(target=try_bootstrap, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(successes) == 1
    assert len(conflicts) == 9
    assert repo.count_users() == 1


# ------------------------------------------------------------------
# 6. Duplicate email rejected when creating user
# ------------------------------------------------------------------

def test_duplicate_email_rejected(svc: AdminService, repo: AuthRepository) -> None:
    svc.bootstrap_admin("admin@example.com", "strongpass")
    admin = repo.list_users()[0]
    with pytest.raises(DuplicateUserError):
        svc.create_user(
            email="admin@example.com",
            password="anotherpass",
            roles=["viewer"],
            actor_id=admin.user_id,
        )


# ------------------------------------------------------------------
# 7. Unknown role rejected
# ------------------------------------------------------------------

def test_unknown_role_rejected(svc: AdminService, repo: AuthRepository) -> None:
    svc.bootstrap_admin("admin@example.com", "strongpass")
    admin = repo.list_users()[0]
    with pytest.raises(InvalidRolesError):
        svc.create_user(
            email="user@example.com",
            password="pass12345",
            roles=["superuser"],
            actor_id=admin.user_id,
        )


# ------------------------------------------------------------------
# 8. Last active admin cannot be disabled
# ------------------------------------------------------------------

def test_last_active_admin_cannot_be_disabled(svc: AdminService, repo: AuthRepository) -> None:
    result = svc.bootstrap_admin("admin@example.com", "strongpass")
    with pytest.raises(LastAdminError):
        svc.disable_user(result["user_id"], actor_id="test")


# ------------------------------------------------------------------
# 9. Last active admin cannot be demoted
# ------------------------------------------------------------------

def test_last_active_admin_cannot_be_demoted(svc: AdminService, repo: AuthRepository) -> None:
    result = svc.bootstrap_admin("admin@example.com", "strongpass")
    with pytest.raises(LastAdminError):
        svc.update_user(result["user_id"], actor_id="test", roles=["viewer"])


def test_second_admin_allows_demotion_of_first(svc: AdminService, repo: AuthRepository) -> None:
    admin1 = svc.bootstrap_admin("admin1@example.com", "strongpass")
    svc.create_user(
        email="admin2@example.com",
        password="strongpass2",
        roles=["admin"],
        actor_id=admin1["user_id"],
    )
    # Now demoting admin1 to viewer is allowed (admin2 remains)
    updated = svc.update_user(admin1["user_id"], actor_id="test", roles=["viewer"])
    assert "viewer" in updated["roles"]
    assert "admin" not in updated["roles"]


# ------------------------------------------------------------------
# 10. Disabled user cannot log in
# ------------------------------------------------------------------

def test_disabled_user_cannot_log_in(
    svc: AdminService, repo: AuthRepository, auth_svc: LocalAuthService
) -> None:
    admin = svc.bootstrap_admin("admin@example.com", "adminpass")
    viewer = svc.create_user(
        email="viewer@example.com",
        password="viewerpass",
        roles=["viewer"],
        actor_id=admin["user_id"],
    )
    # Create a second admin so we can disable the first admin in other tests, but
    # here we just disable the viewer:
    svc.disable_user(viewer["user_id"], actor_id=admin["user_id"])
    with pytest.raises(InvalidCredentialsError):
        auth_svc.login("viewer@example.com", "viewerpass")


# ------------------------------------------------------------------
# 11. Disabling user revokes active sessions
# ------------------------------------------------------------------

def test_disabling_user_revokes_sessions(
    svc: AdminService, repo: AuthRepository, auth_svc: LocalAuthService
) -> None:
    admin = svc.bootstrap_admin("admin@example.com", "adminpass")
    viewer = svc.create_user(
        email="viewer@example.com",
        password="viewerpass",
        roles=["viewer"],
        actor_id=admin["user_id"],
    )
    # Log in to create a session
    token, _ = auth_svc.login("viewer@example.com", "viewerpass")
    # Session resolves before disable
    assert auth_svc.resolve_session(token) is not None
    # Disable user (revokes sessions)
    svc.disable_user(viewer["user_id"], actor_id=admin["user_id"])
    # Session no longer resolves
    assert auth_svc.resolve_session(token) is None


# ------------------------------------------------------------------
# General admin service: list/get/update/enable
# ------------------------------------------------------------------

def test_list_users_includes_roles(svc: AdminService) -> None:
    svc.bootstrap_admin("admin@example.com", "strongpass")
    users = svc.list_users()
    assert len(users) == 1
    assert "admin" in users[0]["roles"]


def test_get_user_returns_none_for_unknown(svc: AdminService) -> None:
    assert svc.get_user("nonexistent-id") is None


def test_update_display_name(svc: AdminService) -> None:
    result = svc.bootstrap_admin("admin@example.com", "strongpass")
    updated = svc.update_user(result["user_id"], "test", display_name="Admin User")
    assert updated["display_name"] == "Admin User"


def test_enable_user_after_disable(svc: AdminService, repo: AuthRepository) -> None:
    admin = svc.bootstrap_admin("admin@example.com", "adminpass")
    viewer = svc.create_user(
        email="viewer@example.com",
        password="viewerpass",
        roles=["viewer"],
        actor_id=admin["user_id"],
    )
    svc.disable_user(viewer["user_id"], actor_id=admin["user_id"])
    result = svc.enable_user(viewer["user_id"], actor_id=admin["user_id"])
    assert result["status"] == "active"


def test_admin_user_not_found_raises(svc: AdminService) -> None:
    with pytest.raises(AdminUserNotFoundError):
        svc.disable_user("no-such-id", actor_id="test")


def test_bootstrap_response_excludes_password_hash(svc: AdminService) -> None:
    result = svc.bootstrap_admin("admin@example.com", "strongpass")
    assert "password_hash" not in result
    assert "password" not in result


def test_create_user_response_excludes_password_hash(svc: AdminService) -> None:
    admin = svc.bootstrap_admin("admin@example.com", "adminpass")
    user = svc.create_user(
        email="viewer@example.com",
        password="viewerpass",
        roles=["viewer"],
        actor_id=admin["user_id"],
    )
    assert "password_hash" not in user
    assert "password" not in user
