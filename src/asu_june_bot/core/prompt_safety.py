"""Prompt-safety helpers shared by project chat and meeting QA prompt builders.

Retrieved source text is untrusted.  The prompt wraps each source in
``[BEGIN UNTRUSTED SOURCE Sn]`` / ``[END UNTRUSTED SOURCE Sn]`` delimiters
(#90).  An adversarial document could embed its own fake delimiter line to
"close" the block early and smuggle instruction-looking text outside the
delimiter contract.  ``neutralize_source_delimiters`` rewrites any such
marker inside untrusted content to an inert placeholder before the real
delimiters are applied.
"""
from __future__ import annotations

import re

# Case-insensitive, whitespace-tolerant match for fake source delimiters,
# e.g. "[END UNTRUSTED SOURCE S1]", "[ begin   untrusted source S99 ]".
_FAKE_DELIMITER_RE = re.compile(
    r"\[\s*(?:BEGIN|END)\s+UNTRUSTED\s+SOURCE\b[^\]\n]*\]?",
    re.IGNORECASE,
)

NEUTRALIZED_MARKER = "[NEUTRALIZED SOURCE MARKER]"


def neutralize_source_delimiters(text: str) -> str:
    """Replace fake untrusted-source delimiters inside text with an inert marker.

    Legitimate content is otherwise unchanged.  Idempotent: the replacement
    marker does not match the pattern, so repeated application is a no-op.
    """
    if not text or "[" not in text:
        return text
    return _FAKE_DELIMITER_RE.sub(NEUTRALIZED_MARKER, text)
