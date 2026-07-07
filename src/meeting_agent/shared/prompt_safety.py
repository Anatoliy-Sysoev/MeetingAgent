"""Prompt-safety helpers for untrusted retrieved sources."""
from __future__ import annotations

import re

_FAKE_DELIMITER_RE = re.compile(
    r"\[\s*(?:BEGIN|END)\s+UNTRUSTED\s+SOURCE\b[^\]\n]*\]?",
    re.IGNORECASE,
)

NEUTRALIZED_MARKER = "[NEUTRALIZED SOURCE MARKER]"


def neutralize_source_delimiters(text: str) -> str:
    """Replace fake untrusted-source delimiters inside text with an inert marker."""
    if not text or "[" not in text:
        return text
    return _FAKE_DELIMITER_RE.sub(NEUTRALIZED_MARKER, text)
