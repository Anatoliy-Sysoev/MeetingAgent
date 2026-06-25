"""Pure guard decision API — thin adapter over the existing guardrails pipeline.

Exposes the existing rule-based guard logic (segmenter → classifier →
aggregator → policy) as a stable, testable function that requires only a query
string.  No LLM, retrieval, network, or runtime data files are involved.

This module does not change guard behavior; it surfaces the same logic
that SearchService already calls via ProjectGuard.evaluate_v2().
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from asu_june_bot.guardrails.project_guard import ProjectGuard

# Valid decision values — mirrors GuardDecision / GuardAction.
VALID_DECISIONS: frozenset[str] = frozenset({"allow", "refuse", "clarify"})

# Module-level singleton so tests and callers share one pre-built rule set.
_DEFAULT_GUARD: ProjectGuard | None = None


def _get_default_guard() -> ProjectGuard:
    global _DEFAULT_GUARD  # noqa: PLW0603
    if _DEFAULT_GUARD is None:
        _DEFAULT_GUARD = ProjectGuard()
    return _DEFAULT_GUARD


@dataclass(slots=True, frozen=True)
class GuardDecisionResult:
    """Result of a pure guard evaluation.

    decision: one of "allow", "refuse", or "clarify".
    reason:   machine-readable reason string from the policy layer.
    matched_rule: aggregate scope label that triggered the decision.
    confidence: mean segment-level confidence from the aggregator.
    metadata: extra fields for diagnostics (scope breakdown flags).
    """

    decision: str
    reason: str | None = None
    matched_rule: str | None = None
    confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def evaluate_guard_decision(
    query: str,
    *,
    config: dict[str, Any] | None = None,  # reserved for future per-call overrides
) -> GuardDecisionResult:
    """Evaluate the guard decision for query using the existing rule-based pipeline.

    This is a pure function: no LLM, no retrieval, no network, no disk I/O.
    The ``config`` parameter is accepted for forward-compatibility but is not
    used by the current rule-based implementation.

    Returns a GuardDecisionResult with decision ∈ {"allow", "refuse", "clarify"}.
    """
    guard = _get_default_guard()
    policy_result = guard.evaluate_v2(query)

    aggregate = policy_result.aggregate
    return GuardDecisionResult(
        decision=policy_result.action.value,
        reason=policy_result.reason,
        matched_rule=aggregate.scope.value,
        confidence=round(float(aggregate.confidence), 4),
        metadata={
            "has_in_project": aggregate.has_in_project,
            "has_out_of_project": aggregate.has_out_of_project,
            "has_meta": aggregate.has_meta,
            "has_ambiguous": aggregate.has_ambiguous,
            "has_mixed_segment": aggregate.has_mixed_segment,
        },
    )
