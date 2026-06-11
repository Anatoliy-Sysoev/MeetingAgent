from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.auth.passwords import hash_password  # noqa: E402
from asu_june_bot.auth.repository import AuthRepository  # noqa: E402
from asu_june_bot.auth.service import (  # noqa: E402
    InvalidCredentialsError,
    LocalAuthService,
)

PASSWORD = "correct horse battery staple"


@pytest.fixture()
def repo(tmp_path: Path) -> AuthRepository:
    r = AuthRepository(tmp_path / "auth.db")
    r.initialize()
    return r


@pytest.fixture()
def service(repo: AuthRepository) -> LocalAuthService:
    return LocalAuthService(repo)


def make_user(repo: AuthRepository, email: str = "alice@example.com"):
    user = repo.create_user(email=email)
    repo.create_local_credential(user.user_id, hash_password(PASSWORD))
    repo.set_user_roles(user.user_id, {"editor"})
    return user


def test_login_success(repo: AuthRepository, service: LocalAuthService) -> None:
    user = make_user(repo)
    token, auth = service.login("alice@example.com", PASSWORD)
    assert token
    assert auth.user.user_id == user.user_id
    assert auth.roles == frozenset({"editor"})
    assert repo.get_user(user.user_id).last_login_at is not None


def test_login_wrong_password(repo: AuthRepository, service: LocalAuthService) -> None:
    make_user(repo)
    with pytest.raises(InvalidCredentialsError):
        service.login("alice@example.com", "wrong")


def test_login_unknown_email_same_error(service: LocalAuthService) -> None:
    with pytest.raises(InvalidCredentialsError):
        service.login("nobody@example.com", PASSWORD)


def test_login_invalid_email_format_same_error(service: LocalAuthService) -> None:
    with pytest.raises(InvalidCredentialsError):
        service.login("not-an-email", PASSWORD)


def test_login_disabled_user_rejected(repo: AuthRepository, service: LocalAuthService) -> None:
    user = make_user(repo)
    repo.set_user_status(user.user_id, "disabled")
    with pytest.raises(InvalidCredentialsError):
        service.login("alice@example.com", PASSWORD)


def test_resolve_session_roundtrip(repo: AuthRepository, service: LocalAuthService) -> None:
    make_user(repo)
    token, _ = service.login("alice@example.com", PASSWORD)
    auth = service.resolve_session(token)
    assert auth is not None
    assert auth.user.email == "alice@example.com"


def test_resolve_invalid_token(service: LocalAuthService) -> None:
    assert service.resolve_session("garbage") is None
    assert service.resolve_session("") is None


def test_resolve_revoked_session(repo: AuthRepository, service: LocalAuthService) -> None:
    make_user(repo)
    token, _ = service.login("alice@example.com", PASSWORD)
    assert service.logout(token) is True
    assert service.resolve_session(token) is None


def test_resolve_expired_session(repo: AuthRepository, service: LocalAuthService) -> None:
    make_user(repo)
    short = LocalAuthService(repo, session_ttl_seconds=-1)
    token, _ = short.login("alice@example.com", PASSWORD)
    assert short.resolve_session(token) is None


def test_resolve_session_user_disabled_after_login(
    repo: AuthRepository, service: LocalAuthService
) -> None:
    user = make_user(repo)
    token, _ = service.login("alice@example.com", PASSWORD)
    repo.set_user_status(user.user_id, "disabled")
    assert service.resolve_session(token) is None


def test_logout_idempotent(service: LocalAuthService) -> None:
    assert service.logout("no-such-token") is False
    assert service.logout("") is False


def test_token_not_stored_in_plaintext(repo: AuthRepository, service: LocalAuthService) -> None:
    make_user(repo)
    token, auth = service.login("alice@example.com", PASSWORD)
    assert auth.session.token_hash != token
    assert repo.get_session_by_token_hash(token) is None


def test_audit_events_for_login_logout_failure(
    repo: AuthRepository, service: LocalAuthService
) -> None:
    make_user(repo)
    token, _ = service.login("alice@example.com", PASSWORD)
    with pytest.raises(InvalidCredentialsError):
        service.login("alice@example.com", "wrong")
    service.logout(token)
    actions = {e.action for e in repo.list_audit_events()}
    assert {"auth.login.success", "auth.login.failure", "auth.logout"} <= actions
