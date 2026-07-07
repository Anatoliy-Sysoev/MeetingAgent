from __future__ import annotations

MAX_QUERY_CHARS = 2000


def validate_query_length(query: str, *, max_chars: int = MAX_QUERY_CHARS) -> None:
    if len(query or "") > max_chars:
        raise ValueError(f"Query is too long: max {max_chars} characters")
