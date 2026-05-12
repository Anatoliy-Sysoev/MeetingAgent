from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


WORK_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = WORK_ROOT / "scripts"
SRC_DIR = WORK_ROOT / "src"
for path in (SCRIPTS_DIR, SRC_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from rag_common import jsonl_read, jsonl_write, load_config, normalize_text, resolve_work_path, stable_id  # noqa: E402
from asu_june_bot.retrieval.metadata import enrich_metadata  # noqa: E402


CHUNKER_VERSION = "v2"
PROJECT_NAME = "ЦП УПКС"
SECTION_RE = re.compile(r"(?<!\d)(\d+(?:\.\d+){1,5})\s*\.", re.UNICODE)
TABLE_RE = re.compile(r"^\[Table\s+(\d+)\]\s*$", re.IGNORECASE)
HEADING_RE = re.compile(r"^(?:#{1,6}\s+)?((?:\d+(?:\.\d+){0,5})?\s*[А-ЯA-ZЁ][^\n]{3,180})$")
MAX_PARENT_CHARS = 7000
MIN_PARENT_CHARS = 700
TEXT_CHILD_MAX_CHARS = 2500


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def text_hash(text: str) -> str:
    return stable_id(normalize_text(text), length=32)


def detect_requirement_id(text: str) -> str | None:
    match = SECTION_RE.search(text[:1200])
    if not match:
        return None
    return match.group(1)


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


def normalize_doc_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return normalize_text(text)


def split_table_blocks(text: str) -> tuple[list[dict[str, Any]], str]:
    """Extract table blocks from text and return non-table text with tables removed."""
    lines = text.splitlines()
    tables: list[dict[str, Any]] = []
    non_table_lines: list[str] = []
    i = 0
    while i < len(lines):
        match = TABLE_RE.match(lines[i].strip())
        if not match:
            non_table_lines.append(lines[i])
            i += 1
            continue

        table_id = f"Table {match.group(1)}"
        i += 1
        table_lines: list[str] = []
        while i < len(lines):
            line = lines[i]
            if TABLE_RE.match(line.strip()):
                break
            # Extracted text has headings like '# document'. Keep table until a new table marker; headings can appear inside Word text.
            if line.strip():
                table_lines.append(line)
            i += 1
        if table_lines:
            tables.append({"table_id": table_id, "lines": table_lines})
    return tables, "\n".join(non_table_lines)


def rows_from_table_lines(lines: list[str]) -> tuple[str | None, list[tuple[int, str]]]:
    cleaned = [line.strip() for line in lines if line.strip()]
    pipe_rows = [line for line in cleaned if "|" in line]
    if not pipe_rows:
        return None, list(enumerate(cleaned, start=1))
    header = pipe_rows[0]
    rows = [(idx, row) for idx, row in enumerate(pipe_rows[1:] or pipe_rows, start=1) if row.strip()]
    return header, rows


def split_text_parents(text: str) -> list[dict[str, Any]]:
    paragraphs = [part.strip() for part in re.split(r"\n{2,}", text) if part.strip()]
    parents: list[dict[str, Any]] = []
    current_title: str | None = None
    current_parts: list[str] = []

    def flush() -> None:
        nonlocal current_parts, current_title
        joined = "\n\n".join(current_parts).strip()
        if joined:
            parents.append({"title": current_title, "text": joined})
        current_parts = []

    for para in paragraphs:
        is_heading = bool(HEADING_RE.match(para)) and len(para) < 220 and " | " not in para
        current_len = len("\n\n".join(current_parts))
        if is_heading and current_parts and current_len >= MIN_PARENT_CHARS:
            flush()
            current_title = para.lstrip("# ").strip()
            current_parts.append(para)
            continue
        if current_parts and current_len + len(para) > MAX_PARENT_CHARS:
            flush()
        if is_heading and not current_parts:
            current_title = para.lstrip("# ").strip()
        current_parts.append(para)
    flush()
    return parents


def split_text_children(parent_text: str) -> list[str]:
    """Split parent text into numbered child chunks when possible, otherwise by size."""
    matches = list(SECTION_RE.finditer(parent_text))
    if len(matches) >= 2:
        chunks: list[str] = []
        for idx, match in enumerate(matches):
            start = match.start()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(parent_text)
            piece = parent_text[start:end].strip()
            if piece and len(piece) >= 80:
                chunks.append(piece)
        if chunks:
            return chunks

    if len(parent_text) <= TEXT_CHILD_MAX_CHARS:
        return [parent_text]

    paragraphs = [part.strip() for part in re.split(r"\n{2,}", parent_text) if part.strip()]
    chunks: list[str] = []
    current: list[str] = []
    for para in paragraphs:
        current_text = "\n\n".join(current)
        if current and len(current_text) + len(para) > TEXT_CHILD_MAX_CHARS:
            chunks.append(current_text)
            current = []
        current.append(para)
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def build_chunk(
    *,
    meta: dict[str, Any],
    text: str,
    chunk_level: str,
    chunk_index: int,
    parent_chunk_id: str | None = None,
    table_id: str | None = None,
    row_id: str | None = None,
    row_header: str | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    clean_text = normalize_doc_text(text)
    enriched = enrich_metadata(
        {
            "source_path": meta["source_path"],
            "relative_path": meta["relative_path"],
            "extension": meta["extension"],
            "sha256": meta["sha256"],
            "mtime": meta["mtime"],
        },
        clean_text,
    )
    requirement_id = detect_requirement_id(clean_text)
    integrations = detect_integration_terms(clean_text)
    chunk_id = stable_id(
        f"v2:{meta['sha256']}:{chunk_level}:{chunk_index}:{table_id or ''}:{row_id or ''}:{clean_text[:180]}",
        length=32,
    )
    return {
        "chunk_id": chunk_id,
        "db_id": stable_id(f"{meta['relative_path']}:{chunk_id}", length=32),
        "chunker_version": CHUNKER_VERSION,
        "chunk_level": chunk_level,
        "parent_chunk_id": parent_chunk_id,
        "project": PROJECT_NAME,
        "document_name": Path(meta["relative_path"]).name,
        "document_type": enriched.get("document_type"),
        "document_version": None,
        "source_type": enriched.get("source_type"),
        "source_path": meta["source_path"],
        "relative_path": meta["relative_path"],
        "source_url": None,
        "extension": meta["extension"],
        "sha256": meta["sha256"],
        "mtime": meta["mtime"],
        "stage": enriched.get("stage"),
        "module": enriched.get("module"),
        "section": enriched.get("section"),
        "sections": enriched.get("sections") or [],
        "requirement_id": requirement_id,
        "scenario_id": None,
        "table_id": table_id,
        "table_title": None,
        "row_id": row_id,
        "row_header": row_header,
        "source_system": integrations.get("source_system"),
        "target_system": integrations.get("target_system"),
        "integration": integrations.get("integration"),
        "protocol": integrations.get("protocol"),
        "title": title or enriched.get("title"),
        "text": clean_text,
        "text_hash": text_hash(clean_text),
        "chars": len(clean_text),
        "chunk_index": chunk_index,
        "created_at": utc_now(),
    }


def build_chunks_for_document(meta: dict[str, Any], text: str) -> list[dict[str, Any]]:
    text = normalize_doc_text(text)
    chunks: list[dict[str, Any]] = []
    chunk_index = 0

    tables, non_table_text = split_table_blocks(text)

    for parent in split_text_parents(non_table_text):
        parent_chunk = build_chunk(
            meta=meta,
            text=parent["text"],
            chunk_level="parent",
            chunk_index=chunk_index,
            title=parent.get("title"),
        )
        chunks.append(parent_chunk)
        chunk_index += 1
        for child_text in split_text_children(parent["text"]):
            if normalize_doc_text(child_text) == parent_chunk["text"]:
                continue
            child_chunk = build_chunk(
                meta=meta,
                text=child_text,
                chunk_level="child",
                chunk_index=chunk_index,
                parent_chunk_id=parent_chunk["chunk_id"],
                title=parent.get("title"),
            )
            chunks.append(child_chunk)
            chunk_index += 1

    for table in tables:
        table_id = table["table_id"]
        header, rows = rows_from_table_lines(table["lines"])
        table_parent_text = f"Документ: {meta['relative_path']}\nТаблица: {table_id}\n"
        if header:
            table_parent_text += f"Заголовки: {header}\n"
        table_parent_text += "\n".join(row for _, row in rows[:80])
        parent_chunk = build_chunk(
            meta=meta,
            text=table_parent_text,
            chunk_level="parent",
            chunk_index=chunk_index,
            table_id=table_id,
            row_header=header,
            title=table_id,
        )
        chunks.append(parent_chunk)
        chunk_index += 1

        for row_number, row_text in rows:
            child_text = "\n".join(
                line
                for line in (
                    f"Документ: {meta['relative_path']}",
                    f"Таблица: {table_id}",
                    f"Заголовки: {header}" if header else None,
                    f"Строка {row_number}: {row_text}",
                )
                if line
            )
            child_chunk = build_chunk(
                meta=meta,
                text=child_text,
                chunk_level="child",
                chunk_index=chunk_index,
                parent_chunk_id=parent_chunk["chunk_id"],
                table_id=table_id,
                row_id=str(row_number),
                row_header=header,
                title=table_id,
            )
            chunks.append(child_chunk)
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
    lines.extend(["", "## Errors", ""])
    if report["errors"]:
        for item in report["errors"][:50]:
            lines.append(f"- {item['relative_path']}: {item['error']}")
    else:
        lines.append("- no errors")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_report(chunks: list[dict[str, Any]], errors: list[dict[str, Any]], source_count: int, dry_run: bool) -> dict[str, Any]:
    by_doc_type = Counter(str(chunk.get("document_type") or "unknown") for chunk in chunks)
    by_level = Counter(str(chunk.get("chunk_level") or "unknown") for chunk in chunks)
    by_source_type = Counter(str(chunk.get("source_type") or "unknown") for chunk in chunks)
    return {
        "generated_at": utc_now(),
        "chunker_version": CHUNKER_VERSION,
        "dry_run": dry_run,
        "summary": {
            "sources_processed": source_count,
            "chunks_total": len(chunks),
            "parent_chunks": by_level.get("parent", 0),
            "child_chunks": by_level.get("child", 0),
            "table_child_chunks": len([chunk for chunk in chunks if chunk.get("chunk_level") == "child" and chunk.get("table_id")]),
            "chunks_with_requirement_id": len([chunk for chunk in chunks if chunk.get("requirement_id")]),
            "chunks_with_integration": len([chunk for chunk in chunks if chunk.get("integration")]),
            "errors": len(errors),
        },
        "by_document_type": dict(by_doc_type),
        "by_chunk_level": dict(by_level),
        "by_source_type": dict(by_source_type),
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Asu June Bot chunks v2 without touching legacy RAG index")
    parser.add_argument("--dry-run", action="store_true", help="Do not write chunks/report files")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of source documents")
    parser.add_argument("--path-contains", default=None, help="Process only sources whose relative_path contains this substring")
    parser.add_argument("--output-dir", default="data/asu_june_bot", help="Output directory for v2 chunks and reports")
    args = parser.parse_args()

    cfg = load_config()
    extracted_dir = resolve_work_path(cfg, cfg["paths"]["extracted_text_dir"])
    metadata_path = extracted_dir / "_metadata.jsonl"
    output_dir = resolve_work_path(cfg, args.output_dir)
    chunks_path = output_dir / "chunks_v2.jsonl"
    report_json_path = output_dir / "chunking_v2_report.json"
    report_md_path = output_dir / "chunking_v2_report.md"

    rows = [row for row in jsonl_read(metadata_path) if not row.get("error")]
    if args.path_contains:
        needle = args.path_contains.lower()
        rows = [row for row in rows if needle in str(row.get("relative_path", "")).lower()]
    if args.limit and args.limit > 0:
        rows = rows[: args.limit]

    chunks: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for row in rows:
        try:
            extracted_path = Path(row["extracted_path"])
            if not extracted_path.exists():
                raise FileNotFoundError(str(extracted_path))
            text = extracted_path.read_text(encoding="utf-8", errors="replace")
            chunks.extend(build_chunks_for_document(row, text))
        except Exception as exc:  # noqa: BLE001 - build should continue per document.
            errors.append({"relative_path": row.get("relative_path"), "error": repr(exc)})

    report = build_report(chunks, errors, source_count=len(rows), dry_run=args.dry_run)

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
