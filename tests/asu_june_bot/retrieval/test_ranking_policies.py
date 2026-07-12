from __future__ import annotations

import pytest

from asu_june_bot.retrieval.query_intent import classify_query_intent
from asu_june_bot.retrieval.ranking_policies import (
    CtaPolicy,
    DocumentOverviewPolicy,
    FttRoutePolicy,
    IntegrationPolicy,
    MatchSignalPolicy,
    NoisePolicy,
    NsiPolicy,
    PassportPolicy,
    PerformancePolicy,
    ProjectDecisionPolicy,
    RankingContext,
    RankingStage,
    RequirementPolicy,
    ScoreAdjustment,
    SoiPolicy,
    adjustment_multiplier,
    adjustment_trace,
)
from asu_june_bot.retrieval.ranking_profile import default_ranking_profile


def _context(
    *,
    stage: RankingStage = RankingStage.POST_RERANK,
    query: str = "вопрос об архитектуре",
    text: str = "содержательный синтетический фрагмент",
    document_type: str = "ФТТ",
    matched_by: tuple[str, ...] = ("bm25",),
    relative_path: str = "synthetic/doc.md",
    sections: list[str] | None = None,
    requirement_id: str | None = None,
) -> RankingContext:
    return RankingContext(
        stage=stage,
        query=query,
        original_query=query.split("\n", 1)[0],
        text=text,
        metadata={
            "document_type": document_type,
            "relative_path": relative_path,
            "sections": sections or [],
            "requirement_id": requirement_id,
        },
        document_type=document_type,
        matched_by=matched_by,
        profile=default_ranking_profile(),
        intent=classify_query_intent(query) if stage == RankingStage.POST_RERANK else None,
    )


def _labels(policy, context: RankingContext) -> list[str]:
    return [item.label for item in policy.evaluate(context)]


@pytest.mark.parametrize(
    ("matched_by", "query", "labels"),
    [
        (("bm25", "vector"), "архитектура", ["boost:matched_by_bm25_and_vector"]),
        (("vector",), "Что требует ФТТ 4.2.5?", ["penalty:vector_only_for_exact_or_overview"]),
        (("vector",), "архитектура проекта", ["penalty:vector_only"]),
        (("bm25",), "архитектура проекта", []),
    ],
)
def test_match_signal_policy(matched_by, query: str, labels: list[str]) -> None:
    assert _labels(MatchSignalPolicy(), _context(query=query, matched_by=matched_by)) == labels


def test_document_overview_policy_ignores_other_intents() -> None:
    assert DocumentOverviewPolicy().evaluate(_context(query="архитектура проекта")) == []


@pytest.mark.parametrize(
    ("stage", "document_type", "expected"),
    [
        (RankingStage.POST_RERANK, "ЦТА", ["penalty:passport_other_doc_type"]),
        (
            RankingStage.BM25,
            "ЦТА",
            ["intent:passport", "penalty:passport_other_doc_type"],
        ),
        (RankingStage.POST_RERANK, "Протокол", []),
        (RankingStage.BM25, "Протокол", ["intent:passport"]),
    ],
)
def test_passport_policy_non_primary_documents(
    stage: RankingStage,
    document_type: str,
    expected: list[str],
) -> None:
    context = _context(
        stage=stage,
        query="Какие приложения перечислены в паспорте ИС?",
        document_type=document_type,
    )
    assert _labels(PassportPolicy(), context) == expected


def test_passport_bm25_overview_scope_and_noise_are_explicit() -> None:
    context = _context(
        stage=RankingStage.BM25,
        query="Что входит в паспорт ИС?",
        text="Общие сведения. Контекст: программное обеспечение информационной системы.",
        document_type="Паспорт ИС",
    )
    assert _labels(PassportPolicy(), context) == [
        "intent:passport",
        "intent:passport_overview_scope",
        "penalty:passport_software_table_for_overview",
    ]


