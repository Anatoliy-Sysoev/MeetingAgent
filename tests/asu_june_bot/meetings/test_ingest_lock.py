from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.meetings.ingest_lock import IngestLock  # noqa: E402


_CHILD_SCRIPT = """
import sys
from pathlib import Path
from asu_june_bot.meetings.ingest_lock import IngestLock, IngestLockTimeoutError

try:
    with IngestLock(Path(sys.argv[1]), timeout_seconds=0.25, poll_seconds=0.01):
        pass
except IngestLockTimeoutError:
    raise SystemExit(42)
"""


def _child_attempt(lock_path: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [str(SRC), env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    return subprocess.run(
        [sys.executable, "-c", _CHILD_SCRIPT, str(lock_path)],
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )


def test_lock_blocks_another_process_and_releases_cleanly(tmp_path: Path) -> None:
    lock_path = tmp_path / ".ingest.lock"

    with IngestLock(lock_path, timeout_seconds=1):
        blocked = _child_attempt(lock_path)

    acquired = _child_attempt(lock_path)

    assert blocked.returncode == 42, blocked.stderr
    assert acquired.returncode == 0, acquired.stderr


@pytest.mark.parametrize("timeout", [0, -1])
def test_lock_rejects_non_positive_timeout(tmp_path: Path, timeout: float) -> None:
    with pytest.raises(ValueError):
        IngestLock(tmp_path / ".ingest.lock", timeout_seconds=timeout)
