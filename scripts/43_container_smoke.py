from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SENTINEL = ROOT / ".meetingagent-private-sentinel"
DEFAULT_IMAGE = f"meetingagent:container-hardening-smoke-{os.getpid()}"


def _run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, check=check, text=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build the runtime image and verify its container security contract."
    )
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--keep-image", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if shutil.which("docker") is None:
        raise SystemExit("docker CLI is not available")
    daemon = subprocess.run(
        ["docker", "info"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if daemon.returncode != 0:
        raise SystemExit("Docker daemon is not available; start Docker Desktop and retry")
    existing_image = subprocess.run(
        ["docker", "image", "inspect", args.image],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if existing_image.returncode == 0:
        raise SystemExit(f"Refusing to overwrite existing image tag: {args.image}")
    if SENTINEL.exists():
        raise SystemExit(f"Refusing to overwrite existing sentinel: {SENTINEL.name}")

    try:
        SENTINEL.write_text("private-build-context-sentinel\n", encoding="utf-8")
        _run(["docker", "build", "--tag", args.image, "."])
        probe = (
            "import importlib.util, os; from pathlib import Path; "
            "assert os.geteuid() != 0, 'container runs as root'; "
            "assert not Path('/app/.meetingagent-private-sentinel').exists(), "
            "'private sentinel copied into image'; "
            "assert importlib.util.find_spec('pytest') is None, "
            "'test dependency installed in runtime image'; "
            "paths=['/app/data','/app/logs','/app/meetings','/app/vector_db','/app/watched_folder']; "
            "assert all(os.access(path, os.W_OK) for path in paths), "
            "'runtime directory is not writable'; "
            "print('container-hardening-smoke: ok')"
        )
        _run(["docker", "run", "--rm", "--entrypoint", "python", args.image, "-c", probe])
    finally:
        SENTINEL.unlink(missing_ok=True)
        if not args.keep_image:
            _run(["docker", "image", "rm", "--force", args.image], check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
