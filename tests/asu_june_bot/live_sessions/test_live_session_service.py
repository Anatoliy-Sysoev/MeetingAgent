from __future__ import annotations

import json
import threading
import time
import wave
from pathlib import Path

import pytest

from asu_june_bot.live_sessions import (
    LiveSessionConflict,
    LiveSessionError,
    LiveSessionService,
)
from asu_june_bot.live_sessions.store import LiveSessionStore, LiveSessionStoreError
from asu_june_bot.meetings.service import MeetingsService
from meeting_agent.live_transcription.audio_capture import AudioDevice, AudioSourcePreflight
from meeting_agent.live_transcription.schema import LiveSegment
from meeting_agent.live_transcription.vosk_backend import VoskLiveResult


MEETING_ID = "2026-07-13__live-test"


def _meeting(root: Path, meeting_id: str = MEETING_ID) -> Path:
    meeting_dir = root / meeting_id
    meeting_dir.mkdir(parents=True)
    card = {
        "schema_version": 1,
        "meeting_id": meeting_id,
        "title": "Live test",
        "processing_status": "new",
        "source": {"kind": "live_session"},
        "artifacts": {},
        "rag": {"index_policy": "structured_artifacts_and_final_transcript"},
    }
    (meeting_dir / "meeting.json").write_text(
        json.dumps(card, ensure_ascii=False),
        encoding="utf-8",
    )
    return meeting_dir


def _model(root: Path) -> Path:
    path = root / "models" / "vosk-model-small-ru-0.22"
    path.mkdir(parents=True, exist_ok=True)
    (path / "am").mkdir(exist_ok=True)
    (path / "conf").mkdir(exist_ok=True)
    (path / "graph").mkdir(exist_ok=True)
    (path / "am" / "final.mdl").touch()
    (path / "conf" / "model.conf").touch()
    (path / "graph" / "HCLG.fst").touch()
    return path


def _available_preflight(source: str, **_kwargs) -> AudioSourcePreflight:
    return AudioSourcePreflight(
        source=source,
        available=True,
        device_available=True,
        capture_supported=True,
        devices=[
            AudioDevice(
                index=7,
                name=r"C:\Users\private\Microphone",
                hostapi="private-host-api",
                max_input_channels=2,
                max_output_channels=0,
                default_samplerate=48_000,
            )
        ],
    )


class _BlockingTranscriber:
    def __init__(self, *, partial_count: int = 1, fail: bool = False) -> None:
        self.started = threading.Event()
        self.partial_count = partial_count
        self.fail = fail

    def __call__(self, config) -> VoskLiveResult:
        self.started.set()
        for index in range(self.partial_count):
            config.event_callback(
                "partial",
                {"text": f"draft {index}", "start": index * 0.1, "end": index * 0.1 + 0.1},
            )
        if self.fail:
            raise RuntimeError(r"private failure at C:\Users\private\model.bin")
        segment = LiveSegment(
            segment_id="live-seg-000000",
            segment_index=0,
            start=0.0,
            end=1.0,
            text="Финальная реплика",
            source=config.source,
            engine="vosk",
            model=config.model_path.name,
            confidence=0.9,
        )
        config.event_callback("final", segment.to_dict())
        assert config.stop_event is not None
        config.stop_event.wait(timeout=5)
        assert config.audio_archive_path is not None
        config.audio_archive_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(config.audio_archive_path), "wb") as archive:
            archive.setnchannels(1)
            archive.setsampwidth(2)
            archive.setframerate(config.sample_rate)
            archive.writeframes(b"\x00\x00" * config.sample_rate)
        return VoskLiveResult(
            segments=[segment],
            partials=[{"text": "draft", "source": config.source}],
            metrics={"duration": 1.0, "elapsed_seconds": 0.1, "stop_requested": True},
            audio_archive_path=config.audio_archive_path,
        )


def _service(
    tmp_path: Path,
    *,
    transcriber=None,
    state_path: Path | None = None,
    events_max: int = 20,
    active_sessions_max: int = 2,
) -> LiveSessionService:
    return LiveSessionService(
        meetings_root=tmp_path / "meetings",
        state_path=state_path or tmp_path / "runtime" / "live.json",
        model_path=_model(tmp_path),
        events_max=events_max,
        active_sessions_max=active_sessions_max,
        stop_timeout_seconds=2,
        transcriber=transcriber or _BlockingTranscriber(),
        source_preflight=_available_preflight,
    )


