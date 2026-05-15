from __future__ import annotations

import re

from .models import QuerySegment


SPLIT_RE = re.compile(
    r"(?:\s*[.!?;]+\s*|\s+и\s+(?=(?:дай|напиши|сделай|покажи|расскажи|какая|какой|какие|курс|погода|sql|питон|python|код|игра|игры)\b))",
    re.IGNORECASE | re.UNICODE,
)


def normalize_query_text(text: str) -> str:
    return " ".join((text or "").replace("\u00a0", " ").split())


class QuerySegmenter:
    def split(self, query: str) -> list[QuerySegment]:
        normalized = normalize_query_text(query)
        if not normalized:
            return []

        raw_segments: list[QuerySegment] = []
        start = 0
        index = 1
        for match in SPLIT_RE.finditer(normalized):
            end = match.start()
            text = normalized[start:end].strip(" ,;.!?\t\n\r")
            if text:
                raw_segments.append(QuerySegment(index=index, text=text, start=start, end=end))
                index += 1
            start = match.end()

        tail = normalized[start:].strip(" ,;.!?\t\n\r")
        if tail:
            raw_segments.append(QuerySegment(index=index, text=tail, start=start, end=len(normalized)))

        if not raw_segments:
            return [QuerySegment(index=1, text=normalized, start=0, end=len(normalized))]

        return raw_segments
