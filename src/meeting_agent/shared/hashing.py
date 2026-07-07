from __future__ import annotations

import hashlib


def stable_id(value: str, length: int = 24) -> str:
    return hashlib.sha256(str(value).encode("utf-8", errors="replace")).hexdigest()[:length]
