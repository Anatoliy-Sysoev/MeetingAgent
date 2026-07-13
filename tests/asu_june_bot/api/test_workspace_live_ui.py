"""Static contract tests for the Workspace live transcription surface (#207)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.api.ui_assets import load_ui_asset, load_ui_template  # noqa: E402


def _normalize(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


@pytest.fixture(scope="module")
def html() -> str:
    return _normalize(
        load_ui_template("workspace.html")
        + load_ui_asset("workspace.js")
        + load_ui_asset("workspace.css")
    )


def _function_block(source: str, name: str) -> str:
    marker = f"async function {name}"
    block = source[source.index(marker) :]
    return block[: block.index("\n}\n") + 2]


def test_live_panel_has_distinct_mic_and_sys_tracks(html: str) -> None:
    assert 'id="live-panel"' in html
    assert 'data-live-source="MIC"' in html
    assert 'data-live-source="SYS"' in html
    assert 'id="live-mic-title">Microphone' in html
    assert 'id="live-sys-title">System audio' in html
    assert 'data-live-source="MIX"' not in html


def test_live_draft_is_explicitly_not_indexed(html: str) -> None:
    assert "Live text is a draft and is not indexed" in html
    assert "offline transcription" in html


def test_live_controls_are_native_and_source_scoped(html: str) -> None:
    for source in ("mic", "sys"):
        assert f'id="live-{source}-device"' in html
        assert f'id="live-{source}-vad"' in html
        assert f'id="live-{source}-force"' in html
        assert f'id="live-{source}-start"' in html
        assert f'id="live-{source}-stop"' in html
        assert f'id="live-{source}-partial"' in html
        assert f'id="live-{source}-finals"' in html


def test_live_controls_have_accessible_status_and_labels(html: str) -> None:
    assert 'aria-labelledby="live-mic-title"' in html
    assert 'aria-labelledby="live-sys-title"' in html
    assert 'aria-live="polite"' in html
    assert html.count('role="log"') == 2
    assert 'aria-relevant="additions text"' in html
    assert 'role="alert"' in html
    assert 'for="live-mic-device"' in html
    assert 'for="live-sys-device"' in html


def test_live_api_contract_is_fully_wired(html: str) -> None:
    assert "/live/preflight?${query.toString()}" in html
    assert "/live/sessions/active?${query.toString()}" in html
    assert "/live/sessions`" in html
    assert "${prefix}/events?after=${state.cursor}&limit=200" in html
    assert "${sessionId}/stop`" in html


def test_live_start_and_stop_require_csrf_before_post(html: str) -> None:
    for name in ("startLiveSession", "stopLiveSession"):
        block = _function_block(html, name)
        assert "ensureCsrf()" in block
        assert 'method: "POST"' in block
        assert '"X-CSRF-Token": csrf' in block
        assert block.index("if (!csrf)") < block.index('method: "POST"')


def test_live_start_sends_explicit_source_vad_device_and_force(html: str) -> None:
    block = _function_block(html, "startLiveSession")
    assert "const body = { source, vad, force }" in block
    assert "body.audio_device_index = device" in block
    assert "JSON.stringify(body)" in block
    assert 'liveElement(source, "force").checked = false' in block


def test_live_permissions_gate_start_and_stop(html: str) -> None:
    block = html[html.index("function renderLiveTrack") :]
    block = block[: block.index("async function liveResponseMessage")]
    assert '_permissions.has("jobs.start")' in block
    assert '_permissions.has("jobs.cancel")' in block
    assert "start.disabled" in block
    assert "stop.disabled" in block


def test_live_partial_is_replaced_by_final_event(html: str) -> None:
    block = html[html.index("function applyLiveEvents") :]
    block = block[: block.index("async function pollLiveTrack")]
    assert 'event.type === "partial"' in block
    assert 'event.type === "final"' in block
    assert 'state.partial = ""' in block
    assert "state.finals.push" in block
    assert "eventId <= state.cursor" in block
    assert "batchSeen.has(eventId)" in block


def test_live_final_dom_is_bounded_and_source_labeled(html: str) -> None:
    assert "LIVE_FINAL_ROWS_MAX = 250" in html
    assert "state.finals.splice" in html
    assert "renderedFinalsRevision" in html
    assert "renderedDevicesRevision" in html
    assert "renderedWarningsKey" in html
    block = html[html.index("function renderLiveFinals") :]
    block = block[: block.index("function renderLiveTrack")]
    assert "`${source} · ${fmtSec(event.start)}–${fmtSec(event.end)}`" in block
    assert "textContent" in block
    assert "replaceChildren" in block


def test_live_polling_uses_bounded_cursor_and_stops_when_idle(html: str) -> None:
    assert "LIVE_POLL_INTERVAL_MS = 750" in html
    assert "after=${state.cursor}&limit=200" in html
    assert "payload.next_after" in html
    assert "stopLiveTimersIfIdle" in html
    assert "_livePollInFlight" in html
    assert "state.seen" not in html


def test_live_elapsed_and_capture_warnings_are_rendered(html: str) -> None:
    assert "function updateLiveElapsed" in html
    assert "liveElapsedSeconds" in html
    assert "function renderLiveWarnings" in html
    assert "session.warnings" in html
    assert 'aria-label="Microphone capture warnings"' in html
    assert 'aria-label="System audio capture warnings"' in html


def test_live_blocked_reasons_are_controlled(html: str) -> None:
    for code in (
        "model_missing",
        "sounddevice_missing",
        "sys_loopback_backend_missing",
        "live_session_capacity",
        "live_artifact_exists",
    ):
        assert f"{code}:" in html
    response_block = _function_block(html, "liveResponseMessage")
    assert "body.detail.code" in response_block
    assert "body.detail.message" not in response_block


def test_live_dynamic_content_uses_csp_safe_dom_apis(html: str) -> None:
    live_block = html[html.index("// ---- live transcription draft ----") :]
    live_block = live_block[: live_block.index("// ---- speaker mapping ----")]
    assert "innerHTML" not in live_block
    assert not re.search(r"\.style(?:\.|\s*=)", live_block)
    assert "textContent" in live_block
    assert "replaceChildren" in live_block
    assert "addEventListener" in html


def test_live_state_is_memory_only(html: str) -> None:
    assert "localStorage" not in html
    assert "sessionStorage" not in html
    assert "partial_events_durable" not in html


def test_reload_authenticates_before_rendering_live_permissions(html: str) -> None:
    block = _function_block(html, "reloadAll")
    assert block.index("await loadPermissions()") < block.index("loadLive()")


def test_live_and_offline_pipeline_are_mutually_exclusive_in_ui(html: str) -> None:
    assert "function anyLiveActive" in html
    for name in ("startStage", "startPipeline", "retryStage"):
        block = _function_block(html, name)
        assert "anyLiveActive()" in block
        assert block.index("anyLiveActive()") < block.index('method: "POST"')
    start = _function_block(html, "startLiveSession")
    assert "_activeJob !== null" in start
    assert start.index("_activeJob !== null") < start.index('method: "POST"')


def test_live_polling_failure_is_controlled_and_retried(html: str) -> None:
    track = _function_block(html, "pollLiveTrack")
    assert "!eventsResp.ok || !statusResp.ok" in track
    assert 'throw new Error("live_poll_failed")' in track
    block = _function_block(html, "pollLiveSessions")
    assert "catch (e)" in block
    assert "Live status refresh failed" in block
    assert "stopLiveTimersIfIdle" in block
