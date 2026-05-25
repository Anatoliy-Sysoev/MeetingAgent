from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable


WORK_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROJECT_ROOT = r"C:\Users\Сотрудник\Desktop\Yandex.Disk\Документы НТК Сдача"
DEFAULT_CLOUD_LINKS = r"C:\Users\Сотрудник\Desktop\yandex_disk_full_export\cloud_links_full.csv"
DEFAULT_OUTPUT = "data/asu_june_bot_ntk/source_links.jsonl"


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def normalize_relative_path(value: str) -> str:
    text = str(value or "").strip().strip('"').replace("\\", "/")
    text = text.removeprefix("./").lstrip("/")
    prefix = "disk:/Документы НТК Сдача/"
    if text.lower().startswith(prefix.lower()):
        text = text[len(prefix) :]
    return "/".join(part for part in text.split("/") if part)


def path_key(value: str) -> str:
    return normalize_relative_path(value).casefold()


def resolve_repo_path(raw: str | Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = WORK_ROOT / path
    return path.resolve()


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {path}")
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,")
    except csv.Error:
        dialect = csv.excel
        dialect.delimiter = ";"
    rows: list[dict[str, str]] = []
    for row in csv.DictReader(text.splitlines(), dialect=dialect):
        rows.append({str(k or "").strip(): str(v or "").strip() for k, v in row.items()})
    return rows


def cloud_url(row: dict[str, str]) -> str | None:
    for key in ("cloud_url", "public_url", "url", "href"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return None


def relative_from_cloud_row(row: dict[str, str]) -> str | None:
    for key in ("relative_path", "path", "file_path"):
        value = normalize_relative_path(row.get(key) or "")
        if value:
            return value
    value = normalize_relative_path(row.get("cloud_path") or "")
    return value or None


def load_cloud_links(path: Path) -> dict[str, dict[str, Any]]:
    links: dict[str, dict[str, Any]] = {}
    for row in read_csv_rows(path):
        rel = relative_from_cloud_row(row)
        url = cloud_url(row)
        if not rel or not url:
            continue
        links[path_key(rel)] = {
            "relative_path": rel,
            "source_url": url,
            "cloud_path": row.get("cloud_path") or None,
            "cloud_name": row.get("name") or Path(rel).name,
            "cloud_size_bytes": row.get("size_bytes") or None,
            "cloud_modified": row.get("modified") or None,
            "cloud_mime_type": row.get("mime_type") or None,
        }
    return links


def iter_local_files(project_root: Path) -> Iterable[Path]:
    for path in project_root.rglob("*"):
        if path.is_file():
            yield path


def build_source_links(project_root: Path, cloud_links_path: Path) -> tuple[list[dict[str, Any]], dict[str, int]]:
    cloud_links = load_cloud_links(cloud_links_path)
    rows: list[dict[str, Any]] = []
    matched = 0
    missing = 0
    for path in sorted(iter_local_files(project_root), key=lambda item: item.as_posix().casefold()):
        rel = path.resolve().relative_to(project_root).as_posix()
        link = cloud_links.get(path_key(rel))
        stat = path.stat()
        if link:
            matched += 1
        else:
            missing += 1
        rows.append(
            {
                "relative_path": rel,
                "source_url": link.get("source_url") if link else None,
                "cloud_path": link.get("cloud_path") if link else None,
                "cloud_name": link.get("cloud_name") if link else path.name,
                "cloud_modified": link.get("cloud_modified") if link else None,
                "cloud_mime_type": link.get("cloud_mime_type") if link else None,
                "local_path": str(path.resolve()),
                "local_size_bytes": stat.st_size,
                "local_mtime": stat.st_mtime,
            }
        )
    stats = {
        "local_files": len(rows),
        "cloud_links": len(cloud_links),
        "matched": matched,
        "missing_source_url": missing,
    }
    return rows, stats


def write_jsonl_atomic(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    count = 0
    with tmp_path.open("w", encoding="utf-8", newline="\n") as fp:
        for row in rows:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    os.replace(tmp_path, path)
    return count


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"JSONL not found: {path}")
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_source_link_map(path: Path) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(path):
        rel = normalize_relative_path(str(row.get("relative_path") or ""))
        if rel:
            mapping[path_key(rel)] = row
    return mapping


def apply_links_to_jsonl(jsonl_path: Path, source_links_path: Path) -> dict[str, Any]:
    links = load_source_link_map(source_links_path)
    rows = read_jsonl(jsonl_path)
    matched = 0
    missing = 0
    for row in rows:
        rel = normalize_relative_path(str(row.get("relative_path") or ""))
        link = links.get(path_key(rel))
        if link and link.get("source_url"):
            row["source_url"] = link.get("source_url")
            row["cloud_path"] = link.get("cloud_path")
            matched += 1
        else:
            row.setdefault("source_url", None)
            missing += 1
    write_jsonl_atomic(jsonl_path, rows)
    return {"path": str(jsonl_path), "rows": len(rows), "matched": matched, "missing_source_url": missing}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build/apply source_url mapping for the NTK Yandex corpus")
    parser.add_argument("--project-root", default=DEFAULT_PROJECT_ROOT)
    parser.add_argument("--cloud-links", default=DEFAULT_CLOUD_LINKS)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--apply-jsonl", action="append", default=[], help="JSONL file to enrich with source_url. Can be repeated.")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    if not project_root.exists():
        raise FileNotFoundError(f"Project root not found: {project_root}")
    cloud_links_path = Path(args.cloud_links).resolve()
    output_path = resolve_repo_path(args.output)

    rows, stats = build_source_links(project_root, cloud_links_path)
    written = write_jsonl_atomic(output_path, rows)

    applied = []
    for raw_path in args.apply_jsonl:
        applied.append(apply_links_to_jsonl(resolve_repo_path(raw_path), output_path))

    report = {
        "project_root": str(project_root),
        "cloud_links": str(cloud_links_path),
        "output": str(output_path),
        "written": written,
        "stats": stats,
        "applied": applied,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
