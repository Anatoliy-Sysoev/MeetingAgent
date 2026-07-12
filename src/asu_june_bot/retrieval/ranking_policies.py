from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import prod
from typing import Any, Protocol

from .query_intent import QueryIntent, QueryIntentResult
from .ranking_profile import RankingProfile
from .ranking_signals import RankingSignals


class RankingStage(StrEnum):
    BM25 = "bm25"
    POST_RERANK = "post_rerank"


@dataclass(frozen=True, slots=True)
class RankingContext:
    stage: RankingStage
    query: str
    original_query: str
    text: str
    metadata: dict[str, Any]
    document_type: str
    matched_by: tuple[str, ...]
    profile: RankingProfile
    intent: QueryIntentResult | None = None

    @property
    def query_lower(self) -> str:
        return RankingSignals.normalize(self.query)

    @property
    def original_query_lower(self) -> str:
        return RankingSignals.normalize(self.original_query)

    @property
    def text_lower(self) -> str:
        return RankingSignals.normalize(self.text)

    @property
    def signals(self) -> RankingSignals:
        return RankingSignals(self.profile)


@dataclass(frozen=True, slots=True)
class ScoreAdjustment:
    policy: str
    label: str
    multiplier: float

    def __post_init__(self) -> None:
        if not self.policy or not self.label or not 0.0 < self.multiplier <= 20.0:
            raise ValueError("invalid ranking adjustment")


class RankingPolicy(Protocol):
    name: str

    def evaluate(self, context: RankingContext) -> list[ScoreAdjustment]: ...


def _adjust(policy: str, label: str, multiplier: float) -> ScoreAdjustment:
    return ScoreAdjustment(policy=policy, label=label, multiplier=multiplier)


def adjustment_multiplier(adjustments: list[ScoreAdjustment]) -> float:
    return prod(item.multiplier for item in adjustments) if adjustments else 1.0


def adjustment_trace(
    stage: RankingStage,
    base_score: float,
    adjustments: list[ScoreAdjustment],
) -> list[dict[str, Any]]:
    score = float(base_score)
    trace: list[dict[str, Any]] = []
    for item in adjustments:
        adjusted = score * item.multiplier
        trace.append(
            {
                "stage": stage.value,
                "policy": item.policy,
                "label": item.label,
                "multiplier": round(item.multiplier, 6),
                "score_before": round(score, 6),
                "score_after": round(adjusted, 6),
            }
        )
        score = adjusted
    return trace


class MatchSignalPolicy:
    name = "match_signal"

    def evaluate(self, context: RankingContext) -> list[ScoreAdjustment]:
        if context.stage != RankingStage.POST_RERANK:
            return []
        matched = set(context.matched_by)
        if {"bm25", "vector"} <= matched:
            return [_adjust(self.name, "boost:matched_by_bm25_and_vector", 1.12)]
        if "vector" not in matched or "bm25" in matched:
            return []
        exact_intents = {QueryIntent.DOCUMENT_OVERVIEW, QueryIntent.REQUIREMENT_LOOKUP}
        if context.intent and context.intent.intent in exact_intents:
            return [_adjust(self.name, "penalty:vector_only_for_exact_or_overview", 0.42)]
        return [_adjust(self.name, "penalty:vector_only", 0.82)]


class DocumentOverviewPolicy:
    name = "document_overview"

    def evaluate(self, context: RankingContext) -> list[ScoreAdjustment]:
        if (
            context.stage != RankingStage.POST_RERANK
            or context.intent is None
            or context.intent.intent != QueryIntent.DOCUMENT_OVERVIEW
        ):
            return []
        signals = context.signals
        items: list[ScoreAdjustment] = []
        if context.document_type == "Паспорт ИС" and "паспорт" in context.query_lower:
            items.append(_adjust(self.name, "boost:document_overview_passport", 1.55))
        if signals.is_software_or_support_table(context.text_lower):
            items.append(_adjust(self.name, "penalty:software_or_support_table_for_overview", 0.08))
        if signals.is_glossary_or_front_matter(context.text_lower):
            items.append(_adjust(self.name, "penalty:front_matter_or_glossary_for_overview", 0.28))
        if signals.has("overview_scope_chunk", context.text_lower):
            items.append(_adjust(self.name, "boost:overview_scope_chunk", 1.8))
        return items


