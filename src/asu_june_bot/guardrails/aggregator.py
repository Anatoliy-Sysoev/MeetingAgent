from __future__ import annotations

from statistics import mean

from .models import ScopeAggregate, SegmentClassification, SegmentScope


class ScopeAggregator:
    def aggregate(self, classifications: list[SegmentClassification]) -> ScopeAggregate:
        has_in = any(item.scope == SegmentScope.IN_PROJECT for item in classifications)
        has_out = any(item.scope == SegmentScope.OUT_OF_PROJECT for item in classifications)
        has_meta = any(item.scope == SegmentScope.META for item in classifications)
        has_ambiguous = any(item.scope == SegmentScope.AMBIGUOUS for item in classifications)
        has_mixed_segment = any(item.scope == SegmentScope.MIXED for item in classifications)
        labels: list[str] = []

        if has_in:
            labels.append("aggregate_has_in_project")
        if has_out:
            labels.append("aggregate_has_out_of_project")
        if has_meta:
            labels.append("aggregate_has_meta")
        if has_ambiguous:
            labels.append("aggregate_has_ambiguous")
        if has_mixed_segment:
            labels.append("aggregate_has_mixed_segment")

        if not classifications:
            return ScopeAggregate(
                scope=SegmentScope.AMBIGUOUS,
                confidence=0.0,
                has_in_project=False,
                has_out_of_project=False,
                has_meta=False,
                has_ambiguous=True,
                has_mixed_segment=False,
                classifications=[],
                labels=["empty_query"],
            )

        if has_mixed_segment or (has_in and has_out):
            scope = SegmentScope.MIXED
            labels.append("aggregate_mixed_scope")
        elif has_out and not has_in:
            scope = SegmentScope.OUT_OF_PROJECT
            labels.append("aggregate_out_of_project")
        elif has_in and not has_out:
            scope = SegmentScope.IN_PROJECT
            labels.append("aggregate_in_project")
        elif has_meta and not has_ambiguous:
            scope = SegmentScope.META
            labels.append("aggregate_meta_only")
        else:
            scope = SegmentScope.AMBIGUOUS
            labels.append("aggregate_ambiguous")

        confidence = mean(float(item.confidence) for item in classifications)
        if scope == SegmentScope.MIXED:
            confidence = max(confidence, 0.92)
        if scope == SegmentScope.OUT_OF_PROJECT:
            confidence = max(confidence, 0.9)

        return ScopeAggregate(
            scope=scope,
            confidence=confidence,
            has_in_project=has_in,
            has_out_of_project=has_out,
            has_meta=has_meta,
            has_ambiguous=has_ambiguous,
            has_mixed_segment=has_mixed_segment,
            classifications=classifications,
            labels=labels,
        )
