from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.auth.passwords import (  # noqa: E402
    dummy_verify,
    hash_password,
    verify_password,
)


def test_hash_uses_argon2id() -> None:
    assert hash_password("s3cret").startswith("$argon2id$")


def test_roundtrip_verify() -> None:
    h = hash_password("correct horse battery staple")
    assert verify_password(h, "correct horse battery staple")
    assert not verify_password(h, "wrong password")


def test_hash_is_salted() -> None:
    assert hash_password("same") != hash_password("same")


def test_empty_password_rejected() -> None:
    with pytest.raises(ValueError):
        hash_password("")


def test_garbage_hash_returns_false() -> None:
    assert not verify_password("not-a-hash", "anything")


def test_dummy_verify_does_not_raise() -> None:
    dummy_verify("whatever")
