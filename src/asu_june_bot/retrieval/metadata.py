from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any


SYSTEM_EXPORT_HINTS = (
    "система/",
    "asu_admin_export",
    "asu_docs_export",
    "html_export",
    "site_review_runs",
    "playwright",
    "pages_html",
    "pages_text",
    "docs_html",
    "docs_text",
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
    "protocol",
)

INSTRUCTION_HINTS = (
    "руководство",
    "инструкция",
    "admin guide",
    "user guide",
)

SECTION_RE = re.compile(r"(?<!\d)(\d+(?:\.\d+){1,5})\s*\.", re.UNICODE)


def _lower_path(metadata: dict[str, Any]) -> str:
    return str(metadata.get("relative_path") or metadata.get("source_path") or "").replace("\\", "/").lower()


def _norm(value: str) -> str:
    value = value.lower().replace("ё", "е")
    value = value.replace("_", " ").replace("-", " ").replace(".", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def infer_source_type(metadata: dict[str, Any]) -> str:
    path = _lower_path(metadata)
    norm_path = _norm(path)
    if any(hint in path for hint in SYSTEM_EXPORT_HINTS):
        return "system_export"
    if any(_norm(hint) in norm_path for hint in MEETING_HINTS):
        return "meeting_artifact"
    if any(_norm(hint) in norm_path for hint in INSTRUCTION_HINTS):
        return "instruction"
    if any(_norm(hint) in norm_path for hint in ANALYTICAL_NOTE_HINTS):
        return "analytical_note"
    if path.endswith((".py", ".ps1", ".yaml", ".yml", ".json")) and "пд" not in path:
        return "code"
    return "project_doc"


def infer_document_type(metadata: dict[str, Any]) -> str | None:
    path = _lower_path(metadata)
    name = PurePosixPath(path).name
    search_area = _norm(f"{path} {name}")

    candidates: list[tuple[tuple[str, ...], str]] = [
        (("фтт", "функционально технические требования", "функциональные требования"), "ФТТ"),
        (("цта", "целевая техническая архитектура"), "ЦТА"),
        (("проектное решение", " пр ", " цп упкс пр ", "проектное решение смр"), "ПР"),
        (("паспорт ис", "паспорт информационной системы", "паспорт системы"), "Паспорт ИС"),
        (("пми", "программа и методика испытаний", "сценарии функциональных испытаний", "сценарии нефункциональных испытаний"), "ПМИ"),
        (("сои ad", "соглашение об интеграции active directory", "active directory"), "СоИ AD"),
        (("сои справоч", "соглашение об интеграции справоч", "соглашение об интеграции нси", "mdr", "кшд"), "СоИ Справочники"),
        (("реестр объектов нси", "реест объектов нси", "реестр нси"), "Реестр НСИ"),
        (("руководство администратора", "руководство пользователя", "инструкция пользователя", "инструкция администратора"), "Руководство"),
        (("протокол", "protocol"), "Протокол"),
        (("wiki", "вики"), "Wiki"),
        (("bpmn", "бизнес процесс", "to be", "as is"), "BPMN / Процесс"),
        (("api", "openapi", "swagger", "scalar"), "API"),
    ]

    for markers, doc_type in candidates:
        if any(marker in search_area for marker in markers):
            return doc_type
    return None


def infer_module(metadata: dict[str, Any]) -> str | None:
    path = _lower_path(metadata)
    norm_path = _norm(path)
    markers: list[tuple[str, str]] = [
        ("строительный контроль", "СМР / Строительный контроль"),
        ("стройконтроль", "СМР / Строительный контроль"),
        ("construction control", "СМР / Строительный контроль"),
        ("смр", "СМР"),
        ("мто", "МТО"),
        ("мтр", "МТО"),
        ("пир", "ПИР"),
        ("ксп", "КСП"),
        ("календарно сетевое", "КСП"),
        ("справоч", "НСИ / Справочники"),
        ("нси", "НСИ / Справочники"),
        ("active directory", "AD / Авторизация"),
        (" ad ", "AD / Авторизация"),
        ("blitz", "SSO / Авторизация"),
        ("исполнительн", "Исполнительная документация"),
        ("пми", "ПМИ"),
        ("паспорт", "Паспорт ИС"),
    ]
    padded = f" {norm_path} "
    for marker, module in markers:
        if marker in padded:
            return module
    return None


def infer_stage(metadata: dict[str, Any]) -> str | None:
    path = _lower_path(metadata)
    text = _norm(path)
    patterns = [
        (r"этап\s*1\.2", "Этап 1.2"),
        (r"этап\s*1\.1", "Этап 1.1"),
        (r"этап\s*1(?:\D|$)", "Этап 1"),
        (r"этап\s*2\.1", "Этап 2.1"),
        (r"этап\s*2(?:\D|$)", "Этап 2"),
        (r"этап\s*3(?:\D|$)", "Этап 3"),
        (r"этап\s*4(?:\D|$)", "Этап 4"),
    ]
    for pattern, stage in patterns:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return stage
    return None


def infer_sections(text: str, limit: int = 20) -> list[str]:
    """Extract numbered sections mentioned in a chunk.

    Chunks often begin in the middle of a Word table, so the first relevant
    requirement number may be far from the first line. Store all section-like
    markers, and keep `section` as the first marker for backward compatibility.
    """
    seen: set[str] = set()
    sections: list[str] = []
    for match in SECTION_RE.finditer(text[:6000]):
        section = match.group(1)
        if section in seen:
            continue
        # Avoid capturing version-like long fragments or tiny table counters.
        if section.count(".") > 5:
            continue
        seen.add(section)
        sections.append(section)
        if len(sections) >= limit:
            break
    return sections


def infer_section(text: str) -> str | None:
    sections = infer_sections(text, limit=1)
    if sections:
        return sections[0]

    head = text[:1000]
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
    sections = infer_sections(text)
    enriched.setdefault("sections", sections)
    enriched.setdefault("section", sections[0] if sections else infer_section(text))
    enriched.setdefault("title", None)
    return enriched