class PassportPolicy:
    name = "passport"

    def evaluate(self, context: RankingContext) -> list[ScoreAdjustment]:
        signals = context.signals
        if not signals.has("passport_route", context.query_lower):
            return []
        if context.stage == RankingStage.BM25:
            return self._bm25(context, signals)
        return self._post(context, signals)

    def _post(
        self,
        context: RankingContext,
        signals: RankingSignals,
    ) -> list[ScoreAdjustment]:
        if context.document_type != "Паспорт ИС":
            if signals.document_in("passport_other", context.document_type):
                return [_adjust(self.name, "penalty:passport_other_doc_type", 0.42)]
            return []

        items = [_adjust(self.name, "boost:passport_route", 1.35)]
        if signals.is_passport_related_query(context.query_lower):
            if signals.is_passport_related_chunk(context.text_lower):
                items.append(_adjust(self.name, "boost:passport_related_documents", 4.8))
            elif signals.is_software_or_support_table(context.text_lower):
                items.append(
                    _adjust(self.name, "penalty:passport_support_noise_for_related_docs", 0.22)
                )
        if signals.has("passport_appendices_query", context.query_lower):
            if signals.is_passport_appendices_chunk(context.text_lower):
                items.append(_adjust(self.name, "boost:passport_appendices", 5.4))
            elif signals.is_software_or_support_table(context.text_lower):
                items.append(
                    _adjust(self.name, "penalty:passport_support_noise_for_appendices", 0.08)
                )
        if signals.has("passport_purpose_query", context.query_lower):
            purpose_match = signals.is_passport_purpose_chunk(context.text_lower) or signals.has(
                "passport_post_purpose_scope", context.text_lower
            )
            if purpose_match:
                items.append(_adjust(self.name, "boost:passport_system_purpose", 4.0))
                if signals.has("passport_exact_purpose_chunk", context.text_lower):
                    items.append(_adjust(self.name, "boost:passport_exact_system_purpose", 5.0))
            elif signals.is_software_or_support_table(context.text_lower):
                items.append(_adjust(self.name, "penalty:passport_support_noise_for_purpose", 0.22))
        return items

    def _bm25(
        self,
        context: RankingContext,
        signals: RankingSignals,
    ) -> list[ScoreAdjustment]:
        is_passport = context.document_type == "Паспорт ИС"
        items = [_adjust(self.name, "intent:passport", 2.25 if is_passport else 0.55)]
        if signals.document_in("passport_other", context.document_type):
            items.append(_adjust(self.name, "penalty:passport_other_doc_type", 0.42))
        if not is_passport:
            return items

        if signals.is_passport_related_query(context.query_lower):
            if signals.is_passport_related_chunk(context.text_lower):
                items.append(_adjust(self.name, "intent:passport_related_documents", 5.6))
            elif signals.has("passport_support_noise", context.text_lower):
                items.append(
                    _adjust(self.name, "penalty:passport_support_noise_for_related_docs", 0.18)
                )
        if signals.has("passport_appendices_query", context.query_lower):
            if signals.is_passport_appendices_chunk(context.text_lower):
                items.append(_adjust(self.name, "intent:passport_appendices", 6.4))
            elif signals.has(
                "passport_support_noise", context.text_lower
            ) or signals.is_passport_software_table(context.text_lower):
                items.append(
                    _adjust(self.name, "penalty:passport_support_noise_for_appendices", 0.08)
                )
        if signals.has("passport_purpose_query", context.query_lower):
            if signals.is_passport_purpose_chunk(
                context.text_lower
            ) or signals.is_passport_scope_chunk(context.text_lower):
                items.append(_adjust(self.name, "intent:passport_system_purpose", 4.8))
                if signals.has("passport_exact_purpose_chunk", context.text_lower):
                    items.append(_adjust(self.name, "intent:passport_exact_system_purpose", 2.4))
            elif signals.has(
                "passport_support_noise", context.text_lower
            ) or signals.is_passport_software_table(context.text_lower):
                items.append(_adjust(self.name, "penalty:passport_support_noise_for_purpose", 0.22))
        if signals.is_passport_overview_query(context.query_lower):
            if signals.is_passport_scope_chunk(context.text_lower):
                items.append(_adjust(self.name, "intent:passport_overview_scope", 2.6))
            if signals.is_passport_software_table(context.text_lower):
                items.append(
                    _adjust(self.name, "penalty:passport_software_table_for_overview", 0.18)
                )
            if (
                "история изменений" in context.text_lower[:1000]
                or "связанные документы" in context.text_lower[:1200]
            ):
                items.append(_adjust(self.name, "penalty:passport_front_matter_for_overview", 0.35))
        return items


