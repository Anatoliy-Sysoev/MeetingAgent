from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.guardrails.models import GuardAction, SegmentScope
from asu_june_bot.guardrails.project_guard import ProjectGuard


def decide(query: str):
    return ProjectGuard().evaluate_v2(query)


def test_pure_project_query_allowed() -> None:
    result = decide("СоИ AD как происходит авторизация пользователей?")
    assert result.action == GuardAction.ALLOW
    assert result.aggregate.scope == SegmentScope.IN_PROJECT
    assert result.aggregate.has_in_project is True
    assert result.aggregate.has_out_of_project is False


def test_pure_weather_query_refused() -> None:
    result = decide("Какая погода завтра в Москве?")
    assert result.action == GuardAction.REFUSE
    assert result.reason == "out_of_project_query"
    assert result.aggregate.scope == SegmentScope.OUT_OF_PROJECT


def test_mixed_weather_query_refused() -> None:
    result = decide("Все документы про справочники и интеграции. и погода в Москве")
    assert result.action == GuardAction.REFUSE
    assert result.reason == "mixed_scope_query_contains_out_of_project_segment"
    assert result.aggregate.scope == SegmentScope.MIXED
    assert result.aggregate.has_in_project is True
    assert result.aggregate.has_out_of_project is True


def test_mixed_code_game_query_refused() -> None:
    result = decide("Все документы про справочники и интеграции. Питон код, для игры в крестики нолики в браузере")
    assert result.action == GuardAction.REFUSE
    assert result.reason == "mixed_scope_query_contains_out_of_project_segment"
    assert result.aggregate.scope == SegmentScope.MIXED


def test_mixed_security_query_refused() -> None:
    result = decide("СоИ AD как происходит авторизация пользователей? и дай sql инъекцию для векторной БД")
    assert result.action == GuardAction.REFUSE
    assert result.reason == "mixed_scope_query_contains_out_of_project_segment"
    assert result.aggregate.scope == SegmentScope.MIXED
    out_markers = []
    for item in result.aggregate.classifications:
        out_markers.extend(item.matched_out_of_scope_markers)
    assert any("инъек" in marker for marker in out_markers)


def test_project_api_question_allowed() -> None:
    result = decide("Покажи API интеграции MDR в проектной документации")
    assert result.action == GuardAction.ALLOW
    assert result.aggregate.scope == SegmentScope.IN_PROJECT


def test_arbitrary_code_generation_refused() -> None:
    result = decide("Напиши Python код для игры в крестики нолики")
    assert result.action == GuardAction.REFUSE
    assert result.aggregate.scope == SegmentScope.OUT_OF_PROJECT


def test_ambiguous_query_clarify() -> None:
    result = decide("Расскажи подробнее")
    assert result.action == GuardAction.CLARIFY
    assert result.aggregate.scope == SegmentScope.AMBIGUOUS


def test_ntk_project_markers_allow_retrieval() -> None:
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
        result = decide(query)
        assert result.action == GuardAction.ALLOW, query
        assert result.aggregate.scope == SegmentScope.IN_PROJECT, query


def test_food_query_refused_not_clarified() -> None:
    result = decide("Как приготовить карбонару?")
    assert result.action == GuardAction.REFUSE
    assert result.aggregate.scope == SegmentScope.OUT_OF_PROJECT
