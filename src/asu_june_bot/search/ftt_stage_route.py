from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

from asu_june_bot.retrieval.chunks import read_jsonl

from .models import SearchRequest, SearchResponse, SearchStatus


STAGE_DOC_MARKERS = (
    "какие документы",
    "какая документация",
    "документы необходим",
    "документы относятся",
    "документация относится",
    "проектная документация",
    "состав работ",
    "отчетные документы",
    "отчётные документы",
)

FTT_GLOSSARY_MARKERS = (
    "что такое фтт",
    "фтт что это",
    "расшифруй фтт",
    "что означает фтт",
)

STAGE_GROUPS: dict[str, tuple[str, ...]] = {
    "1": ("1", "1.1", "1.2", "1.3"),
    "1.1": ("1.1",),
    "1.2": ("1.2",),
    "1.3": ("1.3",),
    "2": ("2", "2.1", "2.2", "2.3"),
    "2.1": ("2.1",),
    "2.2": ("2.2",),
    "2.3": ("2.3",),
}

_STAGE_RE = re.compile(r"этап(?:а|е|у|ом)?\s*(\d(?:\.\d)?)", re.IGNORECASE | re.UNICODE)


def _norm(text: str) -> str:
    return " ".join((text or "").lower().replace("ё", "е").split())


def _is_ftt_glossary_query(query: str) -> bool:
    lowered = _norm(query)
    return any(marker in lowered for marker in FTT_GLOSSARY_MARKERS)


def _extract_stage(query: str) -> str | None:
    lowered = _norm(query)
    match = _STAGE_RE.search(lowered)
    if match:
        value = match.group(1)
        return value if value in STAGE_GROUPS else None
    if "фт1" in lowered:
        return "1"
    if "фт2" in lowered:
        return "2"
    return None


def _is_stage_docs_query(query: str) -> bool:
    lowered = _norm(query)
    stage = _extract_stage(lowered)
    if not stage:
        return False
    return any(marker in lowered for marker in STAGE_DOC_MARKERS) or "фтт" in lowered


def _row_text(row: dict[str, Any]) -> str:
    return " ".join(str(row.get("text") or row.get("text_preview") or "").split())


def _row_haystack(row: dict[str, Any]) -> str:
    parts = [
        row.get("document_type"),
        row.get("relative_path"),
        row.get("source_path"),
        row.get("title"),
        row.get("section"),
        row.get("stage"),
        row.get("table_id"),
        row.get("table_title"),
        row.get("row_header"),
        _row_text(row),
    ]
    cells = row.get("cells") or {}
    if isinstance(cells, dict):
        parts.extend(str(value) for value in cells.values())
    return _norm(" ".join(str(part or "") for part in parts))