def _wait_status(service: LiveSessionService, session_id: str, expected: str) -> dict:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        record = service.get(MEETING_ID, session_id)
        if record["status"] == expected:
            return record
        time.sleep(0.01)
    raise AssertionError(f"session did not reach {expected}")


def test_preflight_is_path_free_and_hides_raw_device_diagnostics(tmp_path: Path) -> None:
    _meeting(tmp_path / "meetings")
    service = _service(tmp_path)
    try:
        payload = service.preflight("MIC", audio_device_index=7)
    finally:
        service.shutdown()

    assert payload == {
        "source": "MIC",
        "available": True,
        "reason": None,
        "model_ready": True,
        "devices": [{"device_index": 7, "label": "Audio device 7"}],
        "devices_truncated": False,
    }
    serialized = json.dumps(payload)
    assert "Users" not in serialized
    assert "hostapi" not in serialized
    assert "48000" not in serialized


def test_preflight_rejects_empty_model_directory(tmp_path: Path) -> None:
    _meeting(tmp_path / "meetings")
    model_path = tmp_path / "empty-model"
    model_path.mkdir()
    service = LiveSessionService(
        meetings_root=tmp_path / "meetings",
        state_path=tmp_path / "runtime" / "live.json",
        model_path=model_path,
        source_preflight=_available_preflight,
    )
    try:
        payload = service.preflight("MIC")
    finally:
        service.shutdown()

    assert payload["available"] is False
    assert payload["model_ready"] is False
    assert payload["reason"] == "model_missing"


def test_preflight_hides_raw_backend_exception(tmp_path: Path) -> None:
    _meeting(tmp_path / "meetings")

    def broken_preflight(_source: str, **_kwargs):
        raise RuntimeError(r"device failed at C:\Users\private\driver.dll")

    service = LiveSessionService(
        meetings_root=tmp_path / "meetings",
        state_path=tmp_path / "runtime" / "live.json",
        model_path=_model(tmp_path),
        source_preflight=broken_preflight,
    )
    try:
        payload = service.preflight("MIC")
    finally:
        service.shutdown()

    assert payload["available"] is False
    assert payload["reason"] == "source_preflight_failed"
    assert "Users" not in json.dumps(payload)


def test_public_record_sanitizes_durable_diagnostics() -> None:
    public = LiveSessionService._public_record(
        {
            "session_id": "session",
            "meeting_id": MEETING_ID,
            "source": "MIC",
            "status": "failed",
            "engine": "unexpected-engine",
            "model": r"C:\Users\private\model",
            "vad": "unexpected-vad",
            "created_at": "2026-07-13T10:00:00+00:00",
            "updated_at": "2026-07-13T10:00:00+00:00",
            "warnings": [r"failed at C:\Users\private\device", "mic_audio_dropped"],
            "error": {
                "code": "INVALID CODE",
                "message": r"failed at C:\Users\private\model.bin",
            },
            "artifact_keys": ["live_report_mic", r"C:\private\file"],
            "last_event_id": 3,
        }
    )

    serialized = json.dumps(public)
    assert "Users" not in serialized
    assert public["engine"] is None
    assert public["model"] is None
    assert public["vad"] is None
    assert public["warnings"] == ["mic_audio_dropped"]
    assert public["error"] == {
        "code": "live_session_failed",
        "message": "Live transcription failed",
    }
    assert public["artifact_keys"] == ["live_report_mic"]


def test_live_service_accepts_general_safe_meeting_ids(tmp_path: Path) -> None:
    meeting_id = "sample_meeting"
    _meeting(tmp_path / "meetings", meeting_id=meeting_id)
    service = _service(tmp_path)
    try:
        service.ensure_meeting(meeting_id)
    finally:
        service.shutdown()


def test_live_service_rejects_meeting_card_identity_mismatch(tmp_path: Path) -> None:
    meeting_dir = _meeting(tmp_path / "meetings")
    card = json.loads((meeting_dir / "meeting.json").read_text(encoding="utf-8"))
    card["meeting_id"] = "another-meeting"
    (meeting_dir / "meeting.json").write_text(json.dumps(card), encoding="utf-8")
    service = _service(tmp_path)
    try:
        with pytest.raises(LiveSessionError, match="Meeting card is invalid"):
            service.start(MEETING_ID, source="MIC")
    finally:
        service.shutdown()


