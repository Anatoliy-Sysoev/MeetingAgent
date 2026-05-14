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
    "Wiki": 0.55,
}

DEFAULT_EXCLUDED_PATH_MARKERS = [
    "/wip результаты/",
    "/неразобранное после авторазбора/",
    "/_авторазбор/",
    "/черновики и шаблоны/",
    "/_to_review",
]

DEFAULT_PATH_WEIGHT_MARKERS = {
    "/_wiki/": 0.62,
    "/_analysis/": 0.82,
    "/общепроектные/встречи и транскрибация/": 0.86,
}

DEFAULT_CONTEXT_WEIGHT_MARKERS = {
    "глоссарий": 0.2,
    "история изменений": 0.35,
    "связанные документы": 0.45,
    "список сокращений": 0.3,
    "термины и определения": 0.35,
}


class SourcePolicy:
    def __init__(self, config: dict[str, Any] | None = None):
        config = config or {}
        self.allowed_by_default = list(config.get("allowed_by_default") or DEFAULT_ALLOWED_SOURCE_TYPES)
        self.weights = dict(DEFAULT_SOURCE_TYPE_WEIGHTS)
        self.weights.update(config.get("weights") or {})
        self.document_type_weights = dict(DEFAULT_DOCUMENT_TYPE_WEIGHTS)
        self.document_type_weights.update(config.get("document_type_weights") or {})
        self.excluded_path_markers = [str(item).lower() for item in (config.get("excluded_path_markers") or DEFAULT_EXCLUDED_PATH_MARKERS)]
        self.path_weight_markers = dict(DEFAULT_PATH_WEIGHT_MARKERS)
        self.path_weight_markers.update({str(key).lower(): float(value) for key, value in (config.get("path_weight_markers") or {}).items()})
        self.context_weight_markers = dict(DEFAULT_CONTEXT_WEIGHT_MARKERS)
        self.context_weight_markers.update({str(key).lower(): float(value) for key, value in (config.get("context_weight_markers") or {}).items()})
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

    @staticmethod
    def _relative_path(metadata: dict[str, Any]) -> str:
        return str(metadata.get("relative_path") or metadata.get("source_path") or "").replace("\\", "/").lower()

    @staticmethod
    def _context_text(metadata: dict[str, Any]) -> str:
        parts = [
            metadata.get("title"),
            metadata.get("parent_hint"),
            metadata.get("table_title"),
            metadata.get("document_name"),
            metadata.get("block_type"),
        ]
        return " ".join(str(part or "") for part in parts).lower()

    def is_excluded_path(self, metadata: dict[str, Any]) -> bool:
        path = f"/{self._relative_path(metadata)}"
        return any(marker in path for marker in self.excluded_path_markers)

    def is_allowed(self, metadata: dict[str, Any], query: str, requested: list[str] | None = None) -> bool:
        if self.is_excluded_path(metadata):
            return False
        source_type = str(metadata.get("source_type") or "project_doc")
        return source_type in self.allowed_source_types_for_query(query, requested)

    def weight(self, metadata: dict[str, Any]) -> float:
        if self.is_excluded_path(metadata):
            return 0.0

        source_type = str(metadata.get("source_type") or "project_doc")
        document_type = metadata.get("document_type")
        source_weight = float(self.weights.get(source_type, self.weights.get("unknown", 0.5)))
        document_weight = float(self.document_type_weights.get(str(document_type), 1.0)) if document_type else 1.0
        path = f"/{self._relative_path(metadata)}"
        path_weight = 1.0
        for marker, weight in self.path_weight_markers.items():
            if marker in path:
                path_weight *= float(weight)

        context = self._context_text(metadata)
        context_weight = 1.0
        for marker, weight in self.context_weight_markers.items():
            if marker in context:
                context_weight *= float(weight)

        return source_weight * document_weight * path_weight * context_weight
