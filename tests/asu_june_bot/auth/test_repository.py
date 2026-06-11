from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.auth.repository import (  # noqa: E402
    AuthRepository,
    DuplicateEmailError,
    DuplicateIdentityError,
    UserNotFoundError,
)


@pytest.fixture()
def repo(tmp_path: Path) -> AuthRepository:
    r = AuthRepository(tmp_path / "auth.db")
    r.initialize()
    return r


# ------------------------------------------------------------------
# Initialization
# ------------------------------------------------------------------

def test_initialize_creates_db(tmp_path: Path) -> None:
    db = tmp_path / "sub" / "auth.db"
    r = AuthRepository(db)
    r.initialize()
    assert db.exists()


def test_initialize_idempotent(repo: AuthRepository) -> None:
    repo.initialize()
    repo.initialize()
    user = repo.create_user(email="a@b.com")
    assert repo.get_user(user.user_id) is not None


# ------------------------------------------------------------------
# Users
# ------------------------------------------------------------------

def test_create_and_get_user(repo: AuthRepository) -> None:
    user = repo.create_user(email="Alice@Example.com", display_name="Alice")
    fetched = repo.get_user(user.user_id)
    assert fetched is not None
    assert fetched.email == "alice@example.com"
    assert fetched.display_name == "Alice"
    assert fetched.status == "active"


def test_get_user_by_email_case_insensitive(repo: AuthRepository) -> None:
    repo.create_user(email="bob@example.com")
    assert repo.get_user_by_email("  BOB@example.COM ") is not None


def test_duplicate_email_rejected(repo: AuthRepository) -> None:
    repo.create_user(email="dup@example.com")
    with pytest.raises(DuplicateEmailError):
        repo.create_user(email="DUP@example.com")


def test_disable_and_reactivate_user(repo: AuthRepository) -> None:
    user = repo.create_user(email="x@y.com")
    repo.set_user_status(user.user_id, "disabled")
    assert repo.get_user(user.user_id).status == "disabled"
    repo.set_user_status(user.user_id, "active")
    assert repo.get_user(user.user_id).status == "active"


def test_set_status_unknown_user(repo: AuthRepository) -> None:
    with pytest.raises(UserNotFoundError):
        repo.set_user_status("no-such-id", "disabled")


def test_set_status_invalid_value(repo: AuthRepository) -> None:
    user = repo.create_user(email="z@y.com")
    with pytest.raises(ValueError):
        repo.set_user_status(user.user_id, "banned")


def test_list_users_pagination(repo: AuthRepository) -> None:
    for i in range(5):
        repo.create_user(email=f"user{i}@example.com")
    page = repo.list_users(offset=2, limit=2)
    assert len(page) == 2


# ------------------------------------------------------------------
# Roles
# ------------------------------------------------------------------

def test_set_and_get_roles(repo: AuthRepository) -> None:
    user = repo.create_user(email="r@example.com")
    repo.set_user_roles(user.user_id, {"viewer", "editor"})
    assert repo.get_user_roles(user.user_id) == frozenset({"viewer", "editor"})


def test_replace_roles(repo: AuthRepository) -> None:
    user = repo.create_user(email="r2@example.com")
    repo.set_user_roles(user.user_id, {"viewer"})
    repo.set_user_roles(user.user_id, {"admin"})
    assert repo.get_user_roles(user.user_id) == frozenset({"admin"})


def test_unknown_role_rejected(repo: AuthRepository) -> None:
    user = repo.create_user(email="r3@example.com")
    with pytest.raises(ValueError):
        repo.set_user_roles(user.user_id, {"superuser"})


def test_roles_for_unknown_user(repo: AuthRepository) -> None:
    with pytest.raises(UserNotFoundError):
        repo.set_user_roles("ghost", {"viewer"})


# ------------------------------------------------------------------
# Local credentials
# ------------------------------------------------------------------

def test_store_and_read_password_hash(repo: AuthRepository) -> None:
    user = repo.create_user(email="c@example.com")
    repo.create_local_credential(user.user_id, "argon2id$fakehash")
    cred = repo.get_local_credential(user.user_id)
    assert cred is not None
    assert cred.password_hash == "argon2id$fakehash"


def test_credential_foreign_key_enforced(repo: AuthRepository) -> None:
    from asu_june_bot.auth.repository import AuthRepositoryError
    with pytest.raises(AuthRepositoryError):
        repo.create_local_credential("no-such-user", "hash")


def test_no_plaintext_password_column(repo: AuthRepository) -> None:
    """Schema must not have any column that could store plaintext passwords."""
    conn = sqlite3.connect(repo.db_path)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(auth_local_credentials)")]
    conn.close()
    assert "password" not in cols
    assert "password_hash" in cols


# ------------------------------------------------------------------
# External identities
# ------------------------------------------------------------------

