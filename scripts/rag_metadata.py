from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def norm(text: str) -> str:
    return " ".join(str(text or "").lower().replace("ё", "е").split())


def infer_doc_type(relative_path: str, text: str = "") -> str:
    haystack = norm(relative_path + " " + text[:1200])
    checks = (
        ("ftt", ("фтт", "функционально-технические требования", "задание заказчика")),
        ("pr", ("проектное решение", "модуль строительный контроль", "пр_смр")),
        ("cta", ("цта", "целевая техническая архитектура")),
        ("soi_ad", ("active directory", "сои_ad", "соглашение об интеграции active directory")),
        ("soi_nsi", ("сои_справочники", "mdr", "кшд", "соглашение об интеграции")),
        ("pmi", ("пми", "программа и методика", "сценарии испытаний")),
        ("psi", ("пси", "протокол испытаний")),
        ("passport", ("паспорт ис", "паспорт информационной системы")),
        ("instruction", ("инструкция", "инструкции сайта")),
        ("analysis", ("_analysis", "analysis")),
    )
    for doc_type, markers in checks:
        if any(marker in haystack for marker in markers):
            return doc_type
    return "unknown"


def infer_source_kind(relative_path: str, text: str = "") -> str:
    doc_type = infer_doc_type(relative_path, text)
    if doc_type in {"ftt", "pr", "cta", "soi_ad", "soi_nsi", "pmi", "psi", "passport"}:
        return "project_document"
    if doc_type == "instruction":
        return "user_instruction"
    if doc_type == "analysis":
        return "derived_analysis"
    return "unknown"


def infer_requirement_id(text: str) -> str | None:
    compact = norm(text[:1200])
    patterns = (
        r"(?:^|\s)(\d{1,2}\.\d{1,2}(?:\.\d{1,2})?)(?:\.|\s)",
        r"требовани[ея]\s+фтт\s*(\d{1,2}\.\d{1,2}(?:\.\d{1,2})?)",
        r"сфт\s*(\d{1,2})",
        r"снт\s*(\d{1,2})",
    )
    for pattern in patterns:
        match = re.search(pattern, compact, flags=re.IGNORECASE)
        if match:
            value = match.group(1)
            if pattern.startswith("сфт"):
                return f"СФТ {value}"
            if pattern.startswith("снт"):
                return f"СНТ {value}"
            return value
    return None


def infer_section(text: str, relative_path: str = "") -> str | None:
    compact = " ".join(str(text or "").split())
    section_patterns = (
        r"(?:^|\n)\s*(\d+(?:\.\d+){0,4})\s+([^\n]{3,140})",
        r"(?:^|\n)\s*(Табл\.?\s*\d+[^\n]{0,120})",
        r"(?:^|\n)\s*(Таблица\s*\d+[^\n]{0,120})",
        r"(?:^|\n)\s*(Сценарий\s*\d+[^\n]{0,120})",
    )
    for pattern in section_patterns:
        match = re.search(pattern, compact, flags=re.IGNORECASE)
        if not match:
            continue
        if len(match.groups()) >= 2:
            return f"{match.group(1)} {match.group(2)}".strip()
        return match.group(1).strip()
    req = infer_requirement_id(text)
    if req:
        return req
    path = Path(relative_path)
    return path.stem if path.stem else None


def enrich_chunk_metadata(row: dict[str, Any]) -> dict[str, Any]:
    text = str(row.get("text") or "")
    relative_path = str(row.get("relative_path") or "")
    enriched = dict(row)
    enriched.setdefault("doc_type", infer_doc_type(relative_path, text))
    enriched.setdefault("source_kind", infer_source_kind(relative_path, text))
    enriched.setdefault("section", infer_section(text, relative_path))
    enriched.setdefault("requirement_id", infer_requirement_id(text))
    return enriched


def metadata_from_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "doc_type": row.get("doc_type"),
        "source_kind": row.get("source_kind"),
        "section": row.get("section"),
        "requirement_id": row.get("requirement_id"),
    }
