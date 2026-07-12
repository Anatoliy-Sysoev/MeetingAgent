from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from .models import SearchResult
from .query_intent import QueryIntentResult
from .ranking_policies import (
    DEFAULT_POLICIES,
    RankingContext,
    RankingPolicy,
    RankingStage,
    ScoreAdjustment,
    adjustment_multiplier,
    adjustment_trace,
    evaluate_policies,
)
from .ranking_profile import RankingProfile, default_ranking_profile


@dataclass(slots=True)
class RerankResult:
    results: list[SearchResult]
    excluded: list[SearchResult] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)


def _path(result: SearchResult) -> str:
    return str(result.metadata.get("relative_path") or "")


def _dedup_key(result: SearchResult) -> str:
    path = _path(result).lower()
    chunk_index = result.metadata.get("chunk_index")
    return str(result.metadata.get("chunk_id") or f"{path}#{chunk_index}")


class PostReranker:
    def __init__(
        self,
        ranking_profile: RankingProfile | None = None,
        policies: tuple[RankingPolicy, ...] = DEFAULT_POLICIES,
    ) -> None:
        self.ranking_profile = ranking_profile or default_ranking_profile()
        self.policies = policies

    def rerank(
        self,
        query: str,
        intent: QueryIntentResult,
        results: list[SearchResult],
        top_k: int | None = None,
    ) -> RerankResult:
        adjusted: list[SearchResult] = []
        excluded: list[SearchResult] = []
        seen: set[str] = set()

        for result in results:
            key = _dedup_key(result)
            if key in seen:
                excluded.append(
                    self._with_exclusion(result, "dedup", "excluded:duplicate_chunk", 0.0)
                )
                continue
            seen.add(key)

            context = RankingContext(
                stage=RankingStage.POST_RERANK,
                query=query,
                original_query=query,
                text=result.text,
                metadata=result.metadata,
                document_type=str(result.metadata.get("document_type") or ""),
                matched_by=tuple(result.matched_by),
                profile=self.ranking_profile,
                intent=intent,
            )
            adjustments = evaluate_policies(context, self.policies)
            adjusted.append(self._with_adjustments(result, adjustments))

        adjusted.sort(key=lambda item: item.score, reverse=True)
        if top_k is not None and top_k > 0:
            overflow = adjusted[top_k:]
            adjusted = adjusted[:top_k]
            excluded.extend(
                self._with_exclusion(
                    item,
                    "top_k",
                    "excluded:overflow_after_rerank",
                    1.0,
                )
                for item in overflow
            )

        return RerankResult(
            results=self._renumber(adjusted),
            excluded=excluded,
            diagnostics={
                "reranker": "PostReranker",
                "input_count": len(results),
                "output_count": len(adjusted),
                "excluded_count": len(excluded),
                "intent": intent.intent.value,
            },
        )

    def _with_adjustments(
        self,
        result: SearchResult,
        adjustments: list[ScoreAdjustment],
    ) -> SearchResult:
        multiplier = adjustment_multiplier(adjustments)
        adjusted_score = float(result.score) * multiplier
        diagnostics = dict(result.diagnostics)
        diagnostics["rerank_labels"] = list(diagnostics.get("rerank_labels") or []) + [
            item.label for item in adjustments
        ]
        diagnostics["rerank_multiplier"] = round(multiplier, 6)
        diagnostics["score_before_post_rerank"] = round(float(result.score), 6)
        diagnostics["ranking_profile_version"] = self.ranking_profile.version
        diagnostics["ranking_trace"] = list(
            diagnostics.get("ranking_trace") or []
        ) + adjustment_trace(
            RankingStage.POST_RERANK,
            float(result.score),
            adjustments,
        )
        return replace(result, score=adjusted_score, diagnostics=diagnostics)

    @staticmethod
    def _with_exclusion(
        result: SearchResult,
        policy: str,
        label: str,
        multiplier: float,
    ) -> SearchResult:
        diagnostics = dict(result.diagnostics)
        diagnostics["rerank_labels"] = list(diagnostics.get("rerank_labels") or []) + [label]
        diagnostics["score_before_post_rerank"] = round(float(result.score), 6)
        diagnostics["ranking_trace"] = list(diagnostics.get("ranking_trace") or []) + [
            {
                "stage": RankingStage.POST_RERANK.value,
                "policy": policy,
                "label": label,
                "multiplier": multiplier,
                "score_before": round(float(result.score), 6),
                "score_after": round(float(result.score) * multiplier, 6),
            }
        ]
        return replace(result, score=float(result.score) * multiplier, diagnostics=diagnostics)

    @staticmethod
    def _renumber(results: list[SearchResult]) -> list[SearchResult]:
        return [
            replace(result, source_id=f"SRC-{idx:03d}")
            for idx, result in enumerate(results, start=1)
        ]