@pytest.mark.parametrize(
    ("document_type", "expected"),
    [
        ("ФТТ", ["intent:ftt"]),
        ("ПМИ", ["intent:ftt_penalty_pmi"]),
        ("ПР", ["intent:ftt_penalty_pr"]),
        ("ЦТА", []),
    ],
)
def test_ftt_route_policy(document_type: str, expected: list[str]) -> None:
    context = _context(
        stage=RankingStage.BM25,
        query="Что указано в ФТТ?",
        document_type=document_type,
    )
    assert _labels(FttRoutePolicy(), context) == expected


def test_integration_policy_covers_pr_vector_penalty_and_wiki_penalty() -> None:
    post = _context(
        query="Какие интеграции описаны в проектном решении?",
        document_type="ПР",
        matched_by=("vector",),
    )
    lexical = _context(
        stage=RankingStage.BM25,
        query="Какие интеграции описаны?",
        document_type="Wiki",
    )
    assert _labels(IntegrationPolicy(), post) == ["penalty:integration_pr_vector_only"]
    assert _labels(IntegrationPolicy(), lexical) == ["intent:integrations_wiki_penalty"]


@pytest.mark.parametrize(
    ("stage", "document_type", "text", "expected"),
    [
        (
            RankingStage.POST_RERANK,
            "ПР",
            "project_role groups роль",
            ["boost:soi_ad_role_mapping_supporting_chunk"],
        ),
        (
            RankingStage.BM25,
            "ЦТА",
            "общий текст",
            ["intent:soi_ad_penalty_generic_docs"],
        ),
    ],
)
def test_soi_policy_supporting_and_generic_paths(
    stage: RankingStage,
    document_type: str,
    text: str,
    expected: list[str],
) -> None:
    context = _context(
        stage=stage,
        query="Как группы AD передаются через LDAPS?",
        text=text,
        document_type=document_type,
    )
    assert _labels(SoiPolicy(), context) == expected


def test_project_decision_policy_covers_transition_and_other_module() -> None:
    context = _context(
        query="В ПР какие статусы замечаний в модуле строительного контроля?",
        text="Статус замечания меняет статус замечания: к устранению, на проверке.",
        document_type="ПР",
        relative_path="synthetic/other-module.md",
    )
    assert _labels(ProjectDecisionPolicy(), context) == [
        "boost:pr_construction_control_route",
        "penalty:pr_other_module_for_construction_control",
        "boost:pr_notice_status_transition",
    ]


@pytest.mark.parametrize(
    ("query", "text", "expected"),
    [
        (
            "В ПР какие статусы замечаний?",
            "Управление замечаниями: операционный контроль.",
            "penalty:pr_notice_status_generic_process",
        ),
        (
            "В ПР как аннулировать замечание?",
            "Управление замечаниями: эскалация.",
            "penalty:pr_notice_annulment_generic_process",
        ),
        (
            "В ПР какие роли предусмотрены?",
            "Роль исполнителя: пользователь.",
            "penalty:pr_roles_generic_process",
        ),
        (
            "В ПР какие права доступа?",
            "Роль исполнителя: пользователь.",
            "penalty:pr_rights_generic_process",
        ),
    ],
)
def test_project_decision_generic_penalties(query: str, text: str, expected: str) -> None:
    assert expected in _labels(
        ProjectDecisionPolicy(), _context(query=query, text=text, document_type="ПР")
    )


def test_performance_policy_is_ftt_only() -> None:
    query = "Какова производительность для 600 одновременно?"
    assert _labels(PerformancePolicy(), _context(query=query, document_type="ФТТ"))
    assert PerformancePolicy().evaluate(_context(query=query, document_type="ЦТА")) == []


def test_cta_recovery_noise_and_non_cta_penalty() -> None:
    cta = _context(
        query="RTO в ЦТА",
        text="Grafana Loki, порт 4317, мониторинг.",
        document_type="ЦТА",
    )
    other = _context(query="RTO в ЦТА", document_type="ФТТ")
    assert _labels(CtaPolicy(), cta) == [
        "boost:cta_recovery_rto_rpo_route",
        "penalty:cta_recovery_logging_or_port_chunk",
    ]
    assert _labels(CtaPolicy(), other) == ["penalty:cta_recovery_non_cta_doc"]


