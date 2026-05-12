from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


WORK_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MAIN_CONFIG_PATH = WORK_ROOT / "config.yaml"
DEFAULT_ASU_CONFIG_DIR = WORK_ROOT / "configs" / "asu_june_bot"


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fp:
        data = yaml.safe_load(fp) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be object: {path}")
    return data


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_main_config(path: Path = DEFAULT_MAIN_CONFIG_PATH) -> dict[str, Any]:
    cfg = _read_yaml(path)
    work_root = os.path.expandvars(str(cfg.get("work_root", WORK_ROOT)))
    cfg["work_root_path"] = Path(work_root).resolve()
    if "project_root" in cfg:
        cfg["project_root_path"] = Path(os.path.expandvars(str(cfg["project_root"]))).resolve()
    return cfg


def load_asu_config(config_dir: Path = DEFAULT_ASU_CONFIG_DIR) -> dict[str, Any]:
    cfg: dict[str, Any] = {}
    for name in ("retrieval", "source_policy", "query_expansion", "llm", "guardrails"):
        cfg[name] = _read_yaml(config_dir / f"{name}.yaml")
    cfg["config_dir"] = str(config_dir)
    return cfg


def load_config() -> dict[str, Any]:
    main_cfg = load_main_config()
    asu_cfg = load_asu_config()
    cfg = _deep_merge(main_cfg, {"asu_june_bot": asu_cfg})
    cfg.setdefault("work_root_path", WORK_ROOT)
    return cfg


def resolve_work_path(cfg: dict[str, Any], raw: str | Path) -> Path:
    p = Path(raw)
    if not p.is_absolute():
        p = Path(cfg.get("work_root_path", WORK_ROOT)) / p
    return p.resolve()
