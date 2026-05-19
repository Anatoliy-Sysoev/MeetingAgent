from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.chat.models import ChatResponse, ChatSource  # noqa: E402
from asu_june_bot.eval.models import EvalCase  # noqa: E402
from asu_june_bot.eval.runner import EvalRunner  # noqa: E402


class FakeChatService:
    def chat(self, request):
        if "погода" in request.query.lower():
            return ChatResponse(
                status="refused",
                query=request.query,
                answer="Я отвечаю только по материалам проекта ЦП УПКС.",
                sources=[],
                diagnostics={"llm_called": False, "search_status": "refused"},
            )
        return ChatResponse(
            status="answered",
            query=request.query,
            answer="Авторизация использует AD. [S1]",
            sources=[ChatSource(source_ref="S1", title="ЦП УПКС_СоИ_AD")],
            diagnostics={"llm_called": True, "search_status": "ok", "llm_model": "fake-model"},
        )


def test_eval_runner_executes_cases() -> None:
    cases = [
        EvalCase(
            case_id="PROJECT-AD-001",
            category="project_question",
            priority="high",
            query="СоИ AD как происходит авторизация пользователей?",
            expected_status="answered",
            expected_llm_called=True,
            expected_citation_required=True,
            expected_min_sources=1,
            must_include=["AD"],
            expected_source_title_contains=["AD"],
        ),
        EvalCase(
            case_id="REFUSE-WEATHER-001",
            category="out_of_scope",
            priority="high",
            query="Какая погода завтра в Москве?",
            expected_status="refused",
            expected_llm_called=False,
            expected_citation_required=False,
            expected_min_sources=0,
            must_include=["проект"],
        ),
    ]

    report = EvalRunner(chat_service=FakeChatService()).run(cases)

    assert report.total == 2
    assert report.passed == 2
    assert report.failed == 0
    assert report.to_dict()["summary"]["by_category"]["project_question"]["passed"] == 1
