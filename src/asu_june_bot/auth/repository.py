from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from asu_june_bot.auth.models import (
    USER_STATUSES,
    AuditEvent,
    ExternalIdentity,
    LocalCredential,
    Session,
    User,
    new_id,
    normalize_email,
    now_iso,
)
from asu_june_bot.auth.permissions import BUILTIN_ROLES

DEFAULT_DB_PATH = Path("data/meetingagent/auth.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS auth_users (
    user_id        TEXT PRIMARY KEY,
    email          TEXT NOT NULL UNIQUE,
    display_name   TEXT,
    status         TEXT NOT NULL DEFAULT 'active',
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    last_login_at  TEXT
);

CREATE TABLE IF NOT EXISTS auth_local_credentials (
    user_id        TEXT PRIMARY KEY REFERENCES auth_users(user_id) ON DELETE CASCADE,
    password_hash  TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS auth_external_identities (
    identity_id    TEXT PRIMARY KEY,
    user_id        TEXT NOT NULL REFERENCES auth_users(user_id) ON DELETE CASCADE,
    provider       TEXT NOT NULL,
    subject        TEXT NOT NULL,
    email          TEXT,
    email_verified INTEGER NOT NULL DEFAULT 0,
    display_name   TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    UNIQUE (provider, subject)
);

CREATE TABLE IF NOT EXISTS auth_roles (
    role_name      TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS auth_user_roles (
    user_id        TEXT NOT NULL REFERENCES auth_users(user_id) ON DELETE CASCADE,
    role_name      TEXT NOT NULL REFERENCES auth_roles(role_name) ON DELETE CASCADE,
    PRIMARY KEY (user_id, role_name)
);

CREATE TABLE IF NOT EXISTS auth_sessions (
    session_id     TEXT PRIMARY KEY,
    user_id        TEXT NOT NULL REFERENCES auth_users(user_id) ON DELETE CASCADE,
    token_hash     TEXT NOT NULL UNIQUE,
    created_at     TEXT NOT NULL,
    expires_at     TEXT NOT NULL,
    revoked_at     TEXT
);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id ON auth_sessions (user_id);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires_at ON auth_sessions (expires_at);

CREATE TABLE IF NOT EXISTS auth_audit_events (
    event_id       TEXT PRIMARY KEY,
    actor_type     TEXT NOT NULL,
    actor_id       TEXT NOT NULL,
    action         TEXT NOT NULL,
    target_type    TEXT,
    target_id      TEXT,
    metadata_json  TEXT NOT NULL DEFAULT '{}',
    created_at     TEXT NOT NULL
);
"""


class AuthRepositoryError(RuntimeError):
    pass


class DuplicateEmailError(AuthRepositoryError):
    pass


class DuplicateIdentityError(AuthRepositoryError):
    pass


class UserNotFoundError(AuthRepositoryError):
    pass


class AuthRepository:
    """SQLite persistence for the auth domain. Schema setup is idempotent."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            # Idempotent schema migrations for existing databases.
            try:
                conn.execute(
                    "ALTER TABLE auth_sessions ADD COLUMN csrf_token_hash TEXT"
                )
            except sqlite3.OperationalError:
                pass  # Column already exists
            for role in sorted(BUILTIN_ROLES):
                conn.execute(
                    "INSERT OR IGNORE INTO auth_roles (role_name) VALUES (?)", (role,)
                )

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------

    def create_user(
        self,
        *,
        email: str,
        display_name: str | None = None,
        status: str = "active",
    ) -> User:
        user = User(user_id=new_id(), email=email, display_name=display_name, status=status)
        with self._connect() as conn:
            try:
                conn.execute(
                    "INSERT INTO auth_users "
                    "(user_id, email, display_name, status, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (user.user_id, user.email, user.display_name, user.status,
                     user.created_at, user.updated_at),
                )
            except sqlite3.IntegrityError as exc:
                raise DuplicateEmailError(f"Email already registered: {user.email}") from exc
        return user

    def _row_to_user(self, row: sqlite3.Row) -> User:
        return User(
            user_id=row["user_id"],
            email=row["email"],
            display_name=row["display_name"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_login_at=row["last_login_at"],
        )

    def get_user(self, user_id: str) -> User | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM auth_users WHERE user_id = ?", (user_id,)
            ).fetchone()
        return self._row_to_user(row) if row else None

    def get_user_by_email(self, email: str) -> User | None:
        normalized = normalize_email(email)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM auth_users WHERE email = ?", (normalized,)
            ).fetchone()
        return self._row_to_user(row) if row else None

    def list_users(self, offset: int = 0, limit: int = 100) -> list[User]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM auth_users ORDER BY created_at, user_id LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [self._row_to_user(r) for r in rows]

    def set_user_status(self, user_id: str, status: str) -> None:
        if status not in USER_STATUSES:
            raise ValueError(f"Invalid user status: {status!r}")
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE auth_users SET status = ?, updated_at = ? WHERE user_id = ?",
                (status, now_iso(), user_id),
            )
            if cur.rowcount == 0:
                raise UserNotFoundError(f"User not found: {user_id!r}")

    # ------------------------------------------------------------------
    # Roles
    # ------------------------------------------------------------------

    def set_user_roles(self, user_id: str, roles: set[str] | frozenset[str]) -> None:
        unknown = set(roles) - BUILTIN_ROLES
        if unknown:
            raise ValueError(f"Unknown roles: {sorted(unknown)}")
        with self._connect() as conn:
            exists = conn.execute(
                "SELECT 1 FROM auth_users WHERE user_id = ?", (user_id,)
            ).fetchone()
            if not exists:
                raise UserNotFoundError(f"User not found: {user_id!r}")
            conn.execute("DELETE FROM auth_user_roles WHERE user_id = ?", (user_id,))
            conn.executemany(
                "INSERT INTO auth_user_roles (user_id, role_name) VALUES (?, ?)",
                [(user_id, role) for role in sorted(roles)],
            )

    def get_user_roles(self, user_id: str) -> frozenset[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT role_name FROM auth_user_roles WHERE user_id = ?", (user_id,)
            ).fetchall()
        return frozenset(r["role_name"] for r in rows)

    # ------------------------------------------------------------------
    # Local credentials
    # ------------------------------------------------------------------

    def create_local_credential(self, user_id: str, password_hash: str) -> LocalCredential:
        cred = LocalCredential(user_id=user_id, password_hash=password_hash)
        with self._connect() as conn:
            try:
                conn.execute(
                    "INSERT INTO auth_local_credentials "
                    "(user_id, password_hash, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (cred.user_id, cred.password_hash, cred.created_at, cred.updated_at),
                )
            except sqlite3.IntegrityError as exc:
                raise AuthRepositoryError(
                    f"Cannot store credential for user {user_id!r}"
                ) from exc
        return cred

    def get_local_credential(self, user_id: str) -> LocalCredential | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM auth_local_credentials WHERE user_id = ?", (user_id,)
            ).fetchone()
        if not row:
            return None
        return LocalCredential(
            user_id=row["user_id"],
            password_hash=row["password_hash"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def update_local_credential_hash(self, user_id: str, password_hash: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE auth_local_credentials SET password_hash = ?, updated_at = ? "
                "WHERE user_id = ?",
                (password_hash, now_iso(), user_id),
            )

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    def create_session(
        self,
        *,
        user_id: str,
        token_hash: str,
        expires_at: str,
        csrf_token_hash: str | None = None,
    ) -> Session:
        session = Session(
            session_id=new_id(),
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            csrf_token_hash=csrf_token_hash,
        )
        with self._connect() as conn:
            try:
                conn.execute(
                    "INSERT INTO auth_sessions "
                    "(session_id, user_id, token_hash, created_at, expires_at, revoked_at, "
                    " csrf_token_hash) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (session.session_id, session.user_id, session.token_hash,
                     session.created_at, session.expires_at, session.revoked_at,
                     session.csrf_token_hash),
                )
            except sqlite3.IntegrityError as exc:
                raise AuthRepositoryError(
                    f"Cannot create session for user {user_id!r}"
                ) from exc
        return session

    def _row_to_session(self, row: sqlite3.Row) -> Session:
        return Session(
            session_id=row["session_id"],
            user_id=row["user_id"],
            token_hash=row["token_hash"],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            revoked_at=row["revoked_at"],
            csrf_token_hash=row["csrf_token_hash"] if "csrf_token_hash" in row.keys() else None,
        )

    def get_session_by_token_hash(self, token_hash: str) -> Session | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM auth_sessions WHERE token_hash = ?", (token_hash,)
            ).fetchone()
        return self._row_to_session(row) if row else None

    def revoke_session(self, session_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE auth_sessions SET revoked_at = ? "
                "WHERE session_id = ? AND revoked_at IS NULL",
                (now_iso(), session_id),
            )

    def revoke_user_sessions(self, user_id: str) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE auth_sessions SET revoked_at = ? "
                "WHERE user_id = ? AND revoked_at IS NULL",
                (now_iso(), user_id),
            )
            return cur.rowcount

    def delete_expired_sessions(self) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM auth_sessions WHERE expires_at <= ?", (now_iso(),)
            )
            return cur.rowcount

    def set_last_login(self, user_id: str, at: str | None = None) -> None:
        moment = at or now_iso()
        with self._connect() as conn:
            conn.execute(
                "UPDATE auth_users SET last_login_at = ?, updated_at = ? WHERE user_id = ?",
                (moment, moment, user_id),
            )

    # ------------------------------------------------------------------
    # External identities
    # ------------------------------------------------------------------

    def link_external_identity(
        self,
        *,
        user_id: str,
        provider: str,
        subject: str,
        email: str | None = None,
        email_verified: bool = False,
        display_name: str | None = None,
    ) -> ExternalIdentity:
        identity = ExternalIdentity(
            identity_id=new_id(),
            user_id=user_id,
            provider=provider,
            subject=subject,
            email=email,
            email_verified=email_verified,
            display_name=display_name,
        )
        with self._connect() as conn:
            try:
                conn.execute(
                    "INSERT INTO auth_external_identities "
                    "(identity_id, user_id, provider, subject, email, email_verified, "
                    " display_name, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (identity.identity_id, identity.user_id, identity.provider,
                     identity.subject, identity.email, int(identity.email_verified),
                     identity.display_name, identity.created_at, identity.updated_at),
                )
            except sqlite3.IntegrityError as exc:
                msg = str(exc)
                if "provider" in msg or "subject" in msg or "UNIQUE" in msg:
                    raise DuplicateIdentityError(
                        f"Identity already linked: {provider}/{subject}"
                    ) from exc
                raise AuthRepositoryError(msg) from exc
        return identity

    def get_external_identity(self, provider: str, subject: str) -> ExternalIdentity | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM auth_external_identities WHERE provider = ? AND subject = ?",
                (provider, subject),
            ).fetchone()
        if not row:
            return None
        return ExternalIdentity(
            identity_id=row["identity_id"],
            user_id=row["user_id"],
            provider=row["provider"],
            subject=row["subject"],
            email=row["email"],
            email_verified=bool(row["email_verified"]),
            display_name=row["display_name"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # ------------------------------------------------------------------
    # Audit
    # ------------------------------------------------------------------

    def append_audit_event(
        self,
        *,
        actor_type: str,
        actor_id: str,
        action: str,
        target_type: str | None = None,
        target_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            event_id=new_id(),
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            metadata=metadata or {},
        )
        metadata_json = json.dumps(event.metadata, ensure_ascii=False, default=str)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO auth_audit_events "
                "(event_id, actor_type, actor_id, action, target_type, target_id, "
                " metadata_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (event.event_id, event.actor_type, event.actor_id, event.action,
                 event.target_type, event.target_id, metadata_json, event.created_at),
            )
        return event

    def list_audit_events(self, offset: int = 0, limit: int = 100) -> list[AuditEvent]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM auth_audit_events ORDER BY created_at DESC, event_id "
                "LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [
            AuditEvent(
                event_id=r["event_id"],
                actor_type=r["actor_type"],
                actor_id=r["actor_id"],
                action=r["action"],
                target_type=r["target_type"],
                target_id=r["target_id"],
                metadata=json.loads(r["metadata_json"]),
                created_at=r["created_at"],
            )
            for r in rows
        ]