class FttRoutePolicy:
    name = "ftt_route"

    def evaluate(self, context: RankingContext) -> list[ScoreAdjustment]:
        if context.stage != RankingStage.BM25 or not context.signals.has(
            "ftt_route", context.query_lower
        ):
            return []
        if context.document_type == "ФТТ":
            return [_adjust(self.name, "intent:ftt", 1.85)]
        if context.document_type == "ПМИ":
            return [_adjust(self.name, "intent:ftt_penalty_pmi", 0.68)]
        if context.document_type == "ПР":
            return [_adjust(self.name, "intent:ftt_penalty_pr", 0.82)]
        return []


class IntegrationPolicy:
    name = "integration"

    def evaluate(self, context: RankingContext) -> list[ScoreAdjustment]:
        signals = context.signals
        items: list[ScoreAdjustment] = []
        if context.stage == RankingStage.POST_RERANK:
            if context.intent is None or context.intent.intent != QueryIntent.INTEGRATION_OVERVIEW:
                return []
            if signals.document_in("integration_primary", context.document_type):
                items.append(_adjust(self.name, "boost:integration_primary_doc_type", 1.35))
            if context.document_type == "ПР" and set(context.matched_by) == {"vector"}:
                items.append(_adjust(self.name, "penalty:integration_pr_vector_only", 0.72))
            return items

        if not signals.has("integration_query", context.query_lower):
            return []
        if signals.document_in("integration_primary", context.document_type):
            items.append(_adjust(self.name, "intent:integrations", 1.25))
        elif context.document_type == "Wiki":
            items.append(_adjust(self.name, "intent:integrations_wiki_penalty", 0.72))
        return items


class SoiPolicy:
    name = "soi"

    def evaluate(self, context: RankingContext) -> list[ScoreAdjustment]:
        signals = context.signals
        items: list[ScoreAdjustment] = []
        ad_route = signals.has("soi_ad_route", context.query_lower)
        if ad_route:
            if context.document_type == "СоИ AD":
                items.append(
                    _adjust(
                        self.name,
                        "boost:soi_ad_route"
                        if context.stage == RankingStage.POST_RERANK
                        else "intent:soi_ad",
                        3.0 if context.stage == RankingStage.POST_RERANK else 3.2,
                    )
                )
                if signals.is_ad_role_mapping_chunk(context.text_lower):
                    items.append(
                        _adjust(
                            self.name,
                            "boost:soi_ad_role_mapping_chunk"
                            if context.stage == RankingStage.POST_RERANK
                            else "intent:soi_ad_role_mapping",
                            1.9 if context.stage == RankingStage.POST_RERANK else 1.85,
                        )
                    )
            elif signals.is_ad_role_mapping_chunk(context.text_lower):
                items.append(
                    _adjust(
                        self.name,
                        "boost:soi_ad_role_mapping_supporting_chunk"
                        if context.stage == RankingStage.POST_RERANK
                        else "intent:soi_ad_role_mapping_supporting",
                        2.2 if context.stage == RankingStage.POST_RERANK else 2.1,
                    )
                )
            elif signals.document_in("soi_ad_generic", context.document_type):
                items.append(
                    _adjust(
                        self.name,
                        "penalty:soi_ad_generic_doc"
                        if context.stage == RankingStage.POST_RERANK
                        else "intent:soi_ad_penalty_generic_docs",
                        0.68,
                    )
                )

        if signals.has("soi_nsi_route", context.query_lower):
            if context.document_type == "СоИ Справочники":
                items.append(
                    _adjust(
                        self.name,
                        "boost:soi_nsi_mdr_route"
                        if context.stage == RankingStage.POST_RERANK
                        else "intent:soi_nsi_mdr",
                        2.1 if context.stage == RankingStage.POST_RERANK else 2.35,
                    )
                )
            elif signals.document_in("soi_nsi_generic", context.document_type):
                items.append(
                    _adjust(
                        self.name,
                        "penalty:soi_nsi_mdr_generic_doc"
                        if context.stage == RankingStage.POST_RERANK
                        else "intent:soi_nsi_mdr_penalty_generic_docs",
                        0.72,
                    )
                )
        return items


