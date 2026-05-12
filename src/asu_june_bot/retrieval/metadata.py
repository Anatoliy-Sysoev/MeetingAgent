from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any


SYSTEM_EXPORT_HINTS = (
    "asu_admin_export",
    "html_export",
    "site_review_runs",
    "token_blacklist",
    "_analysis/site",
)

ANALYTICAL_NOTE_HINTS = (
    "_analysis/",
    "analysis/",
    "замечан",
    "сравнен",
    "маппинг",
    "mapping",
)

MEETING_HINTS = (
    "meetings/",
    "протокол",
    "memo",
    "transcript",
)


def _lower_path(metadata: dict[str, Any]) -> str:
    return str(metadata.get("relative_path") or metadata.get("source_path") or "").replace("\\", "/").lower()


def infer_source_type(metadata: dict[str, Any]) -> str:
    path = _lower_path(metadata)
    if any(hint in path for hint in SYSTEM_EXPORT_HINTS):
        return "system_export"
    if any(hint in path for hint in MEETING_HINTS):
        return "meeting_artifact"
    if any(hint in path for hint in ANALYTICAL_NOTE_HINTS):
        return "analytical_note"
    if path.endswith((".py", ".ps1", ".yaml", ".yml", ".json")) and not "пд" in path:
        return "code"
    return "project_doc"


def infer_document_type(metadata: dict[str, Any]) -> str | None:
    path = _lower_path(metadata)
    name = PurePosixPath(path).name
    candidates: list[tuple[str, str]] = [
        ("ФТТ", "ФТТ"),
        ("функционально", "ФТТ"),
        ("цта", "ЦТА"),
        ("паспорт", "Паспорт ИС"),
        ("пми", "ПМИ"),
        ("программа и методика", "ПМИ"),
        ("проектное решение", "ПР"),
        ("_пр_", "ПР"),
        ("пp_", "ПР"),
        ("сои_ad", "СоИ AD"),
        ("сои ad", "СоИ AD"),
        ("сои_справоч", "СоИ Справочники"),
        ("сои справоч", "СоИ Справочники"),
        ("руководство", "Руководство"),
        ("инструкция", "Инструкция"),
        ("протокол", "Протокол"),
    ]
    search_area = f"{path} {name}"
    for marker, doc_type in candidates:
        if marker.lower() in search_area:
            return doc_type
    return None


def infer_module(metadata: dict[str, Any]) -> str | None:
    path = _lower_path(metadata)
    markers: list[tuple[str, str]] = [
        ("строительн", "СМР / Строительный контроль"),
        ("смр", "СМР"),
        ("мто", "МТО"),
        ("пир", "ПИР"),
        ("справоч", "НСИ / Справочники"),
        ("ad", "AD / Авторизация"),
        ("исполнительн", "Исполнительная документация"),
        ("пми", "ПМИ"),
        ("паспорт", "Паспорт ИС"),
    ]
    for marker, module in markers:
        if marker in path:
            return module
    return None


def infer_stage(metadata: dict[str, Any]) -> str | None:
    path = _lower_path(metadata)
    text = path.replace("_", " ").replace("-", " ")
    patterns = [
        (r"этап\s*1(?:\D|$)", "Этап 1"),
        (r"этап\s*1\.2", "Этап 1.2"),
        (r"этап\s*2(?:\D|$)", "Этап 2"),
        (r"этап\s*3(?:\D|$)", "Этап 3"),
        (r"этап\s*4(?:\D|$)", "Этап 4"),
    ]
    for pattern, stage in patterns:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return stage
    return None


def infer_section(text: str) -> str | None:
    head = text[:500]
    patterns = [
        r"(?:^|\n)\s*(\d+(?:\.\d+){1,5})\s+[А-ЯA-Z]",
        r"(?:ФТТ|ЦТА|ПР)\s*(\d+(?:\.\d+){1,5})",
        r"(?:раздел|пункт)\s*(\d+(?:\.\d+){1,5})",
    ]
    for pattern in patterns:
        match = re.search(pattern, head, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def enrich_metadata(metadata: dict[str, Any], text: str) -> dict[str, Any]:
    enriched = dict(metadata)
    enriched.setdefault("source_type", infer_source_type(enriched))
    enriched.setdefault("document_type", infer_document_type(enriched))
    enriched.setdefault("module", infer_module(enriched))
    enriched.setdefault("stage", infer_stage(enriched))
    enriched.setdefault("section", infer_section(text))
    enriched.setdefault("title", None)
    return enriched
