from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.chat.models import ChatSource  # noqa: E402
from asu_june_bot.chat.semantic_warnings import SemanticWarningAnalyzer, semantic_warnings_to_payload  # noqa: E402


def test_semantic_warnings_detect_weak_sources_and_low_source_count() -> None:
    analyzer = SemanticWarningAnalyzer()
    warnings = analyzer.analyze(
        answer="Авторизация описана в источнике. [S1]",
        sources=[ChatSource(source_ref="S1", title="СоИ AD")],
        search_payload={
            "context": {
                "diagnostics": {
                    "source_quality_filter": {
                        "results": {"weak_count": 1, "weak_reasons": {"short_text": 1}},
                        "primary_fallback_weak": True,
                    }
                }
            }
        },
        diagnostics={},
    )

    codes = {warning.code for warning in warnings}

    assert "weak_sources_present" in codes
    assert "weak_primary_fallback" in codes
    assert "low_source_count" in codes
    assert semantic_warnings_to_payload(warnings)["has_high"] is True


def test_semantic_warnings_detect_parent_expansion() -> None:
    analyzer = SemanticWarningAnalyzer()
    warnings = analyzer.analyze(
        answer="Авторизация описана в источниках. [S1] [S2]",
        sources=[ChatSource(source_ref="S1"), ChatSource(source_ref="S2")],
        search_payload={
            "context": {
                "diagnostics": {
                    "parent_expansion": {
                        "primary": {"expanded_count": 1},
                        "supporting": {"expanded_count": 0},
                    }
                }
            }
        },
        diagnostics={},
    )

    assert "parent_expansion_applied" in {warning.code for warning in warnings}


def test_semantic_warnings_do_not_hard_fail_clean_answer() -> None:
    analyzer = SemanticWarningAnalyzer()
    warnings = analyzer.analyze(
        answer="Авторизация описана в источниках. [S1] [S2]",
        sources=[ChatSource(source_ref="S1"), ChatSource(source_ref="S2")],
        search_payload={"context": {"diagnostics": {}}},
        diagnostics={},
    )

    assert [warning.to_dict() for warning in warnings] == []
