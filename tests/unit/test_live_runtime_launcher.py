from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / "scripts" / "start_meeting_agent_local.ps1"


def test_live_runtime_launcher_has_fail_closed_preflight() -> None:
    source = LAUNCHER.read_text(encoding="utf-8")

    for dependency in ("vosk", "sounddevice", "pyaudiowpatch", "soxr", "silero_vad"):
        assert dependency in source
    assert "am\\final.mdl" in source
    assert "conf\\model.conf" in source
    assert "MEETINGAGENT_LIVE_PYTHON" in source
    assert "MEETINGAGENT_LIVE_MODEL_PATH" in source
    assert "Test-MeetingAgentHealth" in source
    assert "Test-PortListener" in source


def test_live_runtime_launcher_is_portable_across_user_profiles() -> None:
    source = LAUNCHER.read_text(encoding="utf-8")

    assert "$PSScriptRoot" in source
    assert "C:\\Users\\" not in source
