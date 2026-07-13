from __future__ import annotations


NO_ANSWER_MARKERS = (
    "в переданных источниках данных недостаточно",
    "в предоставленных источниках информации для ответа",
    "в источниках нет информации",
    "нет данных для ответа",
    "недостаточно данных",
)


def has_no_answer_marker(text: str) -> bool:
    lowered = (text or "").lower()
    return any(marker in lowered for marker in NO_ANSWER_MARKERS)
