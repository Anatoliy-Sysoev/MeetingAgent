from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from asu_june_bot.retrieval.query_intent import QueryIntent, QueryIntentResult


class GuardDecision(StrEnum):
    ALLOW = "allow"
    REFUSE = "refuse"


DEFAULT_REFUSAL_MESSAGE = "Я отвечаю только по материалам проекта ЦП УПКС. Вопрос не относится к проектной базе знаний."
DEFAULT_MIXED_SCOPE_MESSAGE = (
    "Запрос содержит проектную и внепроектную части. "
    "Я отвечаю только по материалам проекта ЦП УПКС. "
    "Уберите внепроектную часть запроса и повторите вопрос по документации проекта."
)


@dataclass(slots=True)
class ProjectGuardResult:
    decision: GuardDecision
    reason: str
    message: str | None
    query_intent: QueryIntentResult

    @property
    def allowed(self) -> bool:
        return self.decision == GuardDecision.ALLOW

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "allowed": self.allowed,
            "reason": self.reason,
            "message": self.message,
            "query_intent": self.query_intent.to_dict(),
        }


class ProjectGuard:
    def __init__(
        self,
        refusal_message: str = DEFAULT_REFUSAL_MESSAGE,
        mixed_scope_message: str = DEFAULT_MIXED_SCOPE_MESSAGE,
    ):
        self.refusal_message = refusal_message
        self.mixed_scope_message = mixed_scope_message

    def evaluate(self, query: str, query_intent: QueryIntentResult) -> ProjectGuardResult:
        if query_intent.intent == QueryIntent.OUT_OF_SCOPE_CANDIDATE and not query_intent.is_project_related:
            return ProjectGuardResult(
                decision=GuardDecision.REFUSE,
                reason="out_of_scope_candidate_without_project_signal",
                message=self.refusal_message,
                query_intent=query_intent,
            )

        if query_intent.matched_out_of_scope_markers and query_intent.matched_project_markers:
            return ProjectGuardResult(
                decision=GuardDecision.REFUSE,
                reason="mixed_scope_query_contains_out_of_scope_marker",
                message=self.mixed_scope_message,
                query_intent=query_intent,
            )

        if query_intent.matched_out_of_scope_markers and not query_intent.matched_project_markers:
            return ProjectGuardResult(
                decision=GuardDecision.REFUSE,
                reason="out_of_scope_marker_without_project_marker",
                message=self.refusal_message,
                query_intent=query_intent,
            )

        return ProjectGuardResult(
            decision=GuardDecision.ALLOW,
            reason="project_signal_detected",
            message=None,
            query_intent=query_intent,
        )
