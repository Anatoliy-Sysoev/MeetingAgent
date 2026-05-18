from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.retrieval.source_policy import SourcePolicy  # noqa: E402


def test_requested_source_types_are_intersected_with_default_allowlist() -> None:
    policy = SourcePolicy()

    allowed = policy.allowed_source_types_for_query("Паспорт ИС", requested=["project_doc", "code", "system_export"])

    assert allowed == {"project_doc"}


def test_requested_unsafe_source_type_is_not_enabled_without_query_marker() -> None:
    policy = SourcePolicy()

    allowed = policy.allowed_source_types_for_query("Паспорт ИС", requested=["code"])

    assert allowed == set()


def test_explicit_marker_can_enable_extra_type_but_only_when_requested_or_needed() -> None:
    policy = SourcePolicy()

    allowed = policy.allowed_source_types_for_query("Покажи ошибку в скрипте индексации", requested=["code", "system_export"])

    assert allowed == {"code"}
