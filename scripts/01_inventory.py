from __future__ import annotations

from collections import Counter
from pathlib import Path

from rag_common import (
    ensure_runtime_dirs,
    is_under_excluded_dir,
    jsonl_write,
    load_config,
    path_rel_to_project,
    print_summary,
    resolve_work_path,
    sha256_file,
)


def classify_file(path: Path, rel: Path, cfg: dict) -> tuple[str, str]:
    ext = path.suffix.lower()
    include_ext = {x.lower() for x in cfg.get("include_extensions", [])}
    exclude_ext = {x.lower() for x in cfg.get("exclude_extensions", [])}
    exclude_dirs = {x.lower() for x in cfg.get("exclude_dirs", [])}

    if path.name.startswith("~$"):
        return "excluded", "office_temp_file"
    if is_under_excluded_dir(rel, exclude_dirs):
        return "excluded", "excluded_dir"
    if ext in exclude_ext:
        return "excluded", "excluded_extension"
    if ext not in include_ext:
        return "unsupported", "unsupported_extension"
    return "included", "ok"


def main() -> None:
    cfg = load_config()
    ensure_runtime_dirs(cfg)

    project_root = cfg["project_root_path"]
    manifest_path = resolve_work_path(cfg, cfg["paths"]["manifest"])

    rows = []
    status_counter: Counter[str] = Counter()
    ext_counter: Counter[str] = Counter()

    for path in project_root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(project_root)
        status, reason = classify_file(path, rel, cfg)
        stat = path.stat()
        ext = path.suffix.lower()
        ext_counter[ext or "<none>"] += 1
        status_counter[status] += 1

        digest = None
        if status == "included":
            try:
                digest = sha256_file(path)
            except OSError as exc:
                status = "error"
                reason = f"sha256_error: {exc}"
                status_counter["included"] -= 1
                status_counter["error"] += 1

        rows.append(
            {
                "path": str(path),
                "relative_path": path_rel_to_project(cfg, path),
                "extension": ext,
                "size": stat.st_size,
                "mtime": stat.st_mtime,
                "sha256": digest,
                "status": status,
                "reason": reason,
            }
        )

    count = jsonl_write(manifest_path, rows)
    print_summary(
        "Inventory complete",
        {
            "project_root": str(project_root),
            "manifest": str(manifest_path),
            "files": count,
            "included": status_counter.get("included", 0),
            "excluded": status_counter.get("excluded", 0),
            "unsupported": status_counter.get("unsupported", 0),
            "errors": status_counter.get("error", 0),
            "top_extensions": ", ".join(f"{k}:{v}" for k, v in ext_counter.most_common(12)),
        },
    )


if __name__ == "__main__":
    main()
