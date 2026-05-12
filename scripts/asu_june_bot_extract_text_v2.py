from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import fitz
import pandas as pd
from bs4 import BeautifulSoup
from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from pptx import Presentation


WORK_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = WORK_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from asu_june_bot.core.config import load_config, resolve_work_path  # noqa: E402
from asu_june_bot.ingestion.models import ExtractedBlock, SourceDocument  # noqa: E402
from asu_june_bot.ingestion.utils import (  # noqa: E402
    detect_heading_level,
    enrich_block_metadata,
    iter_source_files,
    jsonl_write,
    normalize_text,
    read_text_guess,
    relative_to_project,
    sha256_file,
    stable_id,
)


EXTRACTOR_VERSION = "v2"
DEFAULT_OUTPUT_DIR = "data/asu_june_bot/extracted_v2"
TEXT_EXTENSIONS = {".md", ".txt", ".json", ".yml", ".yaml", ".drawio", ".puml", ".srt", ".py", ".js", ".ts", ".css"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_source_document(cfg: dict[str, Any], path: Path) -> SourceDocument:
    relative_path = relative_to_project(cfg, path)
    sha = sha256_file(path)
    source_id = stable_id(f"source:{relative_path}:{sha}", length=32)
    probe_meta = enrich_block_metadata(relative_path, path.suffix.lower(), relative_path)
    stat = path.stat()
    return SourceDocument(
        source_id=source_id,
        source_path=str(path.resolve()),
        relative_path=relative_path,
        extension=path.suffix.lower(),
        sha256=sha,
        mtime=stat.st_mtime,
        size_bytes=stat.st_size,
        source_type=probe_meta.get("source_type"),
        document_type=probe_meta.get("document_type"),
        stage=probe_meta.get("stage"),
        module=probe_meta.get("module"),
    )


def make_block(
    *,
    source: SourceDocument,
    block_index: int,
    block_type: str,
    text: str,
    page: int | None = None,
    slide: int | None = None,
    sheet: str | None = None,
    paragraph_index: int | None = None,
    heading_level: int | None = None,
    style_name: str | None = None,
    table_index: int | None = None,
    row_index: int | None = None,
    headers: list[str] | None = None,
    cells: dict[str, str] | None = None,
    title: str | None = None,
    parent_hint: str | None = None,
) -> ExtractedBlock | None:
    clean = normalize_text(text)
    if not clean:
        return None
    enriched = enrich_block_metadata(source.relative_path, source.extension, clean)
    table_id = f"Table {table_index}" if table_index is not None else None
    row_id = str(row_index) if row_index is not None else None
    block_id = stable_id(
        f"block:{source.sha256}:{block_index}:{block_type}:{page or ''}:{slide or ''}:{sheet or ''}:{table_id or ''}:{row_id or ''}:{clean[:160]}",
        length=32,
    )
    return ExtractedBlock(
        block_id=block_id,
        source_id=source.source_id,
        block_index=block_index,
        block_type=block_type,
        text=clean,
        source_path=source.source_path,
        relative_path=source.relative_path,
        extension=source.extension,
        sha256=source.sha256,
        mtime=source.mtime,
        document_name=Path(source.relative_path).name,
        source_type=enriched.get("source_type"),
        document_type=enriched.get("document_type"),
        stage=enriched.get("stage"),
        module=enriched.get("module"),
        page=page,
        slide=slide,
        sheet=sheet,
        paragraph_index=paragraph_index,
        heading_level=heading_level,
        style_name=style_name,
        section=enriched.get("section"),
        sections=enriched.get("sections") or [],
        table_id=table_id,
        table_index=table_index,
        row_id=row_id,
        row_index=row_index,
        col_count=len(headers or []) if headers else (len(cells or {}) if cells else None),
        headers=headers or [],
        cells=cells or {},
        title=title,
        parent_hint=parent_hint,
    )


def iter_docx_blocks(document: Document) -> Iterable[Paragraph | Table]:
    body = document.element.body
    for child in body.iterchildren():
        if child.tag.endswith("}p"):
            yield Paragraph(child, document)
        elif child.tag.endswith("}tbl"):
            yield Table(child, document)


def table_row_values(table: Table, row_index: int) -> list[str]:
    row = table.rows[row_index]
    return [normalize_text(cell.text) for cell in row.cells]


def unique_headers(values: list[str]) -> list[str]:
    headers: list[str] = []
    seen: Counter[str] = Counter()
    for idx, value in enumerate(values, start=1):
        header = value.strip() or f"col_{idx}"
        seen[header] += 1
        if seen[header] > 1:
            header = f"{header}_{seen[header]}"
        headers.append(header)
    return headers


def extract_docx_v2(path: Path, source: SourceDocument) -> list[ExtractedBlock]:
    doc = Document(str(path))
    blocks: list[ExtractedBlock] = []
    block_index = 0
    paragraph_index = 0
    table_index = 0
    current_parent_hint: str | None = None

    for item in iter_docx_blocks(doc):
        if isinstance(item, Paragraph):
            paragraph_index += 1
            text = normalize_text(item.text)
            if not text:
                continue
            style_name = item.style.name if item.style is not None else None
            heading_level = detect_heading_level(style_name)
            if heading_level is not None:
                current_parent_hint = text
            block = make_block(
                source=source,
                block_index=block_index,
                block_type="heading" if heading_level is not None else "paragraph",
                text=text,
                paragraph_index=paragraph_index,
                heading_level=heading_level,
                style_name=style_name,
                title=text if heading_level is not None else None,
                parent_hint=current_parent_hint,
            )
            if block:
                blocks.append(block)
                block_index += 1
            continue

        if isinstance(item, Table):
            table_index += 1
            if not item.rows:
                continue
            raw_headers = table_row_values(item, 0)
            headers = unique_headers(raw_headers)
            table_title = current_parent_hint
            table_text_lines = [f"Таблица {table_index}"]
            if table_title:
                table_text_lines.append(f"Контекст: {table_title}")
            table_text_lines.append("Заголовки: " + " | ".join(headers))

            parent_block = make_block(
                source=source,
                block_index=block_index,
                block_type="table",
                text="\n".join(table_text_lines),
                table_index=table_index,
                headers=headers,
                title=table_title,
                parent_hint=current_parent_hint,
            )
            if parent_block:
                blocks.append(parent_block)
                block_index += 1

            start_row = 1 if len(item.rows) > 1 else 0
            for idx in range(start_row, len(item.rows)):
                values = table_row_values(item, idx)
                if not any(values):
                    continue
                cells = {headers[col_idx] if col_idx < len(headers) else f"col_{col_idx + 1}": value for col_idx, value in enumerate(values)}
                row_text = "\n".join(
                    [
                        f"Таблица {table_index}",
                        f"Контекст: {table_title}" if table_title else "",
                        "Заголовки: " + " | ".join(headers),
                        f"Строка {idx + 1}: " + " | ".join(values),
                    ]
                )
                block = make_block(
                    source=source,
                    block_index=block_index,
                    block_type="table_row",
                    text=row_text,
                    table_index=table_index,
                    row_index=idx + 1,
                    headers=headers,
                    cells=cells,
                    title=table_title,
                    parent_hint=current_parent_hint,
                )
                if block:
                    blocks.append(block)
                    block_index += 1
    return blocks


def extract_xlsx_v2(path: Path, source: SourceDocument) -> list[ExtractedBlock]:
    engine = "pyxlsb" if path.suffix.lower() == ".xlsb" else None
    sheets = pd.read_excel(path, sheet_name=None, dtype=str, engine=engine)
    blocks: list[ExtractedBlock] = []
    block_index = 0

    for sheet_name, df in sheets.items():
        df = df.fillna("")
        headers = [str(col).strip() or f"col_{idx + 1}" for idx, col in enumerate(df.columns)]
        sheet_text = f"Лист: {sheet_name}\nЗаголовки: " + " | ".join(headers)
        block = make_block(
            source=source,
            block_index=block_index,
            block_type="sheet",
            text=sheet_text,
            sheet=str(sheet_name),
            headers=headers,
            title=str(sheet_name),
        )
        if block:
            blocks.append(block)
            block_index += 1

        for row_zero_index, row in df.iterrows():
            values = [normalize_text(row.get(col, "")) for col in df.columns]
            if not any(values):
                continue
            cells = {headers[idx]: values[idx] if idx < len(values) else "" for idx in range(len(headers))}
            row_text = "\n".join(
                [
                    f"Лист: {sheet_name}",
                    "Заголовки: " + " | ".join(headers),
                    f"Строка {int(row_zero_index) + 2}: " + " | ".join(values),
                ]
            )
            block = make_block(
                source=source,
                block_index=block_index,
                block_type="table_row",
                text=row_text,
                sheet=str(sheet_name),
                row_index=int(row_zero_index) + 2,
                headers=headers,
                cells=cells,
                title=str(sheet_name),
                parent_hint=str(sheet_name),
            )
            if block:
                blocks.append(block)
                block_index += 1
    return blocks


def extract_pdf_v2(path: Path, source: SourceDocument) -> list[ExtractedBlock]:
    blocks: list[ExtractedBlock] = []
    block_index = 0
    with fitz.open(str(path)) as doc:
        for page_index, page in enumerate(doc, start=1):
            text = normalize_text(page.get_text("text"))
            block = make_block(
                source=source,
                block_index=block_index,
                block_type="page",
                text=text,
                page=page_index,
                title=f"page {page_index}",
            )
            if block:
                blocks.append(block)
                block_index += 1
    return blocks


def extract_pptx_v2(path: Path, source: SourceDocument) -> list[ExtractedBlock]:
    prs = Presentation(str(path))
    blocks: list[ExtractedBlock] = []
    block_index = 0
    for slide_index, slide in enumerate(prs.slides, start=1):
        slide_text_parts: list[str] = []
        shape_index = 0
        for shape in slide.shapes:
            if not hasattr(shape, "text"):
                continue
            text = normalize_text(shape.text)
            if not text:
                continue
            shape_index += 1
            slide_text_parts.append(text)
            block = make_block(
                source=source,
                block_index=block_index,
                block_type="shape_text",
                text=text,
                slide=slide_index,
                title=f"slide {slide_index} shape {shape_index}",
            )
            if block:
                blocks.append(block)
                block_index += 1
        if slide_text_parts:
            block = make_block(
                source=source,
                block_index=block_index,
                block_type="slide",
                text="\n".join(slide_text_parts),
                slide=slide_index,
                title=f"slide {slide_index}",
            )
            if block:
                blocks.append(block)
                block_index += 1
    return blocks


def extract_html_v2(path: Path, source: SourceDocument) -> list[ExtractedBlock]:
    soup = BeautifulSoup(read_text_guess(path), "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    blocks: list[ExtractedBlock] = []
    block_index = 0
    for tag in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "td", "th"]):
        text = normalize_text(tag.get_text(" "))
        if not text:
            continue
        heading_level = int(tag.name[1]) if tag.name.startswith("h") and tag.name[1:].isdigit() else None
        block = make_block(
            source=source,
            block_index=block_index,
            block_type="heading" if heading_level is not None else "html_text",
            text=text,
            heading_level=heading_level,
            title=text if heading_level is not None else None,
        )
        if block:
            blocks.append(block)
            block_index += 1
    if not blocks:
        text = normalize_text(soup.get_text("\n"))
        block = make_block(source=source, block_index=0, block_type="html", text=text)
        if block:
            blocks.append(block)
    return blocks


