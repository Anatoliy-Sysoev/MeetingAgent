from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


WORK_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = WORK_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from asu_june_bot.core.config import load_config, resolve_work_path  # noqa: E402
from asu_june_bot.ingestion.utils import (  # noqa: E402
    is_office_temp_file,
    relative_to_project,
    should_skip_path,
)


DEFAULT_OUTPUT_DIR = "data/asu_june_bot"


def read_jsonl_if_exists(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def size_mb(paths: list[Path]) -> float:
    total = 0
    for path in paths:
        try:
            total += path.stat().st_size
        except OSError:
            continue
    return round(total / 1024 / 1024, 3)


def group_size_by_extension(paths: list[Path]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Path]] = defaultdict(list)
    for path in paths:
        grouped[path.suffix.lower() or "[no_ext]"].append(path)
    rows: list[dict[str, Any]] = []
    for ext, ext_paths in grouped.items():
        rows.append({"extension": ext, "count": len(ext_paths), "size_mb": size_mb(ext_paths)})
    return sorted(rows, key=lambda row: (row["size_mb"], row["count"]), reverse=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit Asu June Bot v2 source coverage")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Output directory for audit report")
    parser.add_argument("--json", action="store_true", help="Print full JSON report")
    args = parser.parse_args()

    cfg = load_config()
    project_root = Path(os.path.expandvars(str(cfg.get("project_root", WORK_ROOT)))).resolve()
    output_dir = resolve_work_path(cfg, args.output_dir)
    extracted_dir = output_dir / "extracted_v2"
    documents_path = extracted_dir / "documents.jsonl"
    blocks_path = extracted_dir / "blocks.jsonl"
    chunks_path = output_dir / "chunks_v2.jsonl"
    report_path = output_dir / "source_audit_v2_report.json"

    include_extensions = {str(item).lower() for item in cfg.get("include_extensions", [])}
    exclude_dirs = {str(item).lower() for item in cfg.get("exclude_dirs", [])}
    exclude_extensions = {str(item).lower() for item in cfg.get("exclude_extensions", [])}
    exclude_path_patterns = [str(item) for item in cfg.get("exclude_path_patterns", [])]

    all_files: list[Path] = []
    read_errors: list[dict[str, str]] = []
    try:
        iterator = project_root.rglob("*")
        for path in iterator:
            try:
                if path.is_file():
                    all_files.append(path)
            except OSError as exc:
                read_errors.append({"path": str(path), "error": repr(exc)})
    except OSError as exc:
        read_errors.append({"path": str(project_root), "error": repr(exc)})

    included: list[Path] = []
    excluded_by_reason: dict[str, list[Path]] = defaultdict(list)
    for path in all_files:
        ext = path.suffix.lower()
        rel = None
        try:
            rel = path.relative_to(project_root).as_posix()
        except ValueError:
            rel = path.as_posix()

        if is_office_temp_file(path):
            excluded_by_reason["office_temp_file"].append(path)
            continue
        if ext not in include_extensions:
            excluded_by_reason["extension_not_in_config"].append(path)
            continue
        if ext in exclude_extensions:
            excluded_by_reason["extension_excluded"].append(path)
            continue
        parts = {part.lower() for part in path.parts}
        if any(excluded.lower() in parts for excluded in exclude_dirs):
            excluded_by_reason["directory_excluded"].append(path)
            continue
        skipped_by_pattern = False
        from fnmatch import fnmatch
        for pattern in exclude_path_patterns:
            if fnmatch(rel, pattern) or fnmatch("/" + rel, pattern):
                skipped_by_pattern = True
                break
        if skipped_by_pattern:
            excluded_by_reason["path_pattern_excluded"].append(path)
            continue
        if should_skip_path(path, project_root, include_extensions, exclude_dirs, exclude_extensions, exclude_path_patterns):
            excluded_by_reason["other_skip_policy"].append(path)
            continue
        included.append(path)

    documents = read_jsonl_if_exists(documents_path)
    blocks = read_jsonl_if_exists(blocks_path)
    chunks = read_jsonl_if_exists(chunks_path)
    extracted_source_ids = {str(row.get("source_id")) for row in documents if row.get("source_id")}
    extracted_rel_paths = {str(row.get("relative_path")) for row in documents if row.get("relative_path")}
    block_source_ids = {str(row.get("source_id")) for row in blocks if row.get("source_id")}
    included_rel_paths = {relative_to_project(cfg, path) for path in included}
    included_not_extracted = sorted(included_rel_paths - extracted_rel_paths)
    extracted_not_included = sorted(extracted_rel_paths - included_rel_paths)

    report = {
        "project_root": str(project_root),
        "config": {
            "include_extensions": sorted(include_extensions),
            "exclude_extensions": sorted(exclude_extensions),
            "exclude_dirs": sorted(exclude_dirs),
            "exclude_path_patterns": exclude_path_patterns,
        },
        "summary": {
            "all_files_seen": len(all_files),
            "all_files_size_mb": size_mb(all_files),
            "included_by_config": len(included),
            "included_size_mb": size_mb(included),
            "documents_jsonl": len(documents),
            "blocks_jsonl": len(blocks),
            "chunks_jsonl": len(chunks),
            "sources_with_blocks": len(block_source_ids),
            "included_not_extracted": len(included_not_extracted),
            "extracted_not_currently_included": len(extracted_not_included),
            "read_errors": len(read_errors),
        },
        "by_extension_all_files": group_size_by_extension(all_files),
        "by_extension_included": group_size_by_extension(included),
        "excluded_by_reason": {
            reason: {
                "count": len(paths),
                "size_mb": size_mb(paths),
                "by_extension": group_size_by_extension(paths),
                "sample": [relative_to_project(cfg, path) for path in paths[:30]],
            }
            for reason, paths in sorted(excluded_by_reason.items())
        },
        "included_not_extracted_sample": included_not_extracted[:100],
        "extracted_not_currently_included_sample": extracted_not_included[:100],
        "read_errors": read_errors[:100],
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(json.dumps({"report_path": str(report_path), "summary": report["summary"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