def test_link_and_get_external_identity(repo: AuthRepository) -> None:
    user = repo.create_user(email="e@example.com")
    repo.link_external_identity(
        user_id=user.user_id, provider="yandex", subject="12345",
        email="e@example.com", email_verified=True,
    )
    identity = repo.get_external_identity("yandex", "12345")
    assert identity is not None
    assert identity.user_id == user.user_id
    assert identity.email_verified is True


def test_duplicate_provider_subject_rejected(repo: AuthRepository) -> None:
    user = repo.create_user(email="e2@example.com")
    repo.link_external_identity(user_id=user.user_id, provider="google", subject="abc")
    with pytest.raises(DuplicateIdentityError):
        repo.link_external_identity(user_id=user.user_id, provider="google", subject="abc")


def test_same_subject_different_provider_ok(repo: AuthRepository) -> None:
    user = repo.create_user(email="e3@example.com")
    repo.link_external_identity(user_id=user.user_id, provider="google", subject="same")
    repo.link_external_identity(user_id=user.user_id, provider="yandex", subject="same")
    assert repo.get_external_identity("google", "same") is not None
    assert repo.get_external_identity("yandex", "same") is not None


def test_identity_foreign_key_enforced(repo: AuthRepository) -> None:
    from asu_june_bot.auth.repository import AuthRepositoryError
    with pytest.raises(AuthRepositoryError):
        repo.link_external_identity(user_id="ghost", provider="google", subject="x")


# ------------------------------------------------------------------
# Sessions
# ------------------------------------------------------------------

def test_create_and_get_session(repo: AuthRepository) -> None:
    user = repo.create_user(email="s@example.com")
    session = repo.create_session(
        user_id=user.user_id, token_hash="abc123", expires_at="2999-01-01T00:00:00+00:00"
    )
    fetched = repo.get_session_by_token_hash("abc123")
    assert fetched is not None
    assert fetched.session_id == session.session_id
    assert fetched.is_active()


def test_session_foreign_key_enforced(repo: AuthRepository) -> None:
    from asu_june_bot.auth.repository import AuthRepositoryError
    with pytest.raises(AuthRepositoryError):
        repo.create_session(
            user_id="ghost", token_hash="x", expires_at="2999-01-01T00:00:00+00:00"
        )


def test_revoke_session(repo: AuthRepository) -> None:
    user = repo.create_user(email="s2@example.com")
    session = repo.create_session(
        user_id=user.user_id, token_hash="t1", expires_at="2999-01-01T00:00:00+00:00"
    )
    repo.revoke_session(session.session_id)
    fetched = repo.get_session_by_token_hash("t1")
    assert fetched is not None
    assert not fetched.is_active()


def test_expired_session_inactive(repo: AuthRepository) -> None:
    user = repo.create_user(email="s3@example.com")
    repo.create_session(
        user_id=user.user_id, token_hash="t2", expires_at="2000-01-01T00:00:00+00:00"
    )
    fetched = repo.get_session_by_token_hash("t2")
    assert fetched is not None
    assert not fetched.is_active()


def test_revoke_all_user_sessions(repo: AuthRepository) -> None:
    user = repo.create_user(email="s4@example.com")
    repo.create_session(user_id=user.user_id, token_hash="a", expires_at="2999-01-01T00:00:00+00:00")
    repo.create_session(user_id=user.user_id, token_hash="b", expires_at="2999-01-01T00:00:00+00:00")
    assert repo.revoke_user_sessions(user.user_id) == 2


def test_delete_expired_sessions(repo: AuthRepository) -> None:
    user = repo.create_user(email="s5@example.com")
    repo.create_session(user_id=user.user_id, token_hash="old", expires_at="2000-01-01T00:00:00+00:00")
    repo.create_session(user_id=user.user_id, token_hash="new", expires_at="2999-01-01T00:00:00+00:00")
    assert repo.delete_expired_sessions() == 1
    assert repo.get_session_by_token_hash("old") is None
    assert repo.get_session_by_token_hash("new") is not None


def test_set_last_login(repo: AuthRepository) -> None:
    user = repo.create_user(email="s6@example.com")
    repo.set_last_login(user.user_id, "2026-06-11T00:00:00+00:00")
    assert repo.get_user(user.user_id).last_login_at == "2026-06-11T00:00:00+00:00"


# ------------------------------------------------------------------
# Audit
# ------------------------------------------------------------------

def test_audit_event_write_read(repo: AuthRepository) -> None:
    repo.append_audit_event(
        actor_type="user", actor_id="u-1", action="user.created",
        target_type="user", target_id="u-2",
        metadata={"roles": ["viewer"]},
    )
    events = repo.list_audit_events()
    assert len(events) == 1
    assert events[0].action == "user.created"
    assert events[0].metadata == {"roles": ["viewer"]}


def test_audit_metadata_non_serializable_coerced(repo: AuthRepository) -> None:
    repo.append_audit_event(
        actor_type="machine", actor_id="bootstrap", action="test",
        metadata={"path": Path("/tmp/x")},
    )
    events = repo.list_audit_events()
    assert isinstance(events[0].metadata["path"], str)
