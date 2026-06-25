"""Unit tests for the pure guard decision API.

All tests are deterministic: no LLM, no retrieval, no network, no disk I/O.
Query strings are chosen to exercise known branches of the rule-based pipeline:

    IN_PROJECT (no ambiguous segments)   → allow
    OUT_OF_PROJECT                       → refuse
    MIXED                                → refuse
    META                                 → clarify
    AMBIGUOUS                            → clarify
    Empty / blank                        → clarify (ambiguous scope)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.guard.decision import (  # noqa: E402
    VALID_DECISIONS,
    GuardDecisionResult,
    evaluate_guard_decision,
)


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------

def test_returns_guard_decision_result() -> None:
    result = evaluate_guard_decision("Какова архитектура интеграции АСУ ТТ с КШД?")
    assert isinstance(result, GuardDecisionResult)


def test_decision_is_valid_string() -> None:
    result = evaluate_guard_decision("Какова архитектура интеграции АСУ ТТ с КШД?")
    assert result.decision in VALID_DECISIONS


def test_result_is_immutable() -> None:
    result = evaluate_guard_decision("АСУ ТТ")
    with pytest.raises((AttributeError, TypeError)):
        result.decision = "refuse"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ALLOW — clear in-project query (ASU project markers, no out-of-scope segments)
# ---------------------------------------------------------------------------

def test_in_scope_asu_query_returns_allow() -> None:
    # "postgresql" and "асу тт" are strong PROJECT_MARKERS.
    result = evaluate_guard_decision("Какая версия PostgreSQL используется в АСУ ТТ?")
    assert result.decision == "allow"


def test_in_scope_ftt_query_returns_allow() -> None:
    result = evaluate_guard_decision("Какие требования предъявляются к интеграции ФТТ?")
    assert result.decision == "allow"


def test_allow_result_has_reason() -> None:
    result = evaluate_guard_decision("Какова архитектура интеграции АСУ ТТ с КШД?")
    assert result.decision == "allow"
    assert result.reason is not None and len(result.reason) > 0


def test_allow_result_has_confidence() -> None:
    result = evaluate_guard_decision("Какова архитектура интеграции АСУ ТТ с КШД?")
    assert result.decision == "allow"
    assert isinstance(result.confidence, float)
    assert 0.0 <= result.confidence <= 1.0


def test_allow_metadata_flags(tmp_path: Path) -> None:
    result = evaluate_guard_decision("Какова архитектура интеграции АСУ ТТ с КШД?")
    assert result.decision == "allow"
    assert result.metadata["has_in_project"] is True
    assert result.metadata["has_out_of_project"] is False


# ---------------------------------------------------------------------------
# REFUSE — out-of-project query
# ---------------------------------------------------------------------------

def test_out_of_scope_weather_returns_refuse() -> None:
    # "погода" is an OUT_OF_PROJECT_MARKER.
    result = evaluate_guard_decision("Какая сегодня погода в Москве?")
    assert result.decision == "refuse"


def test_out_of_scope_code_generation_returns_refuse() -> None:
    # Generation verb + code noun triggers abuse detection path.
    result = evaluate_guard_decision("Напиши Python код для сортировки массива")
    assert result.decision == "refuse"


def test_refuse_result_has_reason() -> None:
    result = evaluate_guard_decision("Какая сегодня погода в Москве?")
    assert result.decision == "refuse"
    assert result.reason is not None


def test_refuse_metadata_flags() -> None:
    result = evaluate_guard_decision("Какая сегодня погода в Москве?")
    assert result.decision == "refuse"
    assert result.metadata["has_out_of_project"] is True


# ---------------------------------------------------------------------------
# CLARIFY — meta / ambiguous query
# ---------------------------------------------------------------------------

def test_meta_query_returns_clarify() -> None:
    # "какие документы" is a META_MARKER (no project object specified).
    result = evaluate_guard_decision("Какие документы есть по проекту?")
    assert result.decision == "clarify"


def test_ambiguous_empty_query_returns_clarify() -> None:
    result = evaluate_guard_decision("")
    assert result.decision == "clarify"


def test_ambiguous_blank_query_returns_clarify() -> None:
    result = evaluate_guard_decision("   ")
    assert result.decision == "clarify"


def test_clarify_result_has_reason() -> None:
    result = evaluate_guard_decision("Найди нужное")
    assert result.decision == "clarify"
    assert result.reason is not None


# ---------------------------------------------------------------------------
# Metadata structure
# ---------------------------------------------------------------------------

def test_metadata_contains_expected_keys() -> None:
    result = evaluate_guard_decision("АСУ ТТ postgresql интеграция")
    for key in ("has_in_project", "has_out_of_project", "has_meta", "has_ambiguous", "has_mixed_segment"):
        assert key in result.metadata, f"Missing metadata key: {key}"


def test_matched_rule_is_scope_string() -> None:
    result = evaluate_guard_decision("АСУ ТТ postgresql интеграция")
    valid_scopes = {"in_project", "out_of_project", "meta", "ambiguous", "mixed"}
    assert result.matched_rule in valid_scopes


# ---------------------------------------------------------------------------
# No LLM / network — verified implicitly by speed: pure rule-based is < 1s
# ---------------------------------------------------------------------------

def test_pure_api_completes_without_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guard must not open sockets. Monkeypatch socket.socket to fail if called."""
    import socket as _socket

    original_socket = _socket.socket

    def _no_network(*args, **kwargs):
        raise RuntimeError("evaluate_guard_decision must not make network calls")

    monkeypatch.setattr(_socket, "socket", _no_network)
    # Should succeed without touching socket.
    result = evaluate_guard_decision("Какова архитектура интеграции АСУ ТТ?")
    assert result.decision in VALID_DECISIONS
    monkeypatch.setattr(_socket, "socket", original_socket)


# ---------------------------------------------------------------------------
# Determinism — same query always returns same decision
# ---------------------------------------------------------------------------

def test_decision_is_deterministic() -> None:
    query = "Какова архитектура интеграции АСУ ТТ с КШД?"
    results = [evaluate_guard_decision(query) for _ in range(3)]
    assert all(r.decision == results[0].decision for r in results)
    assert all(r.reason == results[0].reason for r in results)