class ProjectDecisionPolicy:
    name = "project_decision"

    def evaluate(self, context: RankingContext) -> list[ScoreAdjustment]:
        signals = context.signals
        if signals.has("soi_ad_route", context.query_lower) or not signals.has_pr_route(
            context.query_lower
        ):
            return []
        is_post = context.stage == RankingStage.POST_RERANK
        if context.document_type != "ПР":
            if signals.document_in("pr_generic", context.document_type):
                return [
                    _adjust(
                        self.name,
                        "penalty:pr_construction_generic_doc"
                        if is_post
                        else "intent:pr_construction_control_penalty_generic_docs",
                        0.72,
                    )
                ]
            return []

        items = [
            _adjust(
                self.name,
                "boost:pr_construction_control_route"
                if is_post
                else "intent:pr_construction_control",
                1.9 if is_post else 2.0,
            )
        ]
        query = context.original_query_lower
        status_route = signals.has("pr_status_route", query)
        annulment_route = "аннулир" in query
        roles_route = signals.has("pr_roles_route", query)
        rights_route = signals.has("pr_rights_route", query)
        module_route = signals.has("pr_module_route", query)
        if module_route and not signals.is_pr_construction_control_document(context.metadata):
            items.append(
                _adjust(self.name, "penalty:pr_other_module_for_construction_control", 0.28)
            )
        if status_route:
            if signals.is_pr_status_values_chunk(context.text_lower):
                items.append(
                    _adjust(
                        self.name,
                        "boost:pr_notice_status_values"
                        if is_post
                        else "intent:pr_notice_status_values",
                        4.8 if is_post else 5.2,
                    )
                )
            elif signals.is_pr_status_transition_chunk(context.text_lower):
                items.append(
                    _adjust(
                        self.name,
                        "boost:pr_notice_status_transition"
                        if is_post
                        else "intent:pr_notice_status_transition",
                        2.0 if is_post else 2.2,
                    )
                )
            elif signals.is_pr_generic_process_chunk(context.text_lower):
                items.append(_adjust(self.name, "penalty:pr_notice_status_generic_process", 0.42))
        if annulment_route:
            if signals.is_pr_annulment_chunk(context.text_lower):
                items.append(
                    _adjust(
                        self.name,
                        "boost:pr_notice_annulment_process"
                        if is_post
                        else "intent:pr_notice_annulment_process",
                        5.0 if is_post else 5.4,
                    )
                )
            elif signals.is_pr_status_values_chunk(context.text_lower):
                items.append(
                    _adjust(
                        self.name,
                        "boost:pr_notice_annulment_status_support"
                        if is_post
                        else "intent:pr_notice_annulment_status_support",
                        1.6 if is_post else 1.7,
                    )
                )
            elif signals.is_pr_generic_process_chunk(context.text_lower):
                items.append(
                    _adjust(self.name, "penalty:pr_notice_annulment_generic_process", 0.36)
                )
        if roles_route:
            if signals.is_pr_role_composition_chunk(context.text_lower):
                items.append(
                    _adjust(
                        self.name,
                        "boost:pr_roles_composition" if is_post else "intent:pr_roles_composition",
                        4.6 if is_post else 5.0,
                    )
                )
            elif signals.is_pr_role_access_chunk(context.text_lower):
                items.append(
                    _adjust(
                        self.name,
                        "boost:pr_roles_access_support"
                        if is_post
                        else "intent:pr_roles_access_support",
                        2.1 if is_post else 2.2,
                    )
                )
            elif signals.is_pr_generic_process_chunk(context.text_lower):
                items.append(_adjust(self.name, "penalty:pr_roles_generic_process", 0.34))
        if rights_route:
            if signals.is_pr_role_access_chunk(context.text_lower):
                items.append(
                    _adjust(
                        self.name,
                        "boost:pr_rights_access_matrix"
                        if is_post
                        else "intent:pr_rights_access_matrix",
                        5.0 if is_post else 5.4,
                    )
                )
            elif signals.is_pr_role_composition_chunk(context.text_lower):
                items.append(
                    _adjust(
                        self.name,
                        "boost:pr_rights_role_composition_support"
                        if is_post
                        else "intent:pr_rights_role_composition_support",
                        2.2 if is_post else 2.4,
                    )
                )
            elif signals.is_pr_generic_process_chunk(context.text_lower):
                items.append(_adjust(self.name, "penalty:pr_rights_generic_process", 0.32))
        return items


