from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml


WORK_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = WORK_ROOT / "config.yaml"
SRC_DIR = WORK_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from asu_june_bot.core.hashing import stable_id as shared_stable_id  # noqa: E402
from asu_june_bot.core.jsonl import jsonl_read as shared_jsonl_read, jsonl_write as shared_jsonl_write  # noqa: E402
from asu_june_bot.core.path_filters import is_excluded_by_path_patterns as shared_is_excluded_by_path_patterns  # noqa: E402


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
    yield from shared_jsonl_read(path)


def jsonl_write(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    return shared_jsonl_write(path, rows)


STRICT_SENSITIVE_QUERY_PATTERNS = (
    ".env",
    "config.yaml",
    "пароль",
    "пароли",
    "password",
    "secret",
    "секрет",
    "system prompt",
    "системный промпт",
    "инструкции модели",
    "developer message",
    "api key",
    "ключ api",
)

TOKEN_SENSITIVE_QUERY_PATTERNS = (
    "token",
    "токен",
    "bearer",
    "jwt",
)

PROJECT_AUTH_ALLOW_TERMS = (
    "bearer",
    "bearer token",
    "токен",
    "token",
    "jwt",
    "oauth",
    "oidc",
    "ldaps",
    "ldap",
    "active directory",
    "blitz",
    "блиц",
)

PROJECT_AUTH_CONTEXT_TERMS = (
    "цп упкс",
    "проект",
    "проектн",
    "документ",
    "требован",
    "описан",
    "указан",
    "сои",
    "цта",
    "интеграц",
    "справоч",
    "mdr",
    "кшд",
    "active directory",
    " ad ",
    "авторизац",
    "аутентификац",
    "нси",
    "ldaps",
    "ldap",
    "порт 636",
    "групп",
    "app_ccpm",
    "dn",
    "upn",
)

PROJECT_AUTH_SAFE_ACTION_TERMS = (
    "что",
    "как в проекте",
    "где описан",
    "где указ",
    "какой",
    "какие",
    "описан",
    "указан",
    "используется",
    "применяется",
    "работает",
    "интеграция",
    "синхронизация",
    "срок жизни",
    "авторизация",
    "аутентификация",
)

HARMFUL_SECURITY_TERMS = (
    "sql injection",
    "sql-инъек",
    "sql инъек",
    "инъекц",
    "эксплойт",
    "эксплуат",
    "взлом",
    "xss",
    "csrf",
    "rce",
    "remote code execution",
    "privilege escalation",
    "повышение привилег",
    "обход авторизации",
    "обойти авторизацию",
    "bypass auth",
)

DESTRUCTIVE_SQL_TERMS = (
    "drop table",
    "delete from",
    "truncate table",
    "удаления таблиц",
    "удаления таблицы",
    "удалить таблиц",
    "удалить таблицу",
    "удали таблиц",
    "удали таблицу",
)

HARMFUL_SECURITY_ACTION_TERMS = (
    "как выполнить",
    "как сделать",
    "как провести",
    "как написать",
    "напиши пример",
    "пример sql",
    "дай payload",
    "payload",
    "пейлоад",
    "обойти",
    "сломать",
    "взломать",
    "украсть",
    "вытащить",
    "получить токен",
    "получить jwt",
    "вытащить пароль",
    "подобрать пароль",
    "эксплуатировать",
    "эксплойт",
)

PROJECT_SECURITY_LOOKUP_TERMS = (
    "фтт",
    "требован",
    "проект",
    "проектн",
    "документ",
    "описан",
    "указан",
    "защит",
    "мер",
    "сои",
    "цта",
    "пми",
    "пси",
    "проверить защищенность",
    "тестировать защищенность",
)

SENSITIVE_QUERY_PATTERNS = STRICT_SENSITIVE_QUERY_PATTERNS + TOKEN_SENSITIVE_QUERY_PATTERNS


def normalize_query_text(text: str) -> str:
    return " ".join(str(text or "").lower().replace("ё", "е").split())


def is_project_auth_query(text: str) -> bool:
    lowered = f" {normalize_query_text(text)} "
    has_allowed_auth_term = any(term in lowered for term in PROJECT_AUTH_ALLOW_TERMS)
    has_project_context = any(term in lowered for term in PROJECT_AUTH_CONTEXT_TERMS)
    has_safe_lookup = any(term in lowered for term in PROJECT_AUTH_SAFE_ACTION_TERMS)
    return has_allowed_auth_term and has_project_context and (has_safe_lookup or not any(term in lowered for term in HARMFUL_SECURITY_ACTION_TERMS))


def is_project_security_lookup_query(text: str) -> bool:
    lowered = normalize_query_text(text)
    has_project_lookup = any(term in lowered for term in PROJECT_SECURITY_LOOKUP_TERMS)
    has_harmful_topic = any(term in lowered for term in HARMFUL_SECURITY_TERMS)
    has_abuse_action = any(term in lowered for term in HARMFUL_SECURITY_ACTION_TERMS)
    return has_project_lookup and has_harmful_topic and not has_abuse_action


def is_harmful_security_query(text: str) -> bool:
    lowered = normalize_query_text(text)
    if is_project_auth_query(lowered) or is_project_security_lookup_query(lowered):
        return False
    has_harmful_marker = any(term in lowered for term in HARMFUL_SECURITY_TERMS)
    has_destructive_sql = ("sql" in lowered or "запрос" in lowered) and any(term in lowered for term in DESTRUCTIVE_SQL_TERMS)
    if not has_harmful_marker and not has_destructive_sql:
        return False
    has_abuse_action = any(term in lowered for term in HARMFUL_SECURITY_ACTION_TERMS)
    has_project_lookup = any(term in lowered for term in PROJECT_SECURITY_LOOKUP_TERMS)
    return has_destructive_sql or has_abuse_action or not has_project_lookup


def is_sensitive_query(text: str) -> bool:
    lowered = normalize_query_text(text)
    if is_harmful_security_query(lowered):
        return True
    if any(pattern in lowered for pattern in STRICT_SENSITIVE_QUERY_PATTERNS):
        return True
    if any(pattern in lowered for pattern in TOKEN_SENSITIVE_QUERY_PATTERNS):
        return not is_project_auth_query(lowered)
    return False


def append_query_log(record: dict[str, Any], cfg: dict[str, Any] | None = None) -> None:
    """Append one query run to the local query log.

    Sensitive queries are never written: the log is runtime data and may
    otherwise leak secrets pasted into a question.
    """
    if is_sensitive_query(str(record.get("question", ""))):
        return
    if cfg is not None:
        raw = cfg.get("paths", {}).get("query_log", "data/query_log.jsonl")
        path = resolve_work_path(cfg, raw)
    else:
        path = WORK_ROOT / "data" / "query_log.jsonl"
    record.setdefault("ts", datetime.now(timezone.utc).isoformat())
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fp:
        fp.write(json.dumps(record, ensure_ascii=False) + "\n")


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
    return shared_stable_id(text, length=length)


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
    return shared_is_excluded_by_path_patterns(rel_path, patterns)


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
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = max(0, end - overlap)
    return chunks


def throttle_sleep(delay: float) -> None:
    if delay > 0:
        time.sleep(delay)