def test_cta_infrastructure_logging_noise_and_explicit_non_cta() -> None:
    cta = _context(
        query="Как PostgreSQL хранит данные в ЦТА?",
        text="PostgreSQL и сервер логирования Grafana Loki.",
        document_type="ЦТА",
    )
    other = _context(query="Как PostgreSQL хранит данные в ЦТА?", document_type="ПР")
    assert "penalty:cta_infrastructure_logging_noise" in _labels(CtaPolicy(), cta)
    assert _labels(CtaPolicy(), other) == ["penalty:cta_infrastructure_non_cta_doc"]


@pytest.mark.parametrize(
    ("query", "document_type", "expected"),
    [
        ("Какие регламенты ведения НСИ?", "Реестр НСИ", "boost:nsi_regulation_register_support"),
        ("Какие регламенты ведения НСИ?", "СоИ Справочники", "boost:nsi_regulation_supporting"),
        ("Какие регламенты ведения НСИ?", "ФТТ", "penalty:nsi_regulation_project_docs"),
        ("Какие справочники НСИ?", "СоИ Справочники", "boost:nsi_reference_soi_spravochniki"),
        ("Какие справочники НСИ?", "Справочник НСИ", "boost:nsi_reference_dictionary"),
        (
            "Какие справочники НСИ?",
            "Методика/Регламент НСИ",
            "boost:nsi_reference_regulation_supporting",
        ),
        ("Какие справочники НСИ?", "ЦТА", "penalty:nsi_reference_project_docs"),
    ],
)
def test_nsi_policy_support_and_penalty_routes(
    query: str,
    document_type: str,
    expected: str,
) -> None:
    assert expected in _labels(NsiPolicy(), _context(query=query, document_type=document_type))


def test_requirement_policy_covers_missing_and_pr_exact_section() -> None:
    missing = _context(
        query="Что требует ФТТ 4.2.5?",
        document_type="ФТТ",
        sections=["4.1"],
    )
    exact_pr = _context(
        query="Что требует раздел 4.2.5?",
        text="Требование 4.2.5 упомянуто в проектном решении.",
        document_type="ПР",
        sections=["4.2.5"],
    )
    assert "penalty:no_exact_section_mention" in _labels(RequirementPolicy(), missing)
    assert _labels(RequirementPolicy(), exact_pr) == [
        "boost:exact_section_mention",
        "boost:pr_mentions_requirement",
    ]


def test_noise_policy_is_stage_and_query_aware() -> None:
    post = _context(query="архитектура проекта", text="Контекст: глоссарий")
    lexical = _context(
        stage=RankingStage.BM25,
        query="архитектура проекта",
        text="Контекст: глоссарий. История изменений.",
    )
    explicit = _context(
        stage=RankingStage.BM25,
        query="глоссарий и история",
        text="Контекст: глоссарий. История изменений.",
    )
    assert _labels(NoisePolicy(), post) == ["penalty:glossary_or_front_matter"]
    assert _labels(NoisePolicy(), lexical) == ["penalty:glossary", "penalty:change_history"]
    assert NoisePolicy().evaluate(explicit) == []


def test_adjustment_math_and_trace_are_deterministic() -> None:
    adjustments = [
        ScoreAdjustment("first", "boost:first", 2.0),
        ScoreAdjustment("second", "penalty:second", 0.25),
    ]
    assert adjustment_multiplier(adjustments) == 0.5
    assert adjustment_trace(RankingStage.POST_RERANK, 10.0, adjustments) == [
        {
            "stage": "post_rerank",
            "policy": "first",
            "label": "boost:first",
            "multiplier": 2.0,
            "score_before": 10.0,
            "score_after": 20.0,
        },
        {
            "stage": "post_rerank",
            "policy": "second",
            "label": "penalty:second",
            "multiplier": 0.25,
            "score_before": 20.0,
            "score_after": 5.0,
        },
    ]
    with pytest.raises(ValueError):
        ScoreAdjustment("bad", "penalty:bad", 0.0)
