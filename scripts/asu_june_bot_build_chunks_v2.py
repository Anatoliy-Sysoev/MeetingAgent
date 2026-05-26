from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


WORK_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = WORK_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from asu_june_bot.core.config import load_config, resolve_work_path  # noqa: E402
from asu_june_bot.ingestion.utils import jsonl_write, normalize_text, stable_id, text_hash  # noqa: E402
from asu_june_bot.retrieval.metadata import enrich_metadata  # noqa: E402


CHUNKER_VERSION = "v2"
PROJECT_NAME = "ЦП УПКС"
SECTION_RE = re.compile(r"(?<!\d)(\d+(?:\.\d+){1,5})\s*\.", re.UNICODE)
TEXT_CHILD_MAX_CHARS = 2500
TABLE_ROW_MAX_CHARS = 2000
SOURCE_PARENT_MAX_CHARS = 6000
MAX_STORED_HEADERS = 120
MAX_STORED_CELLS = 120
MAX_ROW_HEADER_CHARS = 1200
NOISE_TEXT_RE = re.compile(r"^[\s{}\[\],.;:…._\\/-]+$|^(end|окончание|далее)\.?$", re.IGNORECASE)
MEANINGFUL_TEXT_RE = re.compile(r"[А-Яа-яA-Za-z0-9]{2,}", re.UNICODE)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"JSONL file not found: {path}")
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def detect_requirement_id(text: str, sections: list[str] | None = None) -> str | None:
    if sections:
        return str(sections[0])
    match = SECTION_RE.search(text[:1200])
    if not match:
        return None
    return match.group(1)


def detect_scenario_id(text: str) -> str | None:
    match = re.search(r"\b(СФТ|СНТ)\s*[-№#]?[\s]*(\d+(?:\.\d+)?)", text, flags=re.IGNORECASE)
    if not match:
        return None
    return f"{match.group(1).upper()} {match.group(2)}"


def detect_integration_terms(text: str) -> dict[str, str | None]:
    lowered = text.lower()
    integration = None
    protocol = None
    source_system = None
    target_system = None

    if "active directory" in lowered or re.search(r"\bad\b", lowered):
        integration = "Active Directory"
        source_system = "AD"
        target_system = "ЦП УПКС"
    if "ldaps" in lowered:
        protocol = "LDAPS"
    elif "ldap" in lowered:
        protocol = "LDAP"
    if "mdr" in lowered or "кшд" in lowered or "сои" in lowered:
        integration = integration or "MDR / КШД / СОИ"
        source_system = source_system or "MDR / КШД / СОИ"
        target_system = target_system or "ЦП УПКС"
    if "blitz" in lowered:
        integration = integration or "Blitz IDP"
        source_system = source_system or "Blitz IDP"
        target_system = target_system or "ЦП УПКС"
    if "smtp" in lowered or "exchange" in lowered or "почтов" in lowered:
        integration = integration or "SMTP / Exchange"
        protocol = protocol or ("SMTP" if "smtp" in lowered else None)
    if "новадок" in lowered:
        integration = integration or "НОВАДОК"
        target_system = target_system or "НОВАДОК"
    if "1с" in lowered or "основа" in lowered:
        integration = integration or "1С ОСНОВА"
        target_system = target_system or "1С ОСНОВА"

    return {
        "integration": integration,
        "protocol": protocol,
        "source_system": source_system,
        "target_system": target_system,
    }


def block_text(block: dict[str, Any]) -> str:
    text = normalize_text(block.get("text") or "")
    block_type = str(block.get("block_type") or "")
    if block_type == "table_row":
        cells = block.get("cells") or {}
        cell_lines = [
            f"{key}: {value}"
            for key, value in cells.items()
            if normalize_text(value)
        ]
        row_text = "\n".join(cell_lines) if cell_lines else text
        prefix = [
            f"Документ: {block.get('relative_path')}",
            f"Таблица: {block.get('table_id') or ''}".strip(),
            f"Лист: {block.get('sheet')}" if block.get("sheet") else "",
            f"Строка: {block.get('row_id') or block.get('row_index') or ''}".strip(),
        ]
        return normalize_text("\n".join([item for item in prefix if item]) + "\n" + row_text)
    if block_type in {"table", "sheet"}:
        headers = compact_headers(block.get("headers") or [])
        header_text = " | ".join(str(item) for item in headers)
        prefix = [
            f"Документ: {block.get('relative_path')}",
            f"Таблица: {block.get('table_id')}" if block.get("table_id") else "",
            f"Лист: {block.get('sheet')}" if block.get("sheet") else "",
            f"Заголовки: {header_text}" if header_text else "",
        ]
        cleaned_lines = [
            line
            for line in text.splitlines()
            if not line.strip().lower().startswith(("лист:", "заголовки:", "таблица "))
        ]
        payload = normalize_text("\n".join(cleaned_lines))
        if len(payload) > SOURCE_PARENT_MAX_CHARS:
            payload = ""
        return normalize_text("\n".join([item for item in prefix if item]) + ("\n" + payload if payload else ""))
    return text