class PerformancePolicy:
    name = "performance_export"

    def evaluate(self, context: RankingContext) -> list[ScoreAdjustment]:
        if context.document_type != "ФТТ" or not context.signals.has(
            "performance_export_route", context.query_lower
        ):
            return []
        return [
            _adjust(
                self.name,
                "boost:ftt_performance_or_export_route"
                if context.stage == RankingStage.POST_RERANK
                else "intent:ftt_performance_or_export",
                1.75 if context.stage == RankingStage.POST_RERANK else 1.85,
            )
        ]


class CtaPolicy:
    name = "cta"

    def evaluate(self, context: RankingContext) -> list[ScoreAdjustment]:
        signals = context.signals
        query = context.query_lower
        recovery = signals.has("cta_recovery_route", query)
        explicit = "цта" in query or "целевая техническая архитектура" in query
        postgres = signals.has("cta_postgresql_route", query)
        minio = signals.has("cta_minio_route", query)
        kubernetes = signals.has("cta_kubernetes_route", query)
        logging = signals.has("cta_logging_route", query)
        infrastructure = postgres or minio or kubernetes or logging
        is_post = context.stage == RankingStage.POST_RERANK
        items: list[ScoreAdjustment] = []

        if recovery:
            if context.document_type == "ЦТА":
                items.append(
                    _adjust(
                        self.name,
                        "boost:cta_recovery_rto_rpo_route"
                        if is_post
                        else "intent:cta_recovery_rto_rpo",
                        2.2 if is_post else 2.4,
                    )
                )
                if signals.is_cta_recovery_chunk(context.text_lower):
                    items.append(
                        _adjust(
                            self.name,
                            "boost:cta_recovery_chunk" if is_post else "intent:cta_recovery_chunk",
                            1.95 if is_post else 2.2,
                        )
                    )
                elif signals.is_logging_or_port_chunk(context.text_lower):
                    items.append(
                        _adjust(
                            self.name,
                            "penalty:cta_recovery_logging_or_port_chunk"
                            if is_post
                            else "intent:cta_recovery_penalty_logging_or_port",
                            0.26 if is_post else 0.28,
                        )
                    )
            elif signals.document_in("cta_non_primary", context.document_type):
                items.append(
                    _adjust(
                        self.name,
                        "penalty:cta_recovery_non_cta_doc"
                        if is_post
                        else "intent:cta_recovery_penalty_non_cta",
                        0.62,
                    )
                )
            return items

        if not infrastructure:
            return []
        if context.document_type == "ЦТА":
            items.append(
                _adjust(
                    self.name,
                    "boost:cta_infrastructure_route" if is_post else "intent:cta_infrastructure",
                    1.75 if is_post else 1.85,
                )
            )
            if postgres and signals.is_cta_postgresql_chunk(context.text_lower):
                items.append(
                    _adjust(
                        self.name,
                        "boost:cta_postgresql_chunk" if is_post else "intent:cta_postgresql_chunk",
                        2.8 if is_post else 3.0,
                    )
                )
            if minio and signals.is_cta_minio_storage_chunk(context.text_lower):
                items.append(
                    _adjust(
                        self.name,
                        "boost:cta_minio_storage_chunk"
                        if is_post
                        else "intent:cta_minio_storage_chunk",
                        2.6 if is_post else 2.8,
                    )
                )
            if kubernetes and signals.is_cta_kubernetes_chunk(context.text_lower):
                items.append(
                    _adjust(
                        self.name,
                        "boost:cta_kubernetes_chunk" if is_post else "intent:cta_kubernetes_chunk",
                        2.8 if is_post else 3.0,
                    )
                )
            if not logging and signals.is_cta_logging_noise_chunk(context.text_lower):
                items.append(_adjust(self.name, "penalty:cta_infrastructure_logging_noise", 0.16))
        elif explicit:
            items.append(
                _adjust(
                    self.name,
                    "penalty:cta_infrastructure_non_cta_doc"
                    if is_post
                    else "intent:cta_infrastructure_penalty_non_cta",
                    0.25,
                )
            )
        return items


