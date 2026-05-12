from __future__ import annotations

from typing import Any


class QueryExpander:
    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

    def expand(self, query: str) -> tuple[str, list[str]]:
        lowered = query.lower()
        expansions: list[str] = []
        for _group_name, group in self.config.items():
            if not isinstance(group, dict):
                continue
            triggers = [str(item).lower() for item in group.get("triggers", [])]
            if not triggers or not any(trigger in lowered for trigger in triggers):
                continue
            for item in group.get("expansions", []):
                term = str(item).strip()
                if term and term.lower() not in lowered and term not in expansions:
                    expansions.append(term)
        if not expansions:
            return query, []
        return query + "\n" + " ".join(expansions), expansions