def test_start_stop_finalizes_artifacts_and_meeting_card(tmp_path: Path) -> None:
    meeting_dir = _meeting(tmp_path / "meetings")
    transcriber = _BlockingTranscriber()
    service = _service(tmp_path, transcriber=transcriber)
    try:
        started = service.start(MEETING_ID, source="MIC")
        assert transcriber.started.wait(timeout=1)
        stopped = service.stop(MEETING_ID, started["session_id"])
        assert stopped["status"] == "completed"

        events = service.events(MEETING_ID, started["session_id"])
        assert [event["type"] for event in events["events"]].count("final") == 1
        assert events["events"][-1]["status"] == "completed"

        card = json.loads((meeting_dir / "meeting.json").read_text(encoding="utf-8"))
        assert card["processing_status"] == "processing"
        assert card["source"]["audio_tracks"] == ["MIC"]
        assert "live_segments_mic" in card["artifacts"]
        assert card["artifacts"]["live_segments_mic"].startswith("transcript/live/")
        assert card["artifacts"]["live_segments_mic"] in card["rag"]["no_index_artifacts"]
        assert (meeting_dir / card["artifacts"]["live_report_mic"]).is_file()
        assert card["artifacts"]["live_report_mic"] in card["rag"]["no_index_artifacts"]
        assert card["artifacts"]["live_audio_mic"] == "source/live_audio.MIC.wav"
        assert card["artifacts"]["live_audio_mic"] in card["rag"]["no_index_artifacts"]
        assert card["source"]["media_files"] == [
            {
                "path": "source/live_audio.MIC.wav",
                "media_type": "audio",
                "duration_seconds": 1.0,
            }
        ]
        with wave.open(str(meeting_dir / card["artifacts"]["live_audio_mic"]), "rb") as audio:
            assert audio.getnchannels() == 1
            assert audio.getsampwidth() == 2
            assert audio.getframerate() == 16_000
            assert audio.getnframes() == 16_000
        media = MeetingsService(
            meetings_root=tmp_path / "meetings"
        ).list_media(MEETING_ID)
        assert media == [
            {
                "media_id": "0",
                "filename": "live_audio.MIC.wav",
                "media_type": "audio/wav",
                "size_bytes": 32_044,
                "sha256": None,
                "duration_sec": 1.0,
                "view_url": f"/meetings/{MEETING_ID}/media/0",
            }
        ]
        assert "Users" not in json.dumps(media)
    finally:
        service.shutdown()


def test_missing_audio_archive_fails_without_registering_media(tmp_path: Path) -> None:
    meeting_dir = _meeting(tmp_path / "meetings")

    def transcriber(_config) -> VoskLiveResult:
        return VoskLiveResult(segments=[], partials=[], metrics={"duration": 0.0})

    service = _service(tmp_path, transcriber=transcriber)
    try:
        started = service.start(MEETING_ID, source="MIC")
        failed = _wait_status(service, started["session_id"], "failed")
        assert failed["error"] == {
            "code": "live_session_failed",
            "message": "Live transcription failed",
        }
        card = json.loads((meeting_dir / "meeting.json").read_text(encoding="utf-8"))
        assert card["processing_status"] == "failed"
        assert "media_files" not in card["source"]
        assert "live_audio_mic" not in card["artifacts"]
    finally:
        service.shutdown()


def test_sys_capture_registers_separate_audio_archive(tmp_path: Path) -> None:
    meeting_dir = _meeting(tmp_path / "meetings")
    transcriber = _BlockingTranscriber()
    service = _service(tmp_path, transcriber=transcriber)
    try:
        started = service.start(MEETING_ID, source="SYS")
        assert transcriber.started.wait(timeout=1)
        service.stop(MEETING_ID, started["session_id"])

        card = json.loads((meeting_dir / "meeting.json").read_text(encoding="utf-8"))
        assert card["source"]["audio_tracks"] == ["SYS"]
        assert card["artifacts"]["live_audio_sys"] == "source/live_audio.SYS.wav"
        assert card["source"]["media_files"][0]["path"] == "source/live_audio.SYS.wav"
        assert (meeting_dir / "source" / "live_audio.SYS.wav").is_file()
    finally:
        service.shutdown()


