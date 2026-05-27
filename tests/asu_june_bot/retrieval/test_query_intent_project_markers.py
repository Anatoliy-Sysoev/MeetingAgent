from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.retrieval.query_intent import QueryIntent, classify_query_intent  # noqa: E402


def test_ntk_project_markers_are_project_related() -> None:
    queries = [
        "Какие ограничения по производительности указаны для 2520 пользователей и 600 одновременно работающих пользователей?",
        "Какие требования к RTO и RPO описаны в архитектуре системы?",
        "Как в ПР реализована работа со статусами замечаний строительного контроля?",
        "Какие документы формируются автоматически после проведения инспекционной проверки?",
        "Какие группы AD app_ccpm используются для ролей строительного контроля?",
        "Как используется Bearer Token при интеграции MDR/НСИ?",
        "Что входит в Паспорт ИС и какие связанные документы в нём указаны?",
        "Какие ограничения есть на экспорт данных в PDF, Excel и CSV?",
    ]

    for query in queries:
        result = classify_query_intent(query)
        assert result.is_project_related is True, query
        assert result.intent != QueryIntent.OUT_OF_SCOPE_CANDIDATE, query


def test_food_query_is_out_of_scope_candidate() -> None:
    result = classify_query_intent("Как приготовить карбонару?")

    assert result.is_project_related is False
    assert result.intent == QueryIntent.OUT_OF_SCOPE_CANDIDATE
    assert any("карбонар" in marker for marker in result.matched_out_of_scope_markers)