def extract_text_v2(path: Path, source: SourceDocument) -> list[ExtractedBlock]:
    text = read_text_guess(path)
    blocks: list[ExtractedBlock] = []
    block_index = 0
    parts = [part.strip() for part in text.split("\n\n") if part.strip()]
    if not parts:
        parts = [text]
    for part in parts:
        block = make_block(source=source, block_index=block_index, block_type="text", text=part)
        if block:
            blocks.append(block)
            block_index += 1
    return blocks


def extract_source(path: Path, source: SourceDocument) -> list[ExtractedBlock]:
    ext = path.suffix.lower()
    if ext == ".docx":
        return extract_docx_v2(path, source)
    if ext in {".xlsx", ".xlsb"}:
        return extract_xlsx_v2(path, source)
    if ext == ".pdf":
        return extract_pdf_v2(path, source)
    if ext == ".pptx":
        return extract_pptx_v2(path, source)
    if ext == ".html":
        return extract_html_v2(path, source)
    if ext in TEXT_EXTENSIONS:
        return extract_text_v2(path, source)
    return []


def write_report_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Asu June Bot Extraction v2 Report",
        "",
        f"Generated: {report['generated_at']}",
        "",
        "## Summary",
        "",
    ]
    for key, value in report["summary"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## By Extension", ""])
    for key, value in sorted(report["by_extension"].items()):
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## By Block Type", ""])
    for key, value in sorted(report["by_block_type"].items()):
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## By Document Type", ""])
    for key, value in sorted(report["by_document_type"].items()):
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Errors", ""])
    if report["errors"]:
        for item in report["errors"][:100]:
            lines.append(f"- {item['relative_path']}: {item['error']}")
    else:
        lines.append("- no errors")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_report(sources: list[SourceDocument], blocks: list[ExtractedBlock], errors: list[dict[str, Any]], dry_run: bool) -> dict[str, Any]:
    return {
        "generated_at": utc_now(),
        "extractor_version": EXTRACTOR_VERSION,
        "dry_run": dry_run,
        "summary": {
            "sources_total": len(sources),
            "blocks_total": len(blocks),
            "errors": len(errors),
            "docx_sources": len([src for src in sources if src.extension == ".docx"]),
            "xlsx_sources": len([src for src in sources if src.extension in {".xlsx", ".xlsb"}]),
            "pdf_sources": len([src for src in sources if src.extension == ".pdf"]),
            "blocks_with_section": len([block for block in blocks if block.section]),
            "table_row_blocks": len([block for block in blocks if block.block_type == "table_row"]),
        },
        "by_extension": dict(Counter(src.extension or "unknown" for src in sources)),
        "by_block_type": dict(Counter(block.block_type for block in blocks)),
        "by_document_type": dict(Counter(str(block.document_type or "unknown") for block in blocks)),
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Asu June Bot extractor v2: independent structured extraction pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Do not write output files")
    parser.add_argument("--limit", type=int, default=0, help="Limit source files")
    parser.add_argument("--path-contains", default=None, help="Process only source files whose relative path contains substring")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Output directory")
    args = parser.parse_args()

    cfg = load_config()
    output_dir = resolve_work_path(cfg, args.output_dir)
    blocks_path = output_dir / "blocks.jsonl"
    documents_path = output_dir / "documents.jsonl"
    report_json_path = output_dir / "extraction_v2_report.json"
    report_md_path = output_dir / "extraction_v2_report.md"

    paths = iter_source_files(cfg)
    if args.path_contains:
        needle = args.path_contains.lower()
        paths = [path for path in paths if needle in relative_to_project(cfg, path).lower()]
    if args.limit and args.limit > 0:
        paths = paths[: args.limit]

    sources: list[SourceDocument] = []
    blocks: list[ExtractedBlock] = []
    errors: list[dict[str, Any]] = []

    for path in paths:
        try:
            source = make_source_document(cfg, path)
            extracted = extract_source(path, source)
            if not extracted:
                continue
            sources.append(source)
            blocks.extend(extracted)
        except Exception as exc:  # noqa: BLE001 - extraction should continue per file.
            errors.append({"relative_path": relative_to_project(cfg, path), "error": repr(exc)})

    report = build_report(sources, blocks, errors, dry_run=args.dry_run)

    if not args.dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
        jsonl_write(documents_path, [source.to_dict() for source in sources])
        jsonl_write(blocks_path, [block.to_dict() for block in blocks])
        report_json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        write_report_markdown(report_md_path, report)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.dry_run:
        print("Dry-run: no files written.")
    else:
        print(
            json.dumps(
                {
                    "documents_path": str(documents_path),
                    "blocks_path": str(blocks_path),
                    "report_json": str(report_json_path),
                    "report_md": str(report_md_path),
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
