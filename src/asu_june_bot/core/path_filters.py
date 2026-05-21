from __future__ import annotations

from fnmatch import fnmatchcase
from pathlib import Path
from typing import Iterable


def is_excluded_by_path_patterns(rel_path: Path | str, patterns: Iterable[str]) -> bool:
    normalized = str(rel_path).replace("\\", "/").strip("/").lower()
    if not normalized:
        return False

    for raw_pattern in patterns:
        pattern = str(raw_pattern).replace("\\", "/").strip("/").lower()
        if pattern and fnmatchcase(normalized, pattern):
            return True
    return False
