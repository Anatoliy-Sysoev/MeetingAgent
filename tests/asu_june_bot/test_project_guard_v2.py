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
