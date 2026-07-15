from __future__ import annotations

import os
import subprocess
import sys
import time

import pytest

from meeting_agent.jobs.processes import _pid_alive, process_identity, process_matches


@pytest.mark.skipif(os.name != "nt", reason="Windows process-liveness regression")
def test_windows_process_identity_does_not_terminate_live_child() -> None:
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    try:
        identity = process_identity(process.pid)

        assert identity is not None
        assert identity.startswith("windows:")
        assert process.poll() is None
        assert _pid_alive(process.pid) is True
        assert process_matches(process.pid, identity) is True
        time.sleep(0.1)
        assert process.poll() is None
    finally:
        process.terminate()
        process.wait(timeout=5)


@pytest.mark.skipif(os.name != "nt", reason="Windows process-liveness regression")
def test_windows_exited_child_is_not_alive() -> None:
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait(timeout=5)

    assert _pid_alive(process.pid) is False
    assert process_identity(process.pid) is None