def test_force_recapture_replaces_media_entry_without_duplicates(tmp_path: Path) -> None:
    meeting_dir = _meeting(tmp_path / "meetings")
    first = _BlockingTranscriber()
    service = _service(tmp_path, transcriber=first)
    try:
        started = service.start(MEETING_ID, source="MIC")
        assert first.started.wait(timeout=1)
        service.stop(MEETING_ID, started["session_id"])

        card_path = meeting_dir / "meeting.json"
        card = json.loads(card_path.read_text(encoding="utf-8"))
        refinement_rel = "transcript/live/refinement.MIC.json"
        refinement_path = meeting_dir / refinement_rel
        refinement_path.write_text("{}", encoding="utf-8")
        card["artifacts"]["live_refinement_mic"] = refinement_rel
        card["rag"]["no_index_artifacts"].append(refinement_rel)
        card["live_refinements"] = {
            "MIC": {
                "source": "MIC",
                "state": "final",
                "offline_engine": "faster-whisper",
                "offline_model": "large-v3-turbo",
                "started_at": "2026-07-13T10:00:00+00:00",
                "finished_at": "2026-07-13T10:01:00+00:00",
                "report_artifact_key": "live_refinement_mic",
            }
        }
        card_path.write_text(json.dumps(card), encoding="utf-8")

        second = _BlockingTranscriber()
        service.transcriber = second
        restarted = service.start(MEETING_ID, source="MIC", force=True)
        assert second.started.wait(timeout=1)
        service.stop(MEETING_ID, restarted["session_id"])

        card = json.loads((meeting_dir / "meeting.json").read_text(encoding="utf-8"))
        paths = [item["path"] for item in card["source"]["media_files"]]
        assert paths == ["source/live_audio.MIC.wav"]
        assert card["rag"]["no_index_artifacts"].count(
            "source/live_audio.MIC.wav"
        ) == 1
        assert "live_refinements" not in card
        assert "live_refinement_mic" not in card["artifacts"]
        assert refinement_rel not in card["rag"]["no_index_artifacts"]
        assert not refinement_path.exists()
    finally:
        service.shutdown()


def test_live_success_does_not_hide_unrelated_pipeline_failure(tmp_path: Path) -> None:
    meeting_dir = _meeting(tmp_path / "meetings")
    card_path = meeting_dir / "meeting.json"
    card = json.loads(card_path.read_text(encoding="utf-8"))
    card["processing_status"] = "failed"
    card["last_error"] = {
        "stage": "diarize",
        "code": "diarization_runtime_missing",
        "message": "Diarization runtime is not ready",
        "timestamp": "2026-07-13T09:00:00+00:00",
    }
    card_path.write_text(json.dumps(card), encoding="utf-8")
    transcriber = _BlockingTranscriber()
    service = _service(tmp_path, transcriber=transcriber)
    try:
        started = service.start(MEETING_ID, source="MIC")
        assert transcriber.started.wait(timeout=1)
        service.stop(MEETING_ID, started["session_id"])
        updated = json.loads(card_path.read_text(encoding="utf-8"))
        assert updated["processing_status"] == "failed"
        assert updated["last_error"]["stage"] == "diarize"
        assert updated["last_error"]["code"] == "diarization_runtime_missing"
    finally:
        service.shutdown()


def test_duplicate_session_is_rejected_until_worker_finishes(tmp_path: Path) -> None:
    _meeting(tmp_path / "meetings")
    transcriber = _BlockingTranscriber()
    service = _service(tmp_path, transcriber=transcriber)
    try:
        first = service.start(MEETING_ID, source="MIC")
        assert transcriber.started.wait(timeout=1)
        with pytest.raises(LiveSessionConflict, match="already active"):
            service.start(MEETING_ID, source="MIC")
        service.stop(MEETING_ID, first["session_id"])
    finally:
        service.shutdown()


def test_global_capacity_returns_stable_public_conflict(tmp_path: Path) -> None:
    _meeting(tmp_path / "meetings")
    second_meeting = "2026-07-13__second-live-test"
    _meeting(tmp_path / "meetings", meeting_id=second_meeting)
    transcriber = _BlockingTranscriber()
    service = _service(
        tmp_path,
        transcriber=transcriber,
        active_sessions_max=1,
    )
    try:
        first = service.start(MEETING_ID, source="MIC")
        assert transcriber.started.wait(timeout=1)
        with pytest.raises(LiveSessionConflict) as raised:
            service.start(second_meeting, source="MIC")
        assert raised.value.code == "live_session_capacity"
        assert raised.value.public_message == "Live session capacity is reached"
        service.stop(MEETING_ID, first["session_id"])
    finally:
        service.shutdown()


