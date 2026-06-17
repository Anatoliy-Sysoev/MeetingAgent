"""Tests for secret_strength helper (MA-AUTH-SECRET-STRENGTH-AND-TRUSTED-PROXY #86)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.auth.secret_strength import (  # noqa: E402
    SecretStrengthResult,
    validate_secret_strength,
)


# ---------------------------------------------------------------------------
# Repeated single character
# ---------------------------------------------------------------------------

def test_secret_strength_rejects_repeated_single_character_a() -> None:
    result = validate_secret_strength("a" * 40)
    assert not result.ok
    assert result.reason is not None
    assert "repeated" in result.reason.lower() or "entropy" in result.reason.lower()


def test_secret_strength_rejects_repeated_single_character_1() -> None:
    result = validate_secret_strength("1" * 36)
    assert not result.ok


def test_secret_strength_rejects_repeated_single_character_x() -> None:
    result = validate_secret_strength("x" * 32)
    assert not result.ok


# ---------------------------------------------------------------------------
# Repeated short block
# ---------------------------------------------------------------------------

def test_secret_strength_rejects_repeated_short_block_abc() -> None:
    result = validate_secret_strength("abcabcabcabcabcabcabcabcabcabcabcabc")
    assert not result.ok


def test_secret_strength_rejects_repeated_short_block_token() -> None:
    result = validate_secret_strength("token-token-token-token-token-token-token-token")
    assert not result.ok


def test_secret_strength_rejects_repeated_short_block_change_me() -> None:
    result = validate_secret_strength("change-me-change-me-change-me-change-me")
    assert not result.ok


def test_secret_strength_rejects_12341234() -> None:
    result = validate_secret_strength("12341234123412341234123412341234")
    assert not result.ok


# ---------------------------------------------------------------------------
# Placeholder words
# ---------------------------------------------------------------------------

def test_secret_strength_rejects_placeholder_word() -> None:
    result = validate_secret_strength("placeholder-string-of-enough-length-to-pass")
    assert not result.ok


def test_secret_strength_rejects_changeme_word() -> None:
    result = validate_secret_strength("changeme-this-value-to-something-stronger-now")
    assert not result.ok


def test_secret_strength_rejects_example_token() -> None:
    result = validate_secret_strength("example-token-from-documentation-replace-this")
    assert not result.ok


# ---------------------------------------------------------------------------
# Too short
# ---------------------------------------------------------------------------

def test_secret_strength_rejects_too_short() -> None:
    result = validate_secret_strength("shortvalue")
    assert not result.ok
    assert "short" in (result.reason or "").lower() or "minimum" in (result.reason or "").lower()


def test_secret_strength_rejects_empty() -> None:
    result = validate_secret_strength("")
    assert not result.ok


def test_secret_strength_custom_min_length() -> None:
    # 32-char random value passes default but fails min_length=64
    value = "r7NQx4vP9zK2mT6aY8sD3fG5hJ1kL0pW"
    assert validate_secret_strength(value).ok
    assert not validate_secret_strength(value, min_length=64).ok


# ---------------------------------------------------------------------------
# Valid random-looking values
# ---------------------------------------------------------------------------

def test_secret_strength_accepts_random_looking_value_1() -> None:
    assert validate_secret_strength("r7NQx4vP9zK2mT6aY8sD3fG5hJ1kL0pW").ok


def test_secret_strength_accepts_random_looking_value_2() -> None:
    assert validate_secret_strength("Xq2A9mP7vR4tY8nB6cD1eF3gH5jK0sLz").ok


def test_secret_strength_accepts_urlsafe_token() -> None:
    import secrets
    tok = secrets.token_urlsafe(48)
    assert validate_secret_strength(tok).ok


# ---------------------------------------------------------------------------
# Secret redaction: reason must never contain the value
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("secret", [
    "a" * 40,
    "abcabcabcabcabcabcabcabcabcabcabcabc",
    "token-token-token-token-token-token-token",
    "change-me-change-me-change-me-change-me",
])
def test_secret_strength_reason_does_not_expose_secret_value(secret: str) -> None:
    result = validate_secret_strength(secret)
    assert not result.ok
    assert secret not in (result.reason or ""), (
        f"Secret value leaked in reason: {result.reason!r}"
    )


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------

def test_secret_strength_result_is_dataclass() -> None:
    result = validate_secret_strength("r7NQx4vP9zK2mT6aY8sD3fG5hJ1kL0pW")
    assert isinstance(result, SecretStrengthResult)
    assert result.ok is True
    assert result.reason is None
