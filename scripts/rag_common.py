from __future__ import annotations

import hashlib
import json
import os
import re
import time
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, Iterable

import yaml


WORK_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = WORK_ROOT / "config.yaml"


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open("r", encoding="utf-8") as fp:
        cfg = yaml.safe_load(fp) or {}
    work_root = os.path.expandvars(str(cfg.get("work_root", WORK_ROOT)))
    project_root = os.path.expandvars(str(cfg["project_root"]))
    cfg["work_root_path"] = Path(work_root).resolve()
    cfg["project_root_path"] = Path(project_root).resolve()
    return cfg


def resolve_work_path(cfg: dict[str, Any], raw: str) -> Path:
    p = Path(raw)
    if not p.is_absolute():
        p = cfg["work_root_path"] / p
    return p.resolve()


def ensure_runtime_dirs(cfg: dict[str, Any]) -> None:
    paths = cfg.get("paths", {})
    for key in ("extracted_text_dir", "logs", "watched_folder"):
        if key in paths:
            resolve_work_path(cfg, paths[key]).mkdir(parents=True, exist_ok=True)
    (cfg["work_root_path"] / "data").mkdir(parents=True, exist_ok=True)


def jsonl_read(path: Path) -> Iterable[dict[str, Any]]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if line:
                yield json.loads(line)


def jsonl_write(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as fp:
        for row in rows:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fp:
        while True:
            block = fp.read(block_size)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def stable_id(text: str, length: int = 24) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:length]


def normalize_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()


def safe_rel_id(rel_path: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-zА-Яа-я._-]+", "__", rel_path)
    return cleaned.strip("._")[:180] or "file"


def is_under_excluded_dir(rel_path: Path, excluded: set[str]) -> bool:
    parts = {part.lower() for part in rel_path.parts[:-1]}
    return bool(parts & excluded)


def is_excluded_by_path_patterns(rel_path: Path | str, patterns: Iterable[str]) -> bool:
    normalized = str(rel_path).replace("\\", "/").strip("/").lower()
    if not normalized:
        return False

    for raw_pattern in patterns:
        pattern = str(raw_pattern).replace("\\", "/").strip("/").lower()
        if not pattern:
            continue
        if fnmatchcase(normalized, pattern):
            return True
    return False


def path_rel_to_project(cfg: dict[str, Any], path: Path) -> str:
    return str(path.resolve().relative_to(cfg["project_root_path"])).replace("\\", "/")


def read_text_guess(path: Path) -> str:
    data = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp1251", "utf-16"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    text = normalize_text(text)
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        if end < len(text):
            split_at = max(text.rfind("\n\n", start, end), text.rfind(". ", start, end))
            if split_at > start + int(chunk_size * 0.55):
                end = split_at + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(0, end - overlap)
    return chunks


def print_summary(title: str, items: dict[str, Any]) -> None:
    print(f"\n{title}")
    print("=" * len(title))
    for key, value in items.items():
        print(f"{key}: {value}")


class FileLock:
    def __init__(self, path: Path, stale_after_sec: int = 24 * 3600):
        self.path = path
        self.stale_after_sec = stale_after_sec
        self.fd: int | None = None

    def __enter__(self) -> "FileLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            age = time.time() - self.path.stat().st_mtime
            if age > self.stale_after_sec:
                self.path.unlink(missing_ok=True)
        try:
            self.fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            detail = self.path.read_text(encoding="utf-8", errors="replace") if self.path.exists() else ""
            raise RuntimeError(f"Lock already exists: {self.path}\n{detail}") from exc
        os.write(self.fd, f"pid={os.getpid()}\nstarted={time.strftime('%Y-%m-%d %H:%M:%S')}\n".encode("utf-8"))
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        self.path.unlink(missing_ok=True)
