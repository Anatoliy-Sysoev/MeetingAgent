from __future__ import annotations

import json
from pathlib import Path

from .models import EvalCase


def load_cases(path: Path) -> list[EvalCase]:
    cases: list[EvalCase] = []
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            raw = line.strip()
            if not raw or raw.startswith("//"):
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc
            try:
                cases.append(EvalCase.from_dict(data))
            except Exception as exc:  # noqa: BLE001
                raise ValueError(f"Invalid eval case at {path}:{line_number}: {exc}") from exc
    return cases