class NsiPolicy:
    name = "nsi"

    def evaluate(self, context: RankingContext) -> list[ScoreAdjustment]:
        signals = context.signals
        regulation = signals.has("nsi_regulation_route", context.query_lower)
        reference = signals.has("nsi_reference_route", context.original_query_lower) or signals.has(
            "nsi_reference_route", context.query_lower
        )
        is_post = context.stage == RankingStage.POST_RERANK
        items: list[ScoreAdjustment] = []
        if regulation:
            if context.document_type == "Методика/Регламент НСИ":
                items.append(
                    _adjust(
                        self.name,
                        "boost:nsi_regulation_route"
                        if is_post
                        else "intent:nsi_regulation_primary",
                        3.0 if is_post else 3.2,
                    )
                )
                if signals.is_nsi_regulation_chunk(context.text_lower):
                    items.append(
                        _adjust(
                            self.name,
                            "boost:nsi_regulation_chunk"
                            if is_post
                            else "intent:nsi_regulation_chunk",
                            1.65 if is_post else 1.75,
                        )
                    )
            elif context.document_type == "Реестр НСИ":
                items.append(
                    _adjust(
                        self.name,
                        "boost:nsi_regulation_register_support"
                        if is_post
                        else "intent:nsi_regulation_register_support",
                        1.35 if is_post else 1.45,
                    )
                )
            elif context.document_type in {"Справочник НСИ", "СоИ Справочники"}:
                items.append(
                    _adjust(
                        self.name,
                        "boost:nsi_regulation_supporting"
                        if is_post
                        else "intent:nsi_regulation_supporting",
                        1.05,
                    )
                )
            elif signals.document_in("nsi_project_docs", context.document_type):
                items.append(
                    _adjust(
                        self.name,
                        "penalty:nsi_regulation_project_docs"
                        if is_post
                        else "intent:nsi_regulation_penalty_project_docs",
                        0.38,
                    )
                )
            return items

        if not reference:
            return []
        if context.document_type == "Реестр НСИ":
            items.append(
                _adjust(
                    self.name,
                    "boost:nsi_reference_register" if is_post else "intent:nsi_reference_register",
                    3.0 if is_post else 3.2,
                )
            )
            if signals.is_nsi_reference_chunk(context.text_lower):
                items.append(
                    _adjust(
                        self.name,
                        "boost:nsi_reference_chunk" if is_post else "intent:nsi_reference_chunk",
                        1.9 if is_post else 2.0,
                    )
                )
        elif context.document_type == "СоИ Справочники":
            items.append(
                _adjust(
                    self.name,
                    "boost:nsi_reference_soi_spravochniki"
                    if is_post
                    else "intent:nsi_reference_soi_spravochniki",
                    2.5 if is_post else 2.6,
                )
            )
            if signals.is_nsi_reference_chunk(context.text_lower):
                items.append(
                    _adjust(
                        self.name,
                        "boost:nsi_reference_chunk" if is_post else "intent:nsi_reference_chunk",
                        2.2 if is_post else 2.4,
                    )
                )
        elif context.document_type == "Справочник НСИ":
            items.append(
                _adjust(
                    self.name,
                    "boost:nsi_reference_dictionary"
                    if is_post
                    else "intent:nsi_reference_dictionary",
                    2.2 if is_post else 2.3,
                )
            )
            if signals.is_nsi_reference_chunk(context.text_lower):
                items.append(
                    _adjust(
                        self.name,
                        "boost:nsi_reference_chunk" if is_post else "intent:nsi_reference_chunk",
                        1.7 if is_post else 1.8,
                    )
                )
        elif context.document_type == "Методика/Регламент НСИ":
            items.append(
                _adjust(
                    self.name,
                    "boost:nsi_reference_regulation_supporting"
                    if is_post
                    else "intent:nsi_reference_regulation_supporting",
                    1.15,
                )
            )
        elif signals.document_in("nsi_project_docs", context.document_type):
            items.append(
                _adjust(
                    self.name,
                    "penalty:nsi_reference_project_docs"
                    if is_post
                    else "intent:nsi_reference_penalty_project_docs",
                    0.32,
                )
            )
        return items


