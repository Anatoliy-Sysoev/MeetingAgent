from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.chat.models import ChatResponse, ChatSource  # noqa: E402
from asu_june_bot.eval.checks import run_checks  # noqa: E402
from asu_june_bot.eval.models import EvalCase  # noqa: E402


def test_eval_checks_pass_for_answered_response() -> None:
    case = EvalCase(
        case_id="PROJECT-AD-001",
        query="СоИ AD как происходит авторизация пользователей?",
        expected_status="answered",
        expected_llm_called=True,
        expected_citation_required=True,
        expected_min_sources=1,
        must_include=["AD"],
        must_not_include=["OAuth"],
        expected_source_title_contains=["AD"],
    )
    response = ChatResponse(
        status="answered",
        query=case.query,
        answer="Авторизация использует AD. [S1]",
        sources=[ChatSource(source_ref="S1", title="ЦП УПКС_СоИ_AD")],
        diagnostics={"llm_called": True},
    )

    checks = run_checks(case, response)

    assert all(check.passed for check in checks)


def test_eval_checks_find_failures() -> None:
    case = EvalCase(
        case_id="PROJECT-AD-001",
        query="СоИ AD как происходит авторизация пользователей?",
        expected_status="answered",
        expected_llm_called=True,
        expected_citation_required=True,
        expected_min_sources=2,
        must_include=["AD"],
        must_not_include=["OAuth"],
        expected_source_title_contains=["AD"],
    )
    response = ChatResponse(
        status="validation_failed",
        query=case.query,
        answer="Ответ про OAuth без ссылки",
        sources=[ChatSource(source_ref="S1", title="Паспорт ИС")],
        diagnostics={"llm_called": False},
    )

    checks = run_checks(case, response)
    failed = {check.name for check in checks if not check.passed}

    assert "status" in failed
    assert "llm_called" in failed
    assert "must_include" in failed
    assert "must_not_include" in failed
    assert "citations" in failed
    assert "min_sources" in failed
    assert "source_titles" in failed
