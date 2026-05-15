from __future__ import annotations

import re

from .models import QuerySegment


# Do not split requirement numbers like 4.2.5 by dots.
# Split by sentence punctuation only when the punctuation is not between digits.
SPLIT_RE = re.compile(
    r"(?:\s*(?<!\d)[.!?;]+(?!\d)\s*|"
    r"\s+и\s+(?=(?:дай|напиши|сделай|покажи|расскажи|какая|какой|какие|курс|погода|sql|питон|python|код|игра|игры|как\s+обойти|как\s+скрыть)\b)|"
    r"\s+(?:потом|затем|в\s+конце|после\s+этого|между\s+делом|если\s+не\s+можешь)\s+)",
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
