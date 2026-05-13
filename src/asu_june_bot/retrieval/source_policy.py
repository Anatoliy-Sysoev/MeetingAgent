from __future__ import annotations

from typing import Any


DEFAULT_ALLOWED_SOURCE_TYPES = ["project_doc", "meeting_artifact", "analytical_note", "instruction"]
DEFAULT_SOURCE_TYPE_WEIGHTS = {
    "project_doc": 1.0,
    "meeting_artifact": 0.9,
    "analytical_note": 0.82,
    "instruction": 0.82,
    "system_export": 0.12,
    "runtime_export": 0.1,
    "code": 0.25,
    "unknown": 0.5,
}

DEFAULT_DOCUMENT_TYPE_WEIGHTS = {
    "ФТТ": 1.25,
    "ЦТА": 1.22,
    "ПР": 1.18,
    "СоИ AD": 1.16,
    "СоИ Справочники": 1.16,
    "Паспорт ИС": 1.12,
    "ПМИ": 1.08,
    "Руководство": 0.98,
    "Протокол": 0.92,
    "Реестр НСИ": 0.88,
    "BPMN / Процесс": 0.84,
    "API": 0.8,
    "Wiki": 0.72,
}


class SourcePolicy:
    def __init__(self, config: dict[str, Any] | None = None):
        config = config or {}
        self.allowed_by_default = list(config.get("allowed_by_default") or DEFAULT_ALLOWED_SOURCE_TYPES)
        self.weights = dict(DEFAULT_SOURCE_TYPE_WEIGHTS)
        self.weights.update(config.get("weights") or {})
        self.document_type_weights = dict(DEFAULT_DOCUMENT_TYPE_WEIGHTS)
        self.document_type_weights.update(config.get("document_type_weights") or {})
        self.explicit_enable_markers = config.get("explicit_enable_markers") or {
            "system_export": [
                "система",
                "системная выгрузка",
                "админка",
                "django admin",
                "asu_admin_export",
                "asu_docs_export",
                "site_review",
                "html export",
                "экспорт сайта",
                "интерфейс",
                "страница",
                "токен",
                "пользователь",
                "роль",
            ],
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
        document_type = metadata.get("document_type")
        source_weight = float(self.weights.get(source_type, self.weights.get("unknown", 0.5)))
        document_weight = float(self.document_type_weights.get(str(document_type), 1.0)) if document_type else 1.0
        return source_weight * document_weight
