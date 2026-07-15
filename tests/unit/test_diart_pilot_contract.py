from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_diart_requirements_are_cpu_only_and_isolated() -> None:
    text = (ROOT / "requirements-diart.txt").read_text(encoding="utf-8")
    lock_text = (ROOT / "constraints-diart-py310-linux.txt").read_text(encoding="utf-8")
    assert "diart==0.9.2" in text
    assert "pyannote.audio==3.1.1" in text
    assert "torch==2.2.2+cpu" in text
    assert "torchaudio==2.2.2+cpu" in text
    assert "torchvision==0.17.2+cpu" in text
    assert "onnxruntime-gpu" not in text
    forbidden_gpu_packages = ("onnxruntime-gpu", "nvidia-", "cuda-")
    assert all(package not in lock_text.lower() for package in forbidden_gpu_packages)
    assert "torch==2.2.2+cpu" in lock_text
    assert "torchvision==0.17.2+cpu" in lock_text
    assert "requirements-diart.txt" not in (ROOT / "Dockerfile").read_text(encoding="utf-8")


def test_diart_dockerfile_is_non_root_and_pinned() -> None:
    text = (ROOT / "Dockerfile.diart").read_text(encoding="utf-8")
    assert text.startswith("FROM ubuntu:22.04")
    assert '"pip==26.1.1"' in text
    assert "USER meetingagent:meetingagent" in text
    assert "COPY ." not in text
    assert "requirements-diart.txt" in text
    assert "constraints-diart-py310-linux.txt" in text


def test_diart_compose_profile_is_hardened() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    service = compose["services"]["diart"]
    assert service["profiles"] == ["diart"]
    assert service["read_only"] is True
    assert service["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in service["security_opt"]
    assert service["build"]["dockerfile"] == "Dockerfile.diart"
    assert "env_file" not in service
    assert service["environment"]["HF_TOKEN"] == "${HF_TOKEN:-}"
    assert service["environment"]["HF_HOME"] == "/cache/huggingface"
    assert service["environment"]["PYANNOTE_CACHE"] == "/cache/pyannote"
    assert service["environment"]["TORCH_HOME"] == "/cache/torch"
    assert service["environment"]["XDG_CACHE_HOME"] == "/cache/xdg"
    assert service["environment"]["MPLCONFIGDIR"] == "/cache/matplotlib"
    assert all(
        not str(value).startswith("/home/")
        for value in service["environment"].values()
    )
    assert "MEETINGAGENT_API_TOKEN" not in service["environment"]

    api = compose["services"]["diart-api"]
    assert api["profiles"] == ["diart-live"]
    assert api["read_only"] is True
    assert api["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in api["security_opt"]
    assert api["ports"] == ["127.0.0.1:8765:8765"]
    assert "./meetings:/meetings:ro" in api["volumes"]
    assert "MEETINGAGENT_API_TOKEN" not in api["environment"]
    assert api["environment"]["PYANNOTE_CACHE"] == "/cache/pyannote"


def test_diart_preflight_help_has_no_optional_import_requirement() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "50_diart_preflight.py"), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "--load-models" in result.stdout


def test_diart_sidecar_help_has_no_optional_import_requirement() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "51_diart_service.py"), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "--meetings-root" in result.stdout