def test_events_are_bounded_and_partial_events_are_not_durable(tmp_path: Path) -> None:
    _meeting(tmp_path / "meetings")
    transcriber = _BlockingTranscriber(partial_count=25)
    service = _service(tmp_path, transcriber=transcriber, events_max=10)
    try:
        started = service.start(MEETING_ID, source="MIC")
        assert transcriber.started.wait(timeout=1)
        service.stop(MEETING_ID, started["session_id"])
        payload = service.events(MEETING_ID, started["session_id"], after=0, limit=10)
        assert len(payload["events"]) <= 10
        assert payload["truncated"] is True
        assert payload["partial_events_durable"] is False
        durable = service.store.load()["sessions"][0]
        assert all(event["type"] != "partial" for event in durable["events"])
        assert any(event["type"] == "final" for event in durable["events"])
    finally:
        service.shutdown()


def test_restart_marks_active_session_stale_and_updates_card(tmp_path: Path) -> None:
    meeting_dir = _meeting(tmp_path / "meetings")
    state_path = tmp_path / "runtime" / "live.json"
    store = LiveSessionStore(state_path, events_max=20)
    store.reserve(
        {
            "session_id": "stale-session",
            "meeting_id": MEETING_ID,
            "source": "MIC",
            "status": "running",
            "created_at": "2026-07-13T10:00:00+00:00",
            "started_at": "2026-07-13T10:00:00+00:00",
            "updated_at": "2026-07-13T10:00:00+00:00",
            "finished_at": None,
            "last_event_id": 1,
            "events": [{"event_id": 1, "type": "status", "timestamp": "2026-07-13T10:00:00+00:00", "status": "running"}],
            "warnings": [],
            "error": None,
            "artifact_keys": [],
        }
    )

    service = _service(tmp_path, state_path=state_path)
    try:
        recovered = service.get(MEETING_ID, "stale-session")
        assert recovered["status"] == "stale"
        assert recovered["error"]["code"] == "api_restart"
        card = json.loads((meeting_dir / "meeting.json").read_text(encoding="utf-8"))
        assert card["processing_status"] == "processing"
        assert card["last_error"]["code"] == "api_restart"
        assert "\\" not in json.dumps(card["last_error"])
    finally:
        service.shutdown()


def test_worker_failure_never_exposes_raw_exception_path(tmp_path: Path) -> None:
    meeting_dir = _meeting(tmp_path / "meetings")
    service = _service(tmp_path, transcriber=_BlockingTranscriber(fail=True))
    try:
        started = service.start(MEETING_ID, source="MIC")
        failed = _wait_status(service, started["session_id"], "failed")
        serialized = json.dumps(failed)
        assert "Users" not in serialized
        assert failed["error"] == {
            "code": "live_session_failed",
            "message": "Live transcription failed",
        }
        card = json.loads((meeting_dir / "meeting.json").read_text(encoding="utf-8"))
        assert card["last_error"]["message"] == "Live transcription failed"
    finally:
        service.shutdown()


def test_shutdown_never_rolls_terminal_status_back_to_stopping(tmp_path: Path) -> None:
    _meeting(tmp_path / "meetings")
    transcriber = _BlockingTranscriber()
    service = _service(tmp_path, transcriber=transcriber)
    started = service.start(MEETING_ID, source="MIC")
    assert transcriber.started.wait(timeout=1)
    service._set_status(started["session_id"], "completed")

    service.shutdown()

    assert service.get(MEETING_ID, started["session_id"])["status"] == "completed"


def test_only_one_service_process_can_own_a_state_file(tmp_path: Path) -> None:
    _meeting(tmp_path / "meetings")
    state_path = tmp_path / "runtime" / "live.json"
    first = _service(tmp_path, state_path=state_path)
    try:
        with pytest.raises(LiveSessionStoreError, match="already owns"):
            _service(tmp_path, state_path=state_path)
    finally:
        first.shutdown()

    replacement = _service(tmp_path, state_path=state_path)
    replacement.shutdown()
