from __future__ import annotations

import datetime
import hashlib
import secrets
from dataclasses import dataclass
from typing import Literal

from asu_june_bot.auth.models import Principal, Session, User, normalize_email, now_iso
from asu_june_bot.auth.passwords import (
    dummy_verify,
    generate_csrf_token,
    hash_csrf_token,
    hash_password,
    password_needs_rehash,
    verify_password,
)
from asu_june_bot.auth.permissions import BUILTIN_ROLES
from asu_june_bot.auth.repository import (
    AuthRepository,
    DuplicateEmailError,
    FirstAdminExistsError,
    UserNotFoundError as RepoUserNotFoundError,
)

DEFAULT_SESSION_TTL_SECONDS = 24 * 3600
DEFAULT_COOKIE_NAME = "ma_session"
DEFAULT_COOKIE_SECURE: Literal["auto", "true", "false"] = "auto"


class InvalidCredentialsError(Exception):
    """Generic login failure: unknown email, wrong password, or disabled user.

    Callers must surface the same response for all causes so the API does
    not reveal whether an email is registered.
    """


@dataclass(frozen=True)
class AuthenticatedSession:
    user: User
    principal: Principal
    session: Session
    csrf_token: str = ""  # raw token; empty for machine principals

    @property
    def roles(self) -> frozenset[str]:
        return self.principal.roles


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class LocalAuthService:
    """Email/password login with opaque server-side sessions."""

    def __init__(
        self,
        repository: AuthRepository,
        session_ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS,
        cookie_name: str = DEFAULT_COOKIE_NAME,
        cookie_secure: Literal["auto", "true", "false"] = DEFAULT_COOKIE_SECURE,
    ) -> None:
        self.repository = repository
        self.session_ttl_seconds = session_ttl_seconds
        self.cookie_name = cookie_name
        self.cookie_secure = cookie_secure

    def _expires_at(self) -> str:
        moment = datetime.datetime.now(tz=datetime.timezone.utc) + datetime.timedelta(
            seconds=self.session_ttl_seconds
        )
        return moment.isoformat(timespec="seconds")

    def _make_principal(self, user: User) -> Principal:
        roles = self.repository.get_user_roles(user.user_id)
        return Principal.for_user(user.user_id, "local", roles)

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

        # Transparent rehash if parameters are outdated.
        if password_needs_rehash(credential.password_hash):
            self.repository.update_local_credential_hash(
                user.user_id, hash_password(password)
            )

        token = secrets.token_urlsafe(32)
        csrf_token = generate_csrf_token()
        session = self.repository.create_session(
            user_id=user.user_id,
            token_hash=hash_session_token(token),
            expires_at=self._expires_at(),
            csrf_token_hash=hash_csrf_token(csrf_token),
        )
        self.repository.set_last_login(user.user_id)
        principal = self._make_principal(user)
        self.repository.append_audit_event(
            actor_type="user",
            actor_id=user.user_id,
            action="auth.login.success",
            target_type="session",
            target_id=session.session_id,
        )
        return token, AuthenticatedSession(
            user=user, principal=principal, session=session, csrf_token=csrf_token
        )

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
        principal = self._make_principal(user)
        return AuthenticatedSession(user=user, principal=principal, session=session)

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

    def audit_login_throttled(self, email: str) -> None:
        """Record a throttled login attempt. Never stores password/session/CSRF."""
        self.repository.append_audit_event(
            actor_type="user",
            actor_id="anonymous",
            action="auth.login.throttled",
            metadata={"email": email.strip().lower()},
        )

    def _audit_failure(self, email: str, reason: str, user_id: str | None = None) -> None:
        self.repository.append_audit_event(
            actor_type="user",
            actor_id=user_id or "anonymous",
            action="auth.login.failure",
            metadata={"email": email.strip().lower(), "reason": reason},
        )


# ------------------------------------------------------------------
# Admin service exceptions
# ------------------------------------------------------------------

class BootstrapConflictError(Exception):
    """Raised when bootstrap is called but users already exist."""


class DuplicateUserError(Exception):
    """Raised when a user with the given email already exists."""


class AdminUserNotFoundError(Exception):
    """Raised when the target user is not found."""


class LastAdminError(Exception):
    """Raised when an operation would remove the last active admin."""


class InvalidRolesError(Exception):
    """Raised when unknown role names are provided."""


# Sentinel for "field not provided" in update_user.
_UNSET: object = object()


