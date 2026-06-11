from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass, field
from typing import Any

from asu_june_bot.auth.permissions import BUILTIN_ROLES, permissions_for_roles

USER_STATUSES: frozenset[str] = frozenset({"active", "disabled"})
PRINCIPAL_TYPES: frozenset[str] = frozenset({"user", "machine"})


def now_iso() -> str:
    return datetime.datetime.now(tz=datetime.timezone.utc).isoformat(timespec="seconds")


def new_id() -> str:
    return str(uuid.uuid4())


def normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if not normalized or "@" not in normalized:
        raise ValueError(f"Invalid email: {email!r}")
    return normalized


@dataclass(frozen=True)
class Principal:
    """Authenticated identity with resolved local roles and permissions."""

    principal_type: str  # user | machine
    principal_id: str
    provider: str
    roles: frozenset[str] = frozenset()
    permissions: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if self.principal_type not in PRINCIPAL_TYPES:
            raise ValueError(f"Invalid principal_type: {self.principal_type!r}")
        object.__setattr__(self, "roles", frozenset(self.roles))
        object.__setattr__(self, "permissions", frozenset(self.permissions))
        if self.principal_type == "user":
            unknown = self.roles - BUILTIN_ROLES
            if unknown:
                raise ValueError(f"Unknown roles for user principal: {sorted(unknown)}")
            expected = permissions_for_roles(self.roles)
            if self.permissions != expected:
                raise ValueError(
                    "User principal permissions must equal permissions_for_roles(roles); "
                    "use Principal.for_user() to construct correctly"
                )

    def has_permission(self, permission: str) -> bool:
        return permission in self.permissions

    def has_role(self, role: str) -> bool:
        return role in self.roles

    @classmethod
    def for_user(cls, user_id: str, provider: str, roles: frozenset[str]) -> Principal:
        return cls(
            principal_type="user",
            principal_id=user_id,
            provider=provider,
            roles=roles,
            permissions=permissions_for_roles(roles),
        )


@dataclass
class User:
    user_id: str
    email: str
    display_name: str | None = None
    status: str = "active"
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    last_login_at: str | None = None

    def __post_init__(self) -> None:
        self.email = normalize_email(self.email)
        if self.status not in USER_STATUSES:
            raise ValueError(f"Invalid user status: {self.status!r}")


@dataclass
class LocalCredential:
    user_id: str
    password_hash: str
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)


@dataclass
class ExternalIdentity:
    """Normalized identity returned by an external provider.

    Placeholder for future yandex/google/oidc tasks — no OAuth logic here.
    """

    identity_id: str
    user_id: str
    provider: str
    subject: str
    email: str | None = None
    email_verified: bool = False
    display_name: str | None = None
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)


@dataclass
class Session:
    """Server-side session. The browser only ever sees the opaque token;
    the database stores its sha256 digest (token_hash)."""

    session_id: str
    user_id: str
    token_hash: str
    created_at: str = field(default_factory=now_iso)
    expires_at: str = ""
    revoked_at: str | None = None

    def is_active(self, at: str | None = None) -> bool:
        moment = at or now_iso()
        if self.revoked_at is not None:
            return False
        return moment < self.expires_at


@dataclass
class AuditEvent:
    event_id: str
    actor_type: str
    actor_id: str
    action: str
    target_type: str | None = None
    target_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=now_iso)
