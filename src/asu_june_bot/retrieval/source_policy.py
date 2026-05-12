from __future__ import annotations

from typing import Any


DEFAULT_ALLOWED_SOURCE_TYPES = ["project_doc", "meeting_artifact", "analytical_note", "instruction"]
DEFAULT_SOURCE_TYPE_WEIGHTS = {
    "project_doc": 1.0,
    "meeting_artifact": 0.9,
    "analytical_note": 0.85,
    "instruction": 0.8,
    "system_export": 0.55,
    "runtime_export": 0.4,
    "code": 0.35,
}


class SourcePolicy:
    def __init__(self, config: dict[str, Any] | None = None):
        config = config or {}
        self.allowed_by_default = list(config.get("allowed_by_default") or DEFAULT_ALLOWED_SOURCE_TYPES)
        self.weights = dict(DEFAULT_SOURCE_TYPE_WEIGHTS)
        self.weights.update(config.get("weights") or {})
        self.explicit_enable_markers = config.get("explicit_enable_markers") or {
            "system_export": ["админ", "экспорт", "интерфейс", "страница", "токен", "пользователь", "роль"],
            "code": ["код", "скрипт", "python", "powershell", "ошибка в скрипте"],
        }

    def allowed_source_types_for_query(self, query: str, requested: list[str] | None = None) -> set[str]:
        if requested:
            return set(requested)

        lowered = query.lower()
        allowed = set(self.allowed_by_default)
        for source_type, markers in self.explicit_enable_markers.items():
            if any(str(marker).lower() in lowered for marker in markers):
                allowed.add(source_type)
        return allowed

    def is_allowed(self, metadata: dict[str, Any], query: str, requested: list[str] | None = None) -> bool:
        source_type = str(metadata.get("source_type") or "project_doc")
        return source_type in self.allowed_source_types_for_query(query, requested)

    def weight(self, metadata: dict[str, Any]) -> float:
        source_type = str(metadata.get("source_type") or "project_doc")
        return float(self.weights.get(source_type, 0.5))
