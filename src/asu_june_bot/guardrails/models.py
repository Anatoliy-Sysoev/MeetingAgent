from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class SegmentScope(StrEnum):
    IN_PROJECT = "in_project"
    OUT_OF_PROJECT = "out_of_project"
    META = "meta"
    AMBIGUOUS = "ambiguous"
    MIXED = "mixed"


class GuardAction(StrEnum):
    ALLOW = "allow"
    REFUSE = "refuse"
    CLARIFY = "clarify"


@dataclass(slots=True)
class QuerySegment:
    index: int
    text: str
    start: int | None = None
    end: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "text": self.text,
            "start": self.start,
            "end": self.end,
        }


@dataclass(slots=True)
class SegmentClassification:
    segment: QuerySegment
    scope: SegmentScope
    confidence: float
    matched_project_markers: list[str] = field(default_factory=list)
    matched_out_of_scope_markers: list[str] = field(default_factory=list)
    matched_meta_markers: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "segment": self.segment.to_dict(),
            "scope": self.scope.value,
            "confidence": round(float(self.confidence), 4),
            "matched_project_markers": self.matched_project_markers,
            "matched_out_of_scope_markers": self.matched_out_of_scope_markers,
            "matched_meta_markers": self.matched_meta_markers,
            "labels": self.labels,
        }


@dataclass(slots=True)
class ScopeAggregate:
    scope: SegmentScope
    confidence: float
    has_in_project: bool
    has_out_of_project: bool
    has_meta: bool
    has_ambiguous: bool
    has_mixed_segment: bool
    classifications: list[SegmentClassification]
    labels: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope.value,
            "confidence": round(float(self.confidence), 4),
            "has_in_project": self.has_in_project,
            "has_out_of_project": self.has_out_of_project,
            "has_meta": self.has_meta,
            "has_ambiguous": self.has_ambiguous,
            "has_mixed_segment": self.has_mixed_segment,
            "labels": self.labels,
            "segments": [item.to_dict() for item in self.classifications],
        }


@dataclass(slots=True)
class GuardPolicyResult:
    action: GuardAction
    reason: str
    message: str | None
    aggregate: ScopeAggregate

    @property
    def allowed(self) -> bool:
        return self.action == GuardAction.ALLOW

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "allowed": self.allowed,
            "reason": self.reason,
            "message": self.message,
            "aggregate": self.aggregate.to_dict(),
        }