class RequirementPolicy:
    name = "requirement"

    def evaluate(self, context: RankingContext) -> list[ScoreAdjustment]:
        if (
            context.stage != RankingStage.POST_RERANK
            or context.intent is None
            or context.intent.intent != QueryIntent.REQUIREMENT_LOOKUP
        ):
            return []
        items: list[ScoreAdjustment] = []
        if context.document_type == "ФТТ":
            items.append(_adjust(self.name, "boost:requirement_lookup_ftt", 1.6))
        exact = context.signals.has_exact_section(
            context.metadata,
            context.text,
            context.intent.mentioned_sections,
        )
        if exact:
            items.append(_adjust(self.name, "boost:exact_section_mention", 1.9))
        elif context.intent.mentioned_sections:
            items.append(_adjust(self.name, "penalty:no_exact_section_mention", 0.72))
        if context.document_type == "ПР" and exact:
            items.append(_adjust(self.name, "boost:pr_mentions_requirement", 1.15))
        return items


class NoisePolicy:
    name = "noise"

    def evaluate(self, context: RankingContext) -> list[ScoreAdjustment]:
        signals = context.signals
        if context.stage == RankingStage.POST_RERANK:
            if (
                signals.is_glossary_or_front_matter(context.text_lower)
                and context.intent
                and context.intent.intent != QueryIntent.DOCUMENT_OVERVIEW
            ):
                return [_adjust(self.name, "penalty:glossary_or_front_matter", 0.5)]
            return []

        items: list[ScoreAdjustment] = []
        if "глоссарий" not in context.query_lower and signals.has(
            "glossary_chunk", context.text_lower
        ):
            items.append(_adjust(self.name, "penalty:glossary", 0.25))
        if "история изменений" in context.text_lower[:800] and "история" not in context.query_lower:
            items.append(_adjust(self.name, "penalty:change_history", 0.55))
        return items


DEFAULT_POLICIES: tuple[RankingPolicy, ...] = (
    MatchSignalPolicy(),
    DocumentOverviewPolicy(),
    PassportPolicy(),
    FttRoutePolicy(),
    IntegrationPolicy(),
    SoiPolicy(),
    ProjectDecisionPolicy(),
    PerformancePolicy(),
    CtaPolicy(),
    NsiPolicy(),
    RequirementPolicy(),
    NoisePolicy(),
)


def evaluate_policies(
    context: RankingContext,
    policies: tuple[RankingPolicy, ...] = DEFAULT_POLICIES,
) -> list[ScoreAdjustment]:
    adjustments: list[ScoreAdjustment] = []
    for policy in policies:
        adjustments.extend(policy.evaluate(context))
    return adjustments
