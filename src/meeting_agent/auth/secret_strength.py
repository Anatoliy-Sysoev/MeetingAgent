"""Secret strength validation for self-hosted deployments.

Detects secrets that satisfy minimum length but are still weak:
  - single repeated character  (e.g. "aaaaaaaaaa…")
  - repeated short block       (e.g. "abcabc…", "token-token-token-…")
  - known placeholder patterns (e.g. "changeme", "<strong-random>")
  - too short

Usage::

    result = validate_secret_strength(value, min_length=32)
    if not result.ok:
        # result.reason describes the problem, never the value
        ...
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_PLACEHOLDER_RE = re.compile(
    r"(?i)(placeholder|changeme|example|your[_-]?token|strong[_-]?random"
    r"|secret|<[^>]+>|todo|fixme|replace[_-]?me|test[_-]?token)",
)

DEFAULT_MIN_SECRET_LENGTH = 32


def is_placeholder(value: str) -> bool:
    return bool(_PLACEHOLDER_RE.search(value))


@dataclass(frozen=True)
class SecretStrengthResult:
    ok: bool
    reason: str | None = None


def _is_repeated_single_char(value: str) -> bool:
    return len(set(value)) <= 1


def _is_repeated_short_block(value: str, *, max_block: int = 12) -> bool:
    """Return True if value is just a short block repeated 3+ times.

    Catches patterns such as:
      abcabcabc              (block="abc", reps=3)
      token-token-token-     (block="token-", reps=3)
      abcabcabcabc           (block="abcabc" but reps from len 3 = 4)
    """
    n = len(value)
    for block_len in range(1, min(max_block + 1, n // 2 + 1)):
        block = value[:block_len]
        reps, remainder = divmod(n, block_len)
        if reps >= 3 and value == block * reps + block[:remainder]:
            return True
    return False


def validate_secret_strength(
    value: str,
    *,
    min_length: int = DEFAULT_MIN_SECRET_LENGTH,
) -> SecretStrengthResult:
    """Return a SecretStrengthResult without ever including the value in reason.

    Args:
        value:      The secret to validate.
        min_length: Minimum required character count.

    Returns:
        SecretStrengthResult(ok=True) when the secret passes all checks.
        SecretStrengthResult(ok=False, reason=<human text>) otherwise.
    """
    if not value:
        return SecretStrengthResult(ok=False, reason="Secret is empty.")
    if len(value) < min_length:
        return SecretStrengthResult(
            ok=False,
            reason=f"Secret is too short — minimum {min_length} characters required.",
        )
    if is_placeholder(value):
        return SecretStrengthResult(
            ok=False, reason="Secret appears to be a placeholder or documentation example."
        )
    if _is_repeated_single_char(value):
        return SecretStrengthResult(
            ok=False, reason="Secret is a single repeated character and has no entropy."
        )
    if _is_repeated_short_block(value):
        return SecretStrengthResult(
            ok=False, reason="Secret is a short pattern repeated many times and has low entropy."
        )
    return SecretStrengthResult(ok=True)
