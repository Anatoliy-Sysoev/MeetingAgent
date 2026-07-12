from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from types import MappingProxyType
from typing import Any, Mapping

from meeting_agent.shared.config import load_asu_config


MAX_GROUPS = 100
MAX_VALUES_PER_GROUP = 200
MAX_VALUE_CHARS = 180
_GROUP_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


class RankingProfileError(ValueError):
    pass


def _normalize_group_values(group: str, raw: Any) -> tuple[str, ...]:
    if not isinstance(raw, list) or not raw or len(raw) > MAX_VALUES_PER_GROUP:
        raise RankingProfileError(f"ranking profile group {group!r} must be a bounded list")
    values: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            raise RankingProfileError(f"ranking profile group {group!r} values must be strings")
        value = " ".join(item.lower().split())
        if not value or len(value) > MAX_VALUE_CHARS:
            raise RankingProfileError(f"ranking profile group {group!r} has an invalid value")
        if value in seen:
            raise RankingProfileError(f"ranking profile group {group!r} contains a duplicate")
        seen.add(value)
        values.append(value)
    return tuple(values)


def _normalize_groups(raw: Any, *, field_name: str) -> Mapping[str, tuple[str, ...]]:
    if not isinstance(raw, dict) or not raw or len(raw) > MAX_GROUPS:
        raise RankingProfileError(f"ranking profile {field_name} must be a bounded object")
    groups: dict[str, tuple[str, ...]] = {}
    for name, values in raw.items():
        if not isinstance(name, str) or not _GROUP_NAME_RE.fullmatch(name):
            raise RankingProfileError(f"ranking profile {field_name} has an invalid group name")
        groups[name] = _normalize_group_values(name, values)
    return MappingProxyType(groups)


@dataclass(frozen=True, slots=True)
class RankingProfile:
    version: int
    markers: Mapping[str, tuple[str, ...]]
    document_groups: Mapping[str, tuple[str, ...]]

    @classmethod
    def from_config(cls, raw: dict[str, Any]) -> "RankingProfile":
        if not isinstance(raw, dict) or set(raw) != {"version", "markers", "document_groups"}:
            raise RankingProfileError(
                "ranking profile must contain version, markers and document_groups"
            )
        if raw.get("version") != 1:
            raise RankingProfileError("unsupported ranking profile version")
        return cls(
            version=1,
            markers=_normalize_groups(raw["markers"], field_name="markers"),
            document_groups=_normalize_groups(raw["document_groups"], field_name="document_groups"),
        )

    def has_any(self, group: str, text: str) -> bool:
        lowered = " ".join((text or "").lower().split())
        return any(marker in lowered for marker in self.markers.get(group, ()))

    def count(self, group: str, text: str) -> int:
        lowered = " ".join((text or "").lower().split())
        return sum(1 for marker in self.markers.get(group, ()) if marker in lowered)

    def document_in(self, group: str, document_type: str) -> bool:
        return document_type.lower() in self.document_groups.get(group, ())


@lru_cache(maxsize=1)
def default_ranking_profile() -> RankingProfile:
    config = load_asu_config()
    return RankingProfile.from_config(config["ranking_profile"])


def build_ranking_profile(config: dict[str, Any] | None) -> RankingProfile:
    if not config:
        return default_ranking_profile()
    root = config.get("asu_june_bot", config)
    raw = root.get("ranking_profile") if isinstance(root, dict) else None
    if not raw:
        return default_ranking_profile()
    return RankingProfile.from_config(raw)
