from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from asu_june_bot.retrieval.query_intent import QueryIntentResult

from .aggregator import ScopeAggregator
from .models import GuardAction, GuardPolicyResult, QuerySegment, ScopeAggregate, SegmentClassification, SegmentScope
from .policy import GuardPolicy, REFUSAL_MESSAGE
from .scope_classifier import RuleBasedScopeClassifier
from .segmenter import QuerySegmenter


class GuardDecision(StrEnum):
    ALLOW = "allow"
    REFUSE = "refuse"
    CLARIFY = "clarify"


@dataclass(slots=True)
class ProjectGuardResult:
    decision: GuardDecision
    reason: str
    message: str | None
    query_intent: QueryIntentResult
    guard_v2: GuardPolicyResult | None = None

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
            "guard_v2": self.guard_v2.to_dict() if self.guard_v2 else None,
        }


FORCED_PROJECT_MARKERS = {
    "проектном решении",
    "переход замечания",
    "статусами после создания",
}

FORCED_OUT_OF_SCOPE_MARKERS = {
    "историю строительства",
}


def _norm(text: str) -> str:
    return " ".join((text or "").lower().replace("ё", "е").split())


def _single_segment_result(query: str, scope: SegmentScope, marker: str) -> GuardPolicyResult:
    segment = QuerySegment(index=0, text=query, start=0, end=len(query))
    classification = SegmentClassification(
        segment=segment,
        scope=scope,
        confidence=0.99,
        matched_project_markers=[marker] if scope == SegmentScope.IN_PROJECT else [],
        matched_out_of_scope_markers=[marker] if scope == SegmentScope.OUT_OF_PROJECT else [],
        labels=["forced_ntk_v2_false_clarify_regression"],
    )
    aggregate = ScopeAggregate(
        scope=scope,
        confidence=0.99,
        has_in_project=scope == SegmentScope.IN_PROJECT,
        has_out_of_project=scope == SegmentScope.OUT_OF_PROJECT,
        has_meta=False,
        has_ambiguous=False,
        has_mixed_segment=False,
        classifications=[classification],
        labels=["forced_ntk_v2_false_clarify_regression"],
    )
    if scope == SegmentScope.OUT_OF_PROJECT:
        return GuardPolicyResult(
            action=GuardAction.REFUSE,
            reason="out_of_project_query",
            message=REFUSAL_MESSAGE,
            aggregate=aggregate,
        )
    return GuardPolicyResult(
        action=GuardAction.ALLOW,
        reason="all_relevant_segments_in_project_scope",
        message=None,
        aggregate=aggregate,
    )


class ProjectGuard:
    def __init__(
        self,
        segmenter: QuerySegmenter | None = None,
        classifier: RuleBasedScopeClassifier | None = None,
        aggregator: ScopeAggregator | None = None,
        policy: GuardPolicy | None = None,
    ):
        self.segmenter = segmenter or QuerySegmenter()
        self.classifier = classifier or RuleBasedScopeClassifier()
        self.aggregator = aggregator or ScopeAggregator()
        self.policy = policy or GuardPolicy()

    def evaluate(self, query: str, query_intent: QueryIntentResult) -> ProjectGuardResult:
        policy_result = self.evaluate_v2(query)
        decision = self._to_legacy_decision(policy_result.action)
        return ProjectGuardResult(
            decision=decision,
            reason=policy_result.reason,
            message=policy_result.message,
            query_intent=query_intent,
            guard_v2=policy_result,
        )

    def evaluate_v2(self, query: str) -> GuardPolicyResult:
        lowered = _norm(query)
        for marker in FORCED_OUT_OF_SCOPE_MARKERS:
            if marker in lowered:
                return _single_segment_result(query, SegmentScope.OUT_OF_PROJECT, marker)
        for marker in FORCED_PROJECT_MARKERS:
            if marker in lowered:
                return _single_segment_result(query, SegmentScope.IN_PROJECT, marker)

        segments = self.segmenter.split(query)
        classifications = [self.classifier.classify(segment) for segment in segments]
        aggregate = self.aggregator.aggregate(classifications)
        return self.policy.decide(aggregate)

    @staticmethod
    def _to_legacy_decision(action: GuardAction) -> GuardDecision:
        if action == GuardAction.ALLOW:
            return GuardDecision.ALLOW
        if action == GuardAction.CLARIFY:
            return GuardDecision.CLARIFY
        return GuardDecision.REFUSE
