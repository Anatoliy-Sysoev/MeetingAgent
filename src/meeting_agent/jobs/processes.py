from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        return _windows_pid_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _windows_process_handle(pid: int) -> tuple[Any, Any]:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    return kernel32, kernel32.OpenProcess(0x1000, False, pid)


def _windows_pid_alive(pid: int) -> bool:
    import ctypes
    from ctypes import wintypes

    kernel32, process = _windows_process_handle(pid)
    if not process:
        return ctypes.get_last_error() == 5
    exit_code = wintypes.DWORD()
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, wintypes.LPDWORD]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    try:
        if not kernel32.GetExitCodeProcess(process, ctypes.byref(exit_code)):
            return False
        return exit_code.value == 259
    finally:
        kernel32.CloseHandle(process)


def _windows_process_identity(pid: int) -> str | None:
    import ctypes
    from ctypes import wintypes

    kernel32, process = _windows_process_handle(pid)
    if not process:
        return None
    creation = wintypes.FILETIME()
    exit_time = wintypes.FILETIME()
    kernel = wintypes.FILETIME()
    user = wintypes.FILETIME()
    try:
        kernel32.GetProcessTimes.argtypes = [
            wintypes.HANDLE,
            wintypes.LPFILETIME,
            wintypes.LPFILETIME,
            wintypes.LPFILETIME,
            wintypes.LPFILETIME,
        ]
        kernel32.GetProcessTimes.restype = wintypes.BOOL
        ok = kernel32.GetProcessTimes(
            process,
            ctypes.byref(creation),
            ctypes.byref(exit_time),
            ctypes.byref(kernel),
            ctypes.byref(user),
        )
        if not ok:
            return None
        ticks = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
        return f"windows:{ticks}"
    finally:
        kernel32.CloseHandle(process)


def _linux_process_identity(pid: int) -> str | None:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        tail = stat.rsplit(")", 1)[1].strip().split()
        state = tail[0]
        start_ticks = tail[19]
    except (OSError, IndexError):
        return None
    if state == "Z":
        return None
    return f"linux:{start_ticks}"


def process_identity(pid: int | None) -> str | None:
    if pid is None or not _pid_alive(pid):
        return None
    if os.name == "nt":
        return _windows_process_identity(pid)
    if Path("/proc").exists():
        return _linux_process_identity(pid)
    return f"pid:{pid}"


def process_matches(pid: int | None, identity: str | None) -> bool:
    if pid is None or identity is None or not _pid_alive(pid):
        return False
    current = process_identity(pid)
    return current is not None and current == identity


async def _wait_until_gone(
    pid: int,
    identity: str,
    timeout_seconds: float,
    process: Any = None,
) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        # On Windows the kernel process object can remain addressable by PID
        # while asyncio still owns its handle, even though the process has
        # exited and returncode is already available.
        if process is not None and process.returncode is not None:
            return True
        if not process_matches(pid, identity):
            return True
        await asyncio.sleep(0.05)
    if process is not None and process.returncode is not None:
        return True
    return not process_matches(pid, identity)


async def terminate_process_tree(
    *,
    pid: int | None,
    identity: str | None,
    process: Any = None,
    grace_seconds: float = 3.0,
) -> bool:
    """Terminate a verified process group/tree without targeting a reused PID."""
    if process is not None and not isinstance(process, asyncio.subprocess.Process):
        process.terminate()
        return True
    if not process_matches(pid, identity):
        return False
    assert pid is not None

    if os.name == "nt":
        killer = await asyncio.create_subprocess_exec(
            "taskkill",
            "/PID",
            str(pid),
            "/T",
            "/F",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await killer.communicate()
        if killer.returncode != 0 and process is not None:
            process.terminate()
        return await _wait_until_gone(pid, identity, grace_seconds, process)

    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    if await _wait_until_gone(pid, identity, grace_seconds, process):
        return True
    if not process_matches(pid, identity):
        return True
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    return await _wait_until_gone(pid, identity, 1.0, process)


def subprocess_group_kwargs() -> dict[str, Any]:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}