class AdminService:
    """Local admin operations: bootstrap, user management, audit."""

    def __init__(self, repository: AuthRepository) -> None:
        self.repository = repository

    def _user_payload(self, user: User) -> dict:
        roles = self.repository.get_user_roles(user.user_id)
        return {
            "user_id": user.user_id,
            "email": user.email,
            "display_name": user.display_name,
            "status": user.status,
            "roles": sorted(roles),
            "created_at": user.created_at,
            "updated_at": user.updated_at,
            "last_login_at": user.last_login_at,
        }

    def bootstrap_admin(
        self,
        email: str,
        password: str,
        display_name: str | None = None,
    ) -> dict:
        """Create the first admin. Raises BootstrapConflictError if any user exists."""
        try:
            normalized = normalize_email(email)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        password_hash = hash_password(password)
        try:
            user = self.repository.bootstrap_first_admin(
                email=normalized,
                password_hash=password_hash,
                display_name=display_name,
            )
        except (FirstAdminExistsError, DuplicateEmailError) as exc:
            raise BootstrapConflictError(str(exc)) from exc
        self.repository.append_audit_event(
            actor_type="system",
            actor_id="bootstrap",
            action="auth.bootstrap_admin.created",
            target_type="user",
            target_id=user.user_id,
            metadata={"email": user.email},
        )
        return self._user_payload(user)

    def create_user(
        self,
        *,
        email: str,
        password: str,
        display_name: str | None = None,
        roles: list[str],
        actor_id: str,
    ) -> dict:
        unknown = set(roles) - BUILTIN_ROLES
        if unknown:
            raise InvalidRolesError(f"Unknown roles: {sorted(unknown)}")
        try:
            normalized = normalize_email(email)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        password_hash = hash_password(password)
        try:
            user = self.repository.create_user(
                email=normalized, display_name=display_name, status="active"
            )
        except DuplicateEmailError as exc:
            raise DuplicateUserError(str(exc)) from exc
        self.repository.create_local_credential(user.user_id, password_hash)
        self.repository.set_user_roles(user.user_id, set(roles))
        self.repository.append_audit_event(
            actor_type="user",
            actor_id=actor_id,
            action="auth.admin.user_created",
            target_type="user",
            target_id=user.user_id,
            metadata={"email": user.email, "roles": sorted(roles)},
        )
        return self._user_payload(user)

    def list_users(self, offset: int = 0, limit: int = 100) -> list[dict]:
        users = self.repository.list_users(offset=offset, limit=limit)
        return [self._user_payload(u) for u in users]

    def get_user(self, user_id: str) -> dict | None:
        user = self.repository.get_user(user_id)
        if user is None:
            return None
        return self._user_payload(user)

    def update_user(
        self,
        user_id: str,
        actor_id: str,
        *,
        display_name: object = _UNSET,
        roles: object = _UNSET,
    ) -> dict:
        user = self.repository.get_user(user_id)
        if user is None:
            raise AdminUserNotFoundError(f"User not found: {user_id!r}")
        if display_name is not _UNSET:
            self.repository.set_user_display_name(user_id, display_name)  # type: ignore[arg-type]
        if roles is not _UNSET:
            role_set = set(roles)  # type: ignore[arg-type]
            unknown = role_set - BUILTIN_ROLES
            if unknown:
                raise InvalidRolesError(f"Unknown roles: {sorted(unknown)}")
            current_roles = self.repository.get_user_roles(user_id)
            if "admin" in current_roles and "admin" not in role_set:
                if self.repository.count_active_admin_users() <= 1:
                    raise LastAdminError("Cannot demote the last active admin")
            self.repository.set_user_roles(user_id, role_set)
            self.repository.append_audit_event(
                actor_type="user",
                actor_id=actor_id,
                action="auth.admin.user_roles_changed",
                target_type="user",
                target_id=user_id,
                metadata={"roles": sorted(role_set)},
            )
        updated = self.repository.get_user(user_id)
        assert updated is not None
        return self._user_payload(updated)

    def disable_user(self, user_id: str, actor_id: str) -> dict:
        user = self.repository.get_user(user_id)
        if user is None:
            raise AdminUserNotFoundError(f"User not found: {user_id!r}")
        roles = self.repository.get_user_roles(user_id)
        if "admin" in roles and self.repository.count_active_admin_users() <= 1:
            raise LastAdminError("Cannot disable the last active admin")
        self.repository.set_user_status(user_id, "disabled")
        self.repository.revoke_user_sessions(user_id)
        self.repository.append_audit_event(
            actor_type="user",
            actor_id=actor_id,
            action="auth.admin.user_disabled",
            target_type="user",
            target_id=user_id,
        )
        updated = self.repository.get_user(user_id)
        assert updated is not None
        return self._user_payload(updated)

    def enable_user(self, user_id: str, actor_id: str) -> dict:
        user = self.repository.get_user(user_id)
        if user is None:
            raise AdminUserNotFoundError(f"User not found: {user_id!r}")
        self.repository.set_user_status(user_id, "active")
        self.repository.append_audit_event(
            actor_type="user",
            actor_id=actor_id,
            action="auth.admin.user_enabled",
            target_type="user",
            target_id=user_id,
        )
        updated = self.repository.get_user(user_id)
        assert updated is not None
        return self._user_payload(updated)
