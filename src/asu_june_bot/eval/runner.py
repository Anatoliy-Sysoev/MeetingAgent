from __future__ import annotations

import time

from asu_june_bot.chat.models import ChatRequest
from asu_june_bot.chat.service import ChatService

from .checks import run_checks
from .models import EvalCase, EvalReport, EvalResult


class EvalRunner:
    def __init__(self, chat_service: ChatService) -> None:
        self.chat_service = chat_service

    def run(self, cases: list[EvalCase], model: str | None = None, top_k: int = 5) -> EvalReport:
        results = [self._run_case(case, model=model, top_k=top_k) for case in cases]
        return EvalReport(results=results)

    def _run_case(self, case: EvalCase, model: str | None = None, top_k: int = 5) -> EvalResult:
        started = time.perf_counter()
        response = self.chat_service.chat(
            ChatRequest(
                query=case.query,
                mode="hybrid",
                top_k=top_k,
                model=model,
                temperature=0.0,
                max_tokens=500,
                timeout_sec=300,
                include_diagnostics=True,
            )
        )
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        checks = run_checks(case, response)
        sources = [source.to_dict() for source in response.sources]
        diagnostics = response.diagnostics or {}
        return EvalResult(
            case_id=case.case_id,
            category=case.category,
            priority=case.priority,
            query=case.query,
            expected_status=case.expected_status,
            actual_status=response.status,
            passed=all(check.passed for check in checks),
            checks=checks,
            answer_preview=(response.answer or "")[:500],
            sources=sources,
            diagnostics={
                "llm_called": diagnostics.get("llm_called"),
                "llm_model": diagnostics.get("llm_model"),
                "llm_finish_reason": diagnostics.get("llm_finish_reason"),
                "validation_errors": diagnostics.get("validation_errors"),
                "search_status": diagnostics.get("search_status"),
                "prompt_sources": diagnostics.get("prompt_sources"),
                "latency_ms": diagnostics.get("latency_ms", elapsed_ms),
            },
            latency_ms=elapsed_ms,
        )
