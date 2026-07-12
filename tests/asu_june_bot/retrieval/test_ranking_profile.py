from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from asu_june_bot.retrieval.ranking_profile import (
    MAX_GROUPS,
    MAX_VALUE_CHARS,
    RankingProfile,
    RankingProfileError,
    build_ranking_profile,
    default_ranking_profile,
)


ROOT = Path(__file__).resolve().parents[3]
PROFILE_PATH = ROOT / "configs" / "asu_june_bot" / "ranking_profile.yaml"


def _raw_profile() -> dict:
    return yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))


def test_public_profile_is_bounded_and_immutable() -> None:
    profile = default_ranking_profile()

    assert profile.version == 1
    assert profile.has_any("passport_route", "Что указано в ПАСПОРТЕ ИС?")
    assert profile.document_in("integration_primary", "ЦТА")
    assert profile.count("pr_status_values", "к устранению, на проверке") == 2
    with pytest.raises(TypeError):
        profile.markers["new_group"] = ("value",)  # type: ignore[index]


def test_nested_config_builds_custom_profile() -> None:
    raw = _raw_profile()
    raw["markers"]["passport_route"] = ["custom passport marker"]
    profile = build_ranking_profile({"asu_june_bot": {"ranking_profile": raw}})

    assert profile.has_any("passport_route", "custom passport marker")
    assert not profile.has_any("passport_route", "паспорт ис")


def test_missing_config_uses_public_profile() -> None:
    assert build_ranking_profile(None) is default_ranking_profile()
    assert build_ranking_profile({"asu_june_bot": {}}) is default_ranking_profile()


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda raw: raw.update(version=2), "unsupported"),
        (lambda raw: raw.update(extra=True), "must contain"),
        (lambda raw: raw.update(markers=[]), "bounded object"),
        (
            lambda raw: raw["markers"].update({"Bad Name": ["value"]}),
            "invalid group name",
        ),
        (
            lambda raw: raw["markers"].update({"valid_name": "not-a-list"}),
            "bounded list",
        ),
        (
            lambda raw: raw["markers"].update({"valid_name": [123]}),
            "values must be strings",
        ),
        (
            lambda raw: raw["markers"].update({"valid_name": ["same", " same "]}),
            "duplicate",
        ),
        (
            lambda raw: raw["markers"].update({"valid_name": ["x" * (MAX_VALUE_CHARS + 1)]}),
            "invalid value",
        ),
        (
            lambda raw: raw.update(
                markers={f"group_{index}": ["value"] for index in range(MAX_GROUPS + 1)}
            ),
            "bounded object",
        ),
    ],
)
def test_invalid_profile_fails_closed(mutate, message: str) -> None:
    raw = copy.deepcopy(_raw_profile())
    mutate(raw)
    with pytest.raises(RankingProfileError, match=message):
        RankingProfile.from_config(raw)


def test_customer_vocabulary_is_not_embedded_in_ranking_orchestrators() -> None:
    for relative_path in (
        "src/asu_june_bot/retrieval/post_rerank.py",
        "src/asu_june_bot/retrieval/bm25.py",
        "src/asu_june_bot/retrieval/hybrid.py",
    ):
        source = (ROOT / relative_path).read_text(encoding="utf-8").lower()
        assert "project_role" not in source
        assert "статусы замечаний" not in source
        assert "куратор проекта" not in source
