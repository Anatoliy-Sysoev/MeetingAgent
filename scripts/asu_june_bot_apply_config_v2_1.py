from __future__ import annotations

import argparse
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


WORK_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROJECT_ROOT = r"C:\Users\Сотрудник\Desktop\!Проектные документы АСУ"

INCLUDE_EXTENSIONS = [
    ".docx",
    ".pdf",
    ".xlsx",
    ".xlsb",
    ".pptx",
    ".md",
    ".txt",
    ".json",
    ".yml",
    ".yaml",
    ".drawio",
    ".puml",
    ".bpmn",
    ".srt",
]

EXCLUDE_DIRS = [
    ".git",
    "__pycache__",
    "node_modules",
    "_backup",
    "backup",
    "Архив",
    "archive",
    "_archive",
    "Черновики и шаблоны",
    "cache",
    ".venv",
    "dist",
    "build",
    "site_review_runs",
    "playwright",
    "exports",
    "html",
    "html_export",
    "docs_html",
    "docs_text",
    "pages_html",
    "pages_text",
    "screenshots",
    "tmp",
    "temp",
    ".tmp",
]

EXCLUDE_PATH_PATTERNS = [
    "**/Система/**",
    "**/asu_docs_export/**",
    "**/asu_admin_export/**",
    "**/docs_html/**",
    "**/docs_text/**",
    "**/pages_html/**",
    "**/pages_text/**",
    "**/site_review_runs/**",
    "**/playwright/**",
    "**/exports/**",
    "**/screenshots/**",
    "**/*.har",
    "**/~$*",
    "**/.~*",
    "**/*.tmp",
    "**/*.temp",
    "_analysis/docx_json*/**",
    "**/_analysis/docx_json*/**",
    "_analysis/site_review*/**",
    "**/_analysis/site_review*/**",
    "_analysis/__pycache__/**",
    "**/_analysis/__pycache__/**",
    "_analysis/*.py",
    "**/_analysis/*.py",
    "_analysis/*.docx",
    "**/_analysis/*.docx",
    "_analysis/*.json",
    "**/_analysis/*.json",
    "**/Архив/**",
    "**/Архив*/**",
    "**/archive/**",
    "**/archive*/**",
    "**/_archive/**",
    "**/_archive*/**",
    "**/backup/**",
    "**/backup*/**",
    "**/_backup/**",
    "**/_backup*/**",
    "**/*backup*",
    "**/Черновики и шаблоны/**",
    "**/_to_review*/**",
]

EXCLUDE_EXTENSIONS = [
    ".pyc",
    ".ttf",
    ".otf",
    ".woff",
    ".woff2",
    ".zip",
    ".rar",
    ".7z",
    ".tar",
    ".gz",
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".har",
    ".tmp",
    ".temp",
]


def unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with path.open("r", encoding="utf-8") as fp:
        data = yaml.safe_load(fp) or {}
    if not isinstance(data, dict):
        raise ValueError("config.yaml root must be a YAML object")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply Asu June Bot v2.1 local config filters")
    parser.add_argument("--config", default=str(WORK_ROOT / "config.yaml"), help="Path to local config.yaml")
    parser.add_argument("--project-root", default=DEFAULT_PROJECT_ROOT, help="Project documents root")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    project_root = Path(args.project_root).resolve()

    if not project_root.exists():
        raise FileNotFoundError(f"Project root not found: {project_root}")

    data = load_yaml(config_path)
    backup_path = config_path.with_name(f"{config_path.name}.bak_v2_1_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    shutil.copy2(config_path, backup_path)

    data["project_root"] = project_root.as_posix()
    data["include_extensions"] = unique(INCLUDE_EXTENSIONS)
    data["exclude_dirs"] = unique(list(data.get("exclude_dirs") or []) + EXCLUDE_DIRS)
    data["exclude_path_patterns"] = unique(list(data.get("exclude_path_patterns") or []) + EXCLUDE_PATH_PATTERNS)
    data["exclude_extensions"] = unique(list(data.get("exclude_extensions") or []) + EXCLUDE_EXTENSIONS)

    with config_path.open("w", encoding="utf-8", newline="\n") as fp:
        yaml.safe_dump(data, fp, allow_unicode=True, sort_keys=False, width=120)

    print("Config updated")
    print(f"config: {config_path}")
    print(f"backup: {backup_path}")
    print(f"project_root: {data['project_root']}")
    print(f"include_extensions: {len(data['include_extensions'])}")
    print(f"exclude_dirs: {len(data['exclude_dirs'])}")
    print(f"exclude_path_patterns: {len(data['exclude_path_patterns'])}")
    print(f"exclude_extensions: {len(data['exclude_extensions'])}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
