from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.retrieval.context_builder import BuiltContext  # noqa: E402
from asu_june_bot.retrieval.models import SearchResult  # noqa: E402
from asu_june_bot.search.service import SearchService  # noqa: E402

QUERY = "Какая роль соответствует PROJECT_ROLE_GROUP_01 строительного контроля?"


def _source(key: str, *, matching: bool = False) -> SearchResult:
    text = (
        "PROJECT_ROLE_GROUP_01 Отвечающий за выполнение функции строительного контроля"
        if matching
        else "Обычная справочная информация по системе"
    )
    return SearchResult(
        source_id=f"source-{key}",
        text=text,
        score=1.0,
        vector_score=None,
        bm25_score=1.0,
        metadata={
            "chunk_id": key,
            "document_type": "СоИ AD",
            "relative_path": "synthetic/soi-ad.md",
        },
        matched_by=["bm25"],
    )


def _keys(sources: list[SearchResult]) -> list[str]:
    return [SearchService._result_key(source) for source in sources]


def test_primary_only_is_preserved_without_promotion_diagnostics() -> None:
    primary = _source("primary-match", matching=True)
    context = BuiltContext(
        primary_sources=[primary],
        diagnostics={"builder": "test"},
    )

    result = SearchService()._promote_ad_cc_role_mapping_sources(QUERY, context)

    assert result is context
    assert _keys(result.primary_sources) == ["primary-match"]
    assert "ad_cc_role_mapping_promotion" not in result.diagnostics


def test_matching_supporting_source_is_promoted_deterministically() -> None:
    context = BuiltContext(
        primary_sources=[_source("primary")],
        supporting_sources=[
            _source("promote-1", matching=True),
            _source("supporting"),
            _source("promote-2", matching=True),
        ],
        diagnostics={"builder": "test"},
    )

    result = SearchService()._promote_ad_cc_role_mapping_sources(QUERY, context)

    assert _keys(result.primary_sources) == ["promote-1", "promote-2", "primary"]
    assert _keys(result.supporting_sources) == ["supporting"]
    assert result.diagnostics["ad_cc_role_mapping_promotion"] == {
        "applied": True,
        "promoted": 2,
        "chunk_ids": ["promote-1", "promote-2"],
    }


def test_nonmatching_primary_never_moves_or_duplicates() -> None:
    context = BuiltContext(
        primary_sources=[_source("ordinary-primary")],
        supporting_sources=[_source("promoted", matching=True)],
    )

    result = SearchService()._promote_ad_cc_role_mapping_sources(QUERY, context)

    assert _keys(result.primary_sources) == ["promoted", "ordinary-primary"]
    assert result.supporting_sources == []


def test_primary_key_wins_over_duplicate_supporting_key() -> None:
    primary = _source("same")
    context = BuiltContext(
        primary_sources=[primary],
        supporting_sources=[_source("same", matching=True), _source("other")],
        diagnostics={"builder": "test"},
    )

    result = SearchService()._promote_ad_cc_role_mapping_sources(QUERY, context)

    assert result.primary_sources == [primary]
    assert _keys(result.supporting_sources) == ["other"]
    assert "ad_cc_role_mapping_promotion" not in result.diagnostics


def test_duplicate_keys_within_each_bucket_are_removed_first_wins() -> None:
    first_primary = _source("primary")
    first_supporting = _source("supporting")
    context = BuiltContext(
        primary_sources=[first_primary, _source("primary", matching=True)],
        supporting_sources=[first_supporting, _source("supporting")],
    )

    result = SearchService()._promote_ad_cc_role_mapping_sources(QUERY, context)

    assert result.primary_sources == [first_primary]
    assert result.supporting_sources == [first_supporting]
    assert "ad_cc_role_mapping_promotion" not in result.diagnostics


def test_duplicate_matching_supporting_source_is_promoted_once() -> None:
    first = _source("matching", matching=True)
    context = BuiltContext(
        supporting_sources=[first, _source("matching", matching=True)],
    )

    result = SearchService()._promote_ad_cc_role_mapping_sources(QUERY, context)

    assert result.primary_sources == [first]
    assert result.supporting_sources == []
    assert result.diagnostics["ad_cc_role_mapping_promotion"]["promoted"] == 1
    assert result.diagnostics["ad_cc_role_mapping_promotion"]["chunk_ids"] == [
        "matching"
    ]


def test_non_target_query_does_not_rebucket_sources() -> None:
    context = BuiltContext(
        primary_sources=[_source("primary")],
        supporting_sources=[_source("matching", matching=True)],
    )

    result = SearchService()._promote_ad_cc_role_mapping_sources(
        "Какой статус проекта?",
        context,
    )

    assert result is context