def split_long_text(text: str, max_chars: int = TEXT_CHILD_MAX_CHARS) -> list[str]:
    text = normalize_text(text)
    if not text or len(text) <= max_chars:
        return [text] if text else []
    paragraphs = [part.strip() for part in re.split(r"\n{2,}", text) if part.strip()]
    if not paragraphs:
        return [text[:max_chars]]
    chunks: list[str] = []
    current: list[str] = []
    for para in paragraphs:
        if len(para) > max_chars:
            if current:
                chunks.append("\n\n".join(current))
                current = []
            for start in range(0, len(para), max_chars):
                piece = para[start : start + max_chars].strip()
                if piece:
                    chunks.append(piece)
            continue
        current_text = "\n\n".join(current)
        if current and len(current_text) + len(para) > max_chars:
            chunks.append(current_text)
            current = []
        current.append(para)
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def is_noise_text(text: str) -> bool:
    clean = normalize_text(text)
    if not clean:
        return True
    if len(clean) <= 3:
        return True
    if len(clean) < 50 and NOISE_TEXT_RE.fullmatch(clean) and not MEANINGFUL_TEXT_RE.search(clean):
        return True
    return False


def compact_headers(headers: list[Any]) -> list[str]:
    return [str(item) for item in headers[:MAX_STORED_HEADERS]]


def compact_cells(cells: dict[str, Any]) -> dict[str, str]:
    compact: dict[str, str] = {}
    for key, value in cells.items():
        clean_value = normalize_text(value)
        if not clean_value:
            continue
        compact[str(key)] = clean_value
        if len(compact) >= MAX_STORED_CELLS:
            break
    return compact


def compact_row_header(headers: list[Any]) -> str | None:
    row_header = " | ".join(compact_headers(headers))
    return row_header[:MAX_ROW_HEADER_CHARS] if row_header else None


def append_chunk(chunks: list[dict[str, Any]], chunk: dict[str, Any]) -> bool:
    if is_noise_text(str(chunk.get("text") or "")):
        return False
    chunks.append(chunk)
    return True


def base_chunk_metadata(block: dict[str, Any], text: str) -> dict[str, Any]:
    enriched = enrich_metadata(
        {
            "source_path": block.get("source_path"),
            "relative_path": block.get("relative_path"),
            "extension": block.get("extension"),
            "sha256": block.get("sha256"),
            "mtime": block.get("mtime"),
        },
        text,
    )
    sections = block.get("sections") or enriched.get("sections") or []
    section = block.get("section") or enriched.get("section") or (sections[0] if sections else None)
    integrations = detect_integration_terms(text)
    return {
        "project": PROJECT_NAME,
        "document_name": block.get("document_name") or Path(str(block.get("relative_path") or "")).name,
        "document_type": block.get("document_type") or enriched.get("document_type"),
        "document_version": None,
        "source_type": block.get("source_type") or enriched.get("source_type"),
        "source_path": block.get("source_path"),
        "relative_path": block.get("relative_path"),
        "source_url": block.get("source_url"),
        "extension": block.get("extension"),
        "sha256": block.get("sha256"),
        "mtime": block.get("mtime"),
        "stage": block.get("stage") or enriched.get("stage"),
        "module": block.get("module") or enriched.get("module"),
        "section": section,
        "sections": sections,
        "requirement_id": detect_requirement_id(text, sections),
        "scenario_id": detect_scenario_id(text),
        "source_system": integrations.get("source_system"),
        "target_system": integrations.get("target_system"),
        "integration": integrations.get("integration"),
        "protocol": integrations.get("protocol"),
    }


