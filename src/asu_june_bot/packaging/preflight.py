"""Local runtime preflight checks for MeetingAgent packaging.

The checks are intentionally small and dependency-light: they verify host
commands, local Ollama availability, required models, and optional ASR imports
before a user starts Docker/API/Workspace workflows on another machine.
"""
from __future__ import annotations

import importlib.util
import json
import platform
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any

import requests


DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_EMBEDDING_MODEL = "bge-m3"
DEFAULT_CHAT_MODEL = "qwen3.5:4b"


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    detail: str
    required: bool = True

    @property
    def ok(self) -> bool:
        return self.status == "ok" or (self.status == "warn" and not self.required)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "required": self.required,
        }


def _run_version(command: list[str], timeout_sec: int = 10) -> tuple[bool, str]:
    executable = shutil.which(command[0])
    if not executable:
        return False, f"{command[0]} not found in PATH"
    try:
        proc = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
    except Exception as exc:
        return False, f"{command[0]} failed: {type(exc).__name__}: {exc}"
    output = (proc.stdout or proc.stderr or "").splitlines()
    first_line = output[0].strip() if output else f"exit code {proc.returncode}"
    return proc.returncode == 0, first_line


def check_python() -> CheckResult:
    version = platform.python_version()
    major, minor, *_ = platform.python_version_tuple()
    ok = (int(major), int(minor)) >= (3, 11)
    return CheckResult(
        name="python",
        status="ok" if ok else "error",
        detail=f"Python {version}",
    )


def check_command(name: str, command: list[str], required: bool = True) -> CheckResult:
    ok, detail = _run_version(command)
    return CheckResult(
        name=name,
        status="ok" if ok else ("error" if required else "warn"),
        detail=detail,
        required=required,
    )


def check_import(module_name: str, label: str | None = None, required: bool = False) -> CheckResult:
    found = importlib.util.find_spec(module_name) is not None
    name = label or module_name
    return CheckResult(
        name=name,
        status="ok" if found else ("error" if required else "warn"),
        detail="importable" if found else f"{module_name} is not installed",
        required=required,
    )


def _ollama_tags(base_url: str, timeout_sec: int) -> list[str]:
    url = base_url.rstrip("/") + "/api/tags"
    response = requests.get(url, timeout=timeout_sec)
    response.raise_for_status()
    payload = response.json()
    tags = []
    for model in payload.get("models") or []:
        if isinstance(model, dict):
            name = model.get("name") or model.get("model")
            if name:
                tags.append(str(name))
    return tags


def check_ollama(
    base_url: str = DEFAULT_OLLAMA_URL,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    chat_model: str = DEFAULT_CHAT_MODEL,
    timeout_sec: int = 10,
) -> list[CheckResult]:
    try:
        tags = _ollama_tags(base_url, timeout_sec=timeout_sec)
    except Exception as exc:
        return [
            CheckResult(
                name="ollama_api",
                status="error",
                detail=f"{base_url} unavailable: {type(exc).__name__}: {exc}",
            )
        ]

    results = [
        CheckResult(
            name="ollama_api",
            status="ok",
            detail=f"{base_url} reachable; {len(tags)} model(s) visible",
        )
    ]
    visible = set(tags)
    for label, model in (("embedding_model", embedding_model), ("chat_model", chat_model)):
        results.append(
            CheckResult(
                name=label,
                status="ok" if model in visible else "error",
                detail=f"{model} present" if model in visible else f"{model} missing in Ollama tags",
            )
        )
    return results


def run_preflight(
    *,
    mode: str = "docker",
    ollama_url: str = DEFAULT_OLLAMA_URL,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    chat_model: str = DEFAULT_CHAT_MODEL,
    skip_ollama: bool = False,
    optional_asr: bool = False,
) -> list[CheckResult]:
    if mode not in {"docker", "local"}:
        raise ValueError("mode must be 'docker' or 'local'")

    results = [check_python()]
    if mode == "docker":
        results.append(check_command("docker", ["docker", "--version"]))
        results.append(check_command("docker_compose", ["docker", "compose", "version"]))
        # Host ffmpeg is optional in Docker mode because the image installs it.
        results.append(check_command("ffmpeg_host", ["ffmpeg", "-version"], required=False))
    else:
        results.append(check_command("ffmpeg", ["ffmpeg", "-version"]))
        results.append(check_import("faster_whisper", "faster_whisper", required=True))

    if optional_asr:
        results.extend([
            check_import("gigaam", "gigaam", required=False),
            check_import("sherpa_onnx", "sherpa_onnx", required=False),
            check_import("vosk", "vosk", required=False),
            check_import("silero_vad", "silero_vad", required=False),
        ])

    if not skip_ollama:
        results.extend(check_ollama(ollama_url, embedding_model, chat_model))
    return results


def has_required_failures(results: list[CheckResult]) -> bool:
    return any(result.required and result.status != "ok" for result in results)


def format_results(results: list[CheckResult]) -> str:
    lines = []
    for result in results:
        marker = "OK" if result.status == "ok" else ("WARN" if result.status == "warn" else "FAIL")
        requirement = "required" if result.required else "optional"
        lines.append(f"[{marker}] {result.name} ({requirement}) - {result.detail}")
    return "\n".join(lines)


def results_json(results: list[CheckResult]) -> str:
    return json.dumps([result.as_dict() for result in results], ensure_ascii=False, indent=2)
