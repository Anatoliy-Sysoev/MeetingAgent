from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


RUNTIME_KEYS = {"default", "transcription", "gigaam", "diarization"}
_RUNTIME_ENV = {
    "default": "MEETINGAGENT_WORKER_PYTHON",
    "transcription": "MEETINGAGENT_TRANSCRIPTION_PYTHON",
    "gigaam": "MEETINGAGENT_GIGAAM_PYTHON",
    "diarization": "MEETINGAGENT_DIARIZATION_PYTHON",
}


@dataclass(frozen=True)
class WorkerRuntime:
    key: str
    executable: Path
    configured: bool

    @property
    def available(self) -> bool:
        if not self.executable.is_file():
            return False
        return os.name == "nt" or os.access(self.executable, os.X_OK)


class WorkerRuntimeRegistry:
    """Select local Python runtimes without exposing their paths through APIs."""

    def __init__(
        self,
        runtimes: dict[str, Path] | None = None,
        *,
        fallback: Path | str | None = None,
    ) -> None:
        self._runtimes = dict(runtimes or {})
        unknown = set(self._runtimes) - RUNTIME_KEYS
        if unknown:
            raise ValueError(f"Unknown worker runtime keys: {sorted(unknown)!r}")
        self._fallback = Path(fallback or sys.executable).resolve()

    def select(
        self,
        stage: str,
        options: dict[str, Any] | None = None,
    ) -> WorkerRuntime:
        if stage == "transcribe":
            engine = str((options or {}).get("asr_engine") or "faster-whisper")
            keys = ("gigaam", "transcription", "default") if engine == "gigaam" else (
                "transcription",
                "default",
            )
        elif stage == "diarize":
            keys = ("diarization", "default")
        else:
            keys = ("default",)
        for key in keys:
            executable = self._runtimes.get(key)
            if executable is not None:
                return WorkerRuntime(key=key, executable=executable, configured=True)
        return WorkerRuntime(key="api", executable=self._fallback, configured=False)

    def public_error(
        self,
        stage: str,
        options: dict[str, Any] | None = None,
    ) -> str | None:
        runtime = self.select(stage, options)
        return None if runtime.available else "configured worker runtime is unavailable"


def build_worker_runtime_registry(config: dict[str, Any]) -> WorkerRuntimeRegistry:
    jobs = config.get("jobs") if isinstance(config.get("jobs"), dict) else {}
    raw_runtimes = jobs.get("runtimes")
    if raw_runtimes is None:
        raw_runtimes = {}
    if not isinstance(raw_runtimes, dict):
        raise ValueError("jobs.runtimes must be an object")
    unknown = set(raw_runtimes) - RUNTIME_KEYS
    if unknown:
        raise ValueError(f"Unknown jobs.runtimes keys: {sorted(unknown)!r}")

    work_root = Path(config.get("work_root_path") or Path.cwd()).resolve()
    resolved: dict[str, Path] = {}
    for key in sorted(RUNTIME_KEYS):
        env_value = os.getenv(_RUNTIME_ENV[key], "").strip()
        raw_value = env_value if env_value else raw_runtimes.get(key)
        if raw_value in (None, ""):
            continue
        if not isinstance(raw_value, str):
            raise ValueError(f"jobs.runtimes.{key} must be a string")
        expanded = Path(os.path.expandvars(raw_value)).expanduser()
        if not expanded.is_absolute():
            expanded = work_root / expanded
        resolved[key] = expanded.resolve()
    return WorkerRuntimeRegistry(resolved)