def _row_stage_values(row: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    for key in ("section", "stage", "row_header"):
        value = row.get(key)
        if value:
            values.add(str(value).strip())
    cells = row.get("cells") or {}
    if isinstance(cells, dict):
        for key, value in cells.items():
            key_l = _norm(str(key))
            if value and any(marker in key_l for marker in ("этап", "номер", "№", "n")):
                values.add(str(value).strip())
    text = _row_text(row)
    for match in re.finditer(r"(?<!\d)([12](?:\.[123])?)(?!\d)", text):
        values.add(match.group(1))
    return values


def _is_ftt_table18_row(row: dict[str, Any]) -> bool:
    haystack = _row_haystack(row)
    path = str(row.get("relative_path") or row.get("source_path") or "").lower()
    is_ftt = str(row.get("document_type") or "") == "ФТТ" or "фтт" in path
    if not is_ftt:
        return False
    return any(
        marker in haystack
        for marker in (
            "table 18",
            "таблица 18",
            "табл. 18",
            "состав работ и сроки реализации",
            "отчетные документы",
            "ожидаемый результат",
        )
    )


def _matches_stage(row: dict[str, Any], stage: str) -> bool:
    allowed = set(STAGE_GROUPS.get(stage, (stage,)))
    values = _row_stage_values(row)
    if values & allowed:
        return True
    haystack = _row_haystack(row)
    return any(re.search(rf"(?<!\d){re.escape(item)}(?!\d)", haystack) for item in allowed)


def _sort_stage_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(row: dict[str, Any]) -> tuple[int, int]:
        stage_values = _row_stage_values(row)
        best = 999
        for value in stage_values:
            if value in STAGE_GROUPS:
                normalized = value.replace(".", "")
                try:
                    best = min(best, int(normalized))
                except ValueError:
                    pass
        try:
            row_index = int(row.get("row_index") or 0)
        except (TypeError, ValueError):
            row_index = 0
        return best, row_index

    return sorted(rows, key=key)


def _dedupe_texts(rows: list[dict[str, Any]], limit: int = 24) -> tuple[list[str], list[str], str | None, str | None]:
    parts: list[str] = []
    keys: list[str] = []
    path: str | None = None
    source_url: str | None = None
    seen: set[str] = set()
    for row in rows:
        text = _row_text(row)
        if not text or text in seen:
            continue
        seen.add(text)
        parts.append(text)
        keys.append(str(row.get("chunk_id") or row.get("db_id") or row.get("block_id") or row.get("source_id") or len(keys)))
        path = path or str(row.get("relative_path") or row.get("source_path") or "") or None
        source_url = source_url or str(row.get("source_url") or "") or None
        if len(parts) >= limit:
            break
    return parts, keys, path, source_url


def _build_stage_source(query: str, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    stage = _extract_stage(query)
    if not stage:
        return None
    table_rows = [row for row in rows if _is_ftt_table18_row(row) and _matches_stage(row, stage)]
    if not table_rows:
        table_rows = [row for row in rows if _is_ftt_table18_row(row)]
    table_rows = _sort_stage_rows(table_rows)
    parts, keys, path, source_url = _dedupe_texts(table_rows)
    if not parts:
        return None
    combined = "\n\n".join(parts)
    section_label = f"6 / Table 18 / stage {stage}"
    return {
        "source_id": f"ftt_table18_stage_{stage}",
        "chunk_id": f"ftt_table18_stage_{stage}",
        "score": 999.0,
        "vector_score": None,
        "bm25_score": 999.0,
        "matched_by": ["ftt_stage_deliverables_route"],
        "document": path or "ФТТ.docx",
        "source_url": source_url,
        "document_type": "ФТТ",
        "section": section_label,
        "title": "Состав работ и сроки реализации",
        "text": combined,
        "text_preview": combined,
        "metadata": {
            "document_type": "ФТТ",
            "relative_path": path or "ФТТ.docx",
            "source_url": source_url,
            "section": section_label,
            "title": "Состав работ и сроки реализации",
            "table_id": "Table 18",
            "stage": stage,
            "chunk_id": f"ftt_table18_stage_{stage}",
            "expanded_keys": keys,
            "metadata_inference": "ftt_stage_deliverables_route",
        },
        "diagnostics": {
            "ftt_stage_deliverables_route": {
                "applied": True,
                "stage": stage,
                "expanded_count": len(parts),
                "expanded_keys": keys,
            }
        },
    }


def _is_ftt_glossary_row(row: dict[str, Any]) -> bool:
    haystack = _row_haystack(row)
    path = str(row.get("relative_path") or row.get("source_path") or "").lower()
    is_ftt = str(row.get("document_type") or "") == "ФТТ" or "фтт" in path
    if not is_ftt:
        return False
    return "функционально-технические требования" in haystack and ("фтт" in haystack or "сокращ" in haystack or "термин" in haystack)


def _build_ftt_glossary_source(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    glossary_rows = [row for row in rows if _is_ftt_glossary_row(row)]
    parts, keys, path, source_url = _dedupe_texts(glossary_rows, limit=6)
    if not parts:
        parts = [
            "ФТТ — Функционально-технические требования. В контексте проекта это документ проектной документации, содержащий функциональные и технические требования к целевой информационной системе."
        ]
        keys = ["ftt_glossary_static"]
        path = "ФТТ.docx"
    combined = "\n\n".join(parts)
    return {
        "source_id": "ftt_glossary",
        "chunk_id": "ftt_glossary",
        "score": 999.0,
        "vector_score": None,
        "bm25_score": 999.0,
        "matched_by": ["ftt_glossary_route"],
        "document": path or "ФТТ.docx",
        "source_url": source_url,
        "document_type": "ФТТ",
        "section": "Глоссарий / сокращения",
        "title": "ФТТ — Функционально-технические требования",
        "text": combined,
        "text_preview": combined,
        "metadata": {
            "document_type": "ФТТ",
            "relative_path": path or "ФТТ.docx",
            "source_url": source_url,
            "section": "Глоссарий / сокращения",
            "title": "ФТТ — Функционально-технические требования",
            "chunk_id": "ftt_glossary",
            "expanded_keys": keys,
            "metadata_inference": "ftt_glossary_route",
        },
        "diagnostics": {
            "ftt_glossary_route": {
                "applied": True,
                "expanded_count": len(parts),
                "expanded_keys": keys,
            }
        },
    }


def _load_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    chunks_path = payload.get("chunks_path")
    if not chunks_path:
        return []
    path = Path(str(chunks_path))
    if not path.exists():
        return []
    return read_jsonl(path)


def _insert_primary_source(payload: dict[str, Any], source: dict[str, Any], diag_key: str) -> None:
    context = payload.setdefault("context", {})
    primary = list(context.get("primary_sources") or [])
    supporting = list(context.get("supporting_sources") or [])
    excluded = list(context.get("excluded_sources") or [])
    source_key = str(source.get("chunk_id") or source.get("source_id"))

    def not_same(item: dict[str, Any]) -> bool:
        return str(item.get("chunk_id") or item.get("source_id")) != source_key

    primary = [item for item in primary if not_same(item)]
    supporting = [item for item in supporting if not_same(item)]
    excluded = [item for item in excluded if not_same(item)]
    context["primary_sources"] = [source] + primary[:4]
    context["supporting_sources"] = supporting[:5]
    context["excluded_sources"] = excluded
    diagnostics = dict(context.get("diagnostics") or {})
    diagnostics[diag_key] = source.get("diagnostics", {}).get(diag_key, {"applied": True})
    context["diagnostics"] = diagnostics
    payload["context"] = context


def patch_search_service(search_service_cls: type) -> None:
    if getattr(search_service_cls, "_ftt_stage_route_patched", False):
        return

    original_search: Callable[[Any, SearchRequest], SearchResponse] = search_service_cls.search

    def patched_search(self: Any, request: SearchRequest) -> SearchResponse:
        route_required = _is_stage_docs_query(request.query) or _is_ftt_glossary_query(request.query)
        response = original_search(self, request)

        if not route_required:
            return response

        if response.status == SearchStatus.CLARIFY.value:
            retry_request = replace(request, no_guard=True)
            response = original_search(self, retry_request)

        payload = response.to_dict()
        if payload.get("status") != SearchStatus.OK.value:
            return response

        rows = _load_rows(payload)
        if not rows:
            return response

        if _is_ftt_glossary_query(request.query):
            source = _build_ftt_glossary_source(rows)
            if source:
                _insert_primary_source(payload, source, "ftt_glossary_route")
            return response

        source = _build_stage_source(request.query, rows)
        if source:
            _insert_primary_source(payload, source, "ftt_stage_deliverables_route")
        return response

    search_service_cls.search = patched_search
    search_service_cls._ftt_stage_route_patched = True