def make_chunk(
    *,
    block: dict[str, Any],
    text: str,
    chunk_index: int,
    chunk_level: str,
    parent_chunk_id: str | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    clean_text = normalize_text(text)
    meta = base_chunk_metadata(block, clean_text)
    table_id = block.get("table_id")
    row_id = block.get("row_id") or (str(block.get("row_index")) if block.get("row_index") is not None else None)
    chunk_id = stable_id(
        f"v2:{block.get('source_id')}:{block.get('block_id')}:{chunk_index}:{chunk_level}:{parent_chunk_id or ''}:{clean_text[:180]}",
        length=32,
    )
    return {
        "chunk_id": chunk_id,
        "db_id": stable_id(f"{meta.get('relative_path')}:{chunk_id}", length=32),
        "chunker_version": CHUNKER_VERSION,
        "chunk_level": chunk_level,
        "parent_chunk_id": parent_chunk_id,
        **meta,
        "block_id": block.get("block_id"),
        "block_type": block.get("block_type"),
        "block_index": block.get("block_index"),
        "page": block.get("page"),
        "slide": block.get("slide"),
        "sheet": block.get("sheet"),
        "paragraph_index": block.get("paragraph_index"),
        "heading_level": block.get("heading_level"),
        "style_name": block.get("style_name"),
        "table_id": table_id,
        "table_title": block.get("title"),
        "row_id": row_id,
        "row_header": compact_row_header(block.get("headers") or []),
        "row_index": block.get("row_index"),
        "headers": compact_headers(block.get("headers") or []),
        "cells": compact_cells(block.get("cells") or {}),
        "title": title or block.get("title") or block.get("parent_hint"),
        "text": clean_text,
        "text_hash": text_hash(clean_text),
        "chars": len(clean_text),
        "chunk_index": chunk_index,
        "created_at": utc_now(),
    }


def make_source_parent(blocks: list[dict[str, Any]], chunk_index: int) -> dict[str, Any] | None:
    if not blocks:
        return None
    first = blocks[0]
    parts: list[str] = []
    for block in blocks:
        if block.get("block_type") in {"heading", "paragraph", "page", "slide", "sheet", "table"}:
            text = block_text(block)
            if text:
                parts.append(text)
        if len("\n\n".join(parts)) >= SOURCE_PARENT_MAX_CHARS:
            break
    text = normalize_text("\n\n".join(parts))
    if not text:
        return None
    return make_chunk(
        block=first,
        text=text,
        chunk_index=chunk_index,
        chunk_level="parent",
        parent_chunk_id=None,
        title=Path(str(first.get("relative_path") or "")).name,
    )


def build_chunks_for_source(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blocks = sorted(blocks, key=lambda item: int(item.get("block_index") or 0))
    chunks: list[dict[str, Any]] = []
    chunk_index = 0
    current_parent_id: str | None = None
    current_table_parent_by_key: dict[str, str] = {}

    source_parent = make_source_parent(blocks, chunk_index)
    if source_parent:
        if append_chunk(chunks, source_parent):
            current_parent_id = source_parent["chunk_id"]
            chunk_index += 1

    for block in blocks:
        btype = str(block.get("block_type") or "")
        text = block_text(block)
        if not text:
            continue

        if btype in {"heading", "table", "sheet", "slide", "page"}:
            parent = make_chunk(
                block=block,
                text=text,
                chunk_index=chunk_index,
                chunk_level="parent",
                parent_chunk_id=source_parent["chunk_id"] if source_parent else None,
                title=block.get("title") or block.get("parent_hint"),
            )
            if not append_chunk(chunks, parent):
                chunk_index += 1
                continue
            current_parent_id = parent["chunk_id"]
            if btype in {"table", "sheet"}:
                table_key = f"{block.get('table_id') or ''}:{block.get('sheet') or ''}"
                current_table_parent_by_key[table_key] = parent["chunk_id"]
            chunk_index += 1
            continue

        if btype == "table_row":
            table_key = f"{block.get('table_id') or ''}:{block.get('sheet') or ''}"
            parent_id = current_table_parent_by_key.get(table_key) or current_parent_id
            for row_part_index, piece in enumerate(split_long_text(text, max_chars=TABLE_ROW_MAX_CHARS)):
                child = make_chunk(
                    block=block,
                    text=piece,
                    chunk_index=chunk_index,
                    chunk_level="child",
                    parent_chunk_id=parent_id,
                    title=block.get("title") or block.get("parent_hint"),
                )
                child["row_part_index"] = row_part_index if row_part_index else None
                append_chunk(chunks, child)
                chunk_index += 1
            continue

        for piece in split_long_text(text):
            child = make_chunk(
                block=block,
                text=piece,
                chunk_index=chunk_index,
                chunk_level="child",
                parent_chunk_id=current_parent_id,
                title=block.get("title") or block.get("parent_hint"),
            )
            append_chunk(chunks, child)
            chunk_index += 1

    return chunks


def write_report_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Chunking v2 Report",
        "",
        f"Generated: {report['generated_at']}",
        "",
        "## Summary",
        "",
    ]
    for key, value in report["summary"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## By Document Type", ""])
    for key, value in sorted(report["by_document_type"].items()):
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## By Chunk Level", ""])
    for key, value in sorted(report["by_chunk_level"].items()):
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## By Block Type", ""])
    for key, value in sorted(report["by_block_type"].items()):
        lines.append(f"- {key}: {value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_report(chunks: list[dict[str, Any]], source_count: int, block_count: int, dry_run: bool, blocks_path: str) -> dict[str, Any]:
    by_doc_type = Counter(str(chunk.get("document_type") or "unknown") for chunk in chunks)
    by_level = Counter(str(chunk.get("chunk_level") or "unknown") for chunk in chunks)
    by_source_type = Counter(str(chunk.get("source_type") or "unknown") for chunk in chunks)
    by_block_type = Counter(str(chunk.get("block_type") or "unknown") for chunk in chunks)
    return {
        "generated_at": utc_now(),
        "chunker_version": CHUNKER_VERSION,
        "dry_run": dry_run,
        "blocks_path": blocks_path,
        "summary": {
            "sources_processed": source_count,
            "blocks_processed": block_count,
            "chunks_total": len(chunks),
            "parent_chunks": by_level.get("parent", 0),
            "child_chunks": by_level.get("child", 0),
            "table_child_chunks": len([chunk for chunk in chunks if chunk.get("chunk_level") == "child" and chunk.get("table_id")]),
            "chunks_with_requirement_id": len([chunk for chunk in chunks if chunk.get("requirement_id")]),
            "chunks_with_integration": len([chunk for chunk in chunks if chunk.get("integration")]),
        },
        "by_document_type": dict(by_doc_type),
        "by_chunk_level": dict(by_level),
        "by_source_type": dict(by_source_type),
        "by_block_type": dict(by_block_type),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Asu June Bot chunks v2 from Asu June Bot extracted blocks v2")
    parser.add_argument("--dry-run", action="store_true", help="Do not write chunks/report files")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of source documents")
    parser.add_argument("--path-contains", default=None, help="Process only blocks whose relative_path contains this substring")
    parser.add_argument("--blocks-path", default="data/asu_june_bot/extracted_v2/blocks.jsonl", help="Input blocks.jsonl from extractor v2")
    parser.add_argument("--output-dir", default="data/asu_june_bot", help="Output directory for v2 chunks and reports")
    args = parser.parse_args()

    cfg = load_config()
    blocks_path = resolve_work_path(cfg, args.blocks_path)
    output_dir = resolve_work_path(cfg, args.output_dir)
    chunks_path = output_dir / "chunks_v2.jsonl"
    report_json_path = output_dir / "chunking_v2_report.json"
    report_md_path = output_dir / "chunking_v2_report.md"

    blocks = read_jsonl(blocks_path)
    if args.path_contains:
        needle = args.path_contains.lower()
        blocks = [block for block in blocks if needle in str(block.get("relative_path", "")).lower()]

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for block in blocks:
        grouped[str(block.get("source_id") or block.get("relative_path"))].append(block)

    source_items = list(grouped.items())
    if args.limit and args.limit > 0:
        source_items = source_items[: args.limit]

    chunks: list[dict[str, Any]] = []
    for _source_id, source_blocks in source_items:
        chunks.extend(build_chunks_for_source(source_blocks))

    report = build_report(
        chunks,
        source_count=len(source_items),
        block_count=sum(len(source_blocks) for _, source_blocks in source_items),
        dry_run=args.dry_run,
        blocks_path=str(blocks_path),
    )

    if not args.dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
        jsonl_write(chunks_path, chunks)
        report_json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        write_report_markdown(report_md_path, report)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.dry_run:
        print("Dry-run: no files written.")
    else:
        print(json.dumps({"chunks_path": str(chunks_path), "report_json": str(report_json_path), "report_md": str(report_md_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
