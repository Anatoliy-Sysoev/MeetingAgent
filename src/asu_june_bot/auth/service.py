from __future__ import annotations

import datetime
import hashlib
import secrets
from dataclasses import dataclass

from asu_june_bot.auth.models import Session, User, now_iso
from asu_june_bot.auth.passwords import dummy_verify, verify_password
from asu_june_bot.auth.repository import AuthRepository

DEFAULT_SESSION_TTL_SECONDS = 7 * 24 * 3600


class InvalidCredentialsError(Exception):
    """Generic login failure: unknown email, wrong password, or disabled user.

    Callers must surface the same response for all causes so the API does
    not reveal whether an email is registered.
    """


@dataclass(frozen=True)
class AuthenticatedSession:
    user: User
    roles: frozenset[str]
    session: Session


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class LocalAuthService:
    """Email/password login with opaque server-side sessions."""

    def __init__(
        self,
        repository: AuthRepository,
        session_ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS,
    ) -> None:
        self.repository = repository
        self.session_ttl_seconds = session_ttl_seconds

    def _expires_at(self) -> str:
        moment = datetime.datetime.now(tz=datetime.timezone.utc) + datetime.timedelta(
            seconds=self.session_ttl_seconds
        )
        return moment.isoformat(timespec="seconds")

    def login(self, email: str, password: str) -> tuple[str, AuthenticatedSession]:
        """Return (opaque_token, session info) or raise InvalidCredentialsError."""
        try:
            user = self.repository.get_user_by_email(email)
        except ValueError:
            user = None
        credential = (
            self.repository.get_local_credential(user.user_id) if user else None
        )
        if user is None or credential is None:
            dummy_verify(password)
            self._audit_failure(email, "unknown_or_no_credential")
            raise InvalidCredentialsError()
        if not verify_password(credential.password_hash, password):
            self._audit_failure(email, "bad_password", user_id=user.user_id)
            raise InvalidCredentialsError()
        if user.status != "active":
            self._audit_failure(email, "user_disabled", user_id=user.user_id)
            raise InvalidCredentialsError()

        token = secrets.token_urlsafe(32)
        session = self.repository.create_session(
            user_id=user.user_id,
            token_hash=hash_session_token(token),
            expires_at=self._expires_at(),
        )
        self.repository.set_last_login(user.user_id)
        roles = self.repository.get_user_roles(user.user_id)
        self.repository.append_audit_event(
            actor_type="user",
            actor_id=user.user_id,
            action="auth.login.success",
            target_type="session",
            target_id=session.session_id,
        )
        return token, AuthenticatedSession(user=user, roles=roles, session=session)

    def resolve_session(self, token: str) -> AuthenticatedSession | None:
        """Return session info for a valid token; None if missing/expired/revoked."""
        if not token:
            return None
        session = self.repository.get_session_by_token_hash(hash_session_token(token))
        if session is None or not session.is_active(now_iso()):
            return None
        user = self.repository.get_user(session.user_id)
        if user is None or user.status != "active":
            return None
        roles = self.repository.get_user_roles(user.user_id)
        return AuthenticatedSession(user=user, roles=roles, session=session)

    def logout(self, token: str) -> bool:
        """Revoke the session behind the token. Idempotent; True if revoked."""
        if not token:
            return False
        session = self.repository.get_session_by_token_hash(hash_session_token(token))
        if session is None:
            return False
        self.repository.revoke_session(session.session_id)
        self.repository.append_audit_event(
            actor_type="user",
            actor_id=session.user_id,
            action="auth.logout",
            target_type="session",
            target_id=session.session_id,
        )
        return True

    def _audit_failure(self, email: str, reason: str, user_id: str | None = None) -> None:
        self.repository.append_audit_event(
            actor_type="user",
            actor_id=user_id or "anonymous",
            action="auth.login.failure",
            metadata={"email": email.strip().lower(), "reason": reason},
        )
