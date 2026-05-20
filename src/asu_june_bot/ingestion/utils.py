from __future__ import annotations

import hashlib
import os
import re
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Iterable

from asu_june_bot.core.config import WORK_ROOT
from asu_june_bot.core.hashing import stable_id as shared_stable_id
from asu_june_bot.core.jsonl import jsonl_write as shared_jsonl_write
from asu_june_bot.retrieval.metadata import enrich_metadata, infer_sections


SECTION_RE = re.compile(r"(?<!\d)(\d+(?:\.\d+){1,5})\s*\.", re.UNICODE)
OFFICE_TEMP_PREFIXES = ("~$", ".~")
TEMP_EXTENSIONS = {".tmp", ".temp"}
HARD_EXCLUDE_EXTENSIONS = {".har"}
HARD_EXCLUDE_DIRS = {
    "site_review_runs",
    "playwright",
    "exports",
    "html_export",
    "docs_html",
    "docs_text",
    "pages_html",
    "pages_text",
    "screenshots",
    "node_modules",
    "__pycache__",
    ".git",
    ".venv",
    "dist",
    "build",
}
HARD_EXCLUDE_PATH_FRAGMENTS = (
    "/система/",
    "/asu_docs_export/",
    "/asu_admin_export/",
    "/site_review_runs/",
    "/playwright/",
    "/docs_html/",
    "/docs_text/",
    "/pages_html/",
    "/pages_text/",
)


def normalize_text(text: str) -> str:
    text = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()


def stable_id(value: str, length: int = 32) -> str:
    return shared_stable_id(value, length=length)


def sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fp:
        while True:
            chunk = fp.read(block_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def read_text_guess(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8", "utf-8-sig", "cp1251", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def jsonl_write(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    shared_jsonl_write(path, rows)


def is_office_temp_file(path: Path) -> bool:
    name = path.name
    return name.startswith(OFFICE_TEMP_PREFIXES)


def is_hard_excluded(path: Path, root: Path) -> bool:
    if is_office_temp_file(path):
        return True
    if path.suffix.lower() in TEMP_EXTENSIONS | HARD_EXCLUDE_EXTENSIONS:
        return True
    lowered_parts = {part.lower() for part in path.parts}
    if lowered_parts & HARD_EXCLUDE_DIRS:
        return True
    try:
        rel = "/" + path.relative_to(root).as_posix().lower()
    except ValueError:
        rel = "/" + path.as_posix().lower()
    rel = rel.replace("\\", "/")
    return any(fragment in rel for fragment in HARD_EXCLUDE_PATH_FRAGMENTS)


def should_skip_path(path: Path, root: Path, include_extensions: set[str], exclude_dirs: set[str], exclude_extensions: set[str], exclude_path_patterns: list[str]) -> bool:
    if is_hard_excluded(path, root):
        return True
    ext = path.suffix.lower()
    if ext not in include_extensions:
        return True
    if ext in exclude_extensions:
        return True
    parts = {part.lower() for part in path.parts}
    if any(excluded.lower() in parts for excluded in exclude_dirs):
        return True
    rel = path.relative_to(root).as_posix()
    for pattern in exclude_path_patterns:
        if fnmatch(rel, pattern) or fnmatch("/" + rel, pattern):
            return True
    return False


def iter_source_files(cfg: dict[str, Any]) -> list[Path]:
    root = Path(os.path.expandvars(str(cfg.get("project_root", WORK_ROOT)))).resolve()
    include_extensions = {str(item).lower() for item in cfg.get("include_extensions", [])}
    exclude_dirs = {str(item).lower() for item in cfg.get("exclude_dirs", [])}
    exclude_extensions = {str(item).lower() for item in cfg.get("exclude_extensions", [])}
    exclude_path_patterns = [str(item) for item in cfg.get("exclude_path_patterns", [])]

    paths: list[Path] = []
    for path in root.rglob("*"):
        if path.is_file() and not should_skip_path(path, root, include_extensions, exclude_dirs, exclude_extensions, exclude_path_patterns):
            paths.append(path)
    paths.sort(key=lambda item: item.as_posix().lower())
    return paths


def relative_to_project(cfg: dict[str, Any], path: Path) -> str:
    root = Path(os.path.expandvars(str(cfg.get("project_root", WORK_ROOT)))).resolve()
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def enrich_block_metadata(relative_path: str, extension: str, text: str) -> dict[str, Any]:
    base = {
        "relative_path": relative_path,
        "source_path": relative_path,
        "extension": extension,
    }
    enriched = enrich_metadata(base, text)
    return {
        "source_type": enriched.get("source_type"),
        "document_type": enriched.get("document_type"),
        "stage": enriched.get("stage"),
        "module": enriched.get("module"),
        "section": enriched.get("section"),
        "sections": enriched.get("sections") or infer_sections(text),
    }


def detect_heading_level(style_name: str | None) -> int | None:
    if not style_name:
        return None
    style = style_name.lower()
    match = re.search(r"heading\s*(\d+)|заголовок\s*(\d+)", style)
    if match:
        raw = match.group(1) or match.group(2)
        return int(raw)
    return None


def text_hash(text: str) -> str:
    return stable_id(normalize_text(text), length=32)
