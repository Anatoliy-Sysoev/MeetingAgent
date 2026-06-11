from __future__ import annotations

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

# argon2-cffi defaults use Argon2id (type=Type.ID) with RFC 9106
# low-memory recommended parameters — fine for a local-first CPU host.
_hasher = PasswordHasher()

# Pre-computed hash used to equalize timing when the email is unknown
# or the user has no local credential.
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("Password must not be empty")
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    """True if the hash was produced with outdated parameters and should be updated."""
    try:
        return _hasher.check_needs_rehash(password_hash)
    except Exception:
        return False


def generate_csrf_token() -> str:
    """Return a new random opaque CSRF token."""
    return secrets.token_urlsafe(32)


def hash_csrf_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_csrf_token(csrf_token_hash: str, token: str) -> bool:
    """Constant-time comparison of supplied token against stored hash."""
    return secrets.compare_digest(csrf_token_hash, hash_csrf_token(token))


def dummy_verify(password: str) -> None:
    """Burn the same time as a real verification to hide whether the email exists."""
    try:
        _hasher.verify(_DUMMY_HASH, password)
    except VerifyMismatchError:
        pass
