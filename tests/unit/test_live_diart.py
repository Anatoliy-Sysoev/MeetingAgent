from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path

import pytest

from meeting_agent.live_transcription.diart_client import (
    DiartClientError,
    DiartHttpClient,
    DiartSpeakerTurn,
    assign_diart_speakers,
    parse_diart_turns,
    write_diart_turns_atomic,
)
from meeting_agent.live_transcription.schema import LiveSegment


ROOT = Path(__file__).resolve().parents[2]


class _Response(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def _segment(start: float, end: float, *, source: str = "SYS") -> LiveSegment:
    return LiveSegment(
        segment_id="live-seg-000001",
        segment_index=1,
        start=start,
        end=end,
        text="Финальная реплика",
        source=source,
        engine="vosk",
    )


def test_client_accepts_only_loopback_http() -> None:
    assert DiartHttpClient("http://127.0.0.1:8765").base_url.endswith("8765")
    assert DiartHttpClient("http://localhost:8765/").base_url.endswith("8765")
    with pytest.raises(ValueError, match="loopback"):
        DiartHttpClient("http://diart-api:8765")
    with pytest.raises(ValueError, match="local HTTP"):
        DiartHttpClient("https://127.0.0.1:8765")


def test_client_sends_bounded_identity_and_parses_turns() -> None:
    captured: dict[str, object] = {}

    def opener(request, *, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("ascii"))
        captured["timeout"] = timeout
        return _Response(
            json.dumps(
                {
                    "ok": True,
                    "turns": [
                        {"speaker": "SPEAKER_01", "start": 2.0, "end": 3.0},
                        {"speaker": "SPEAKER_00", "start": 0.0, "end": 1.0},
                    ],
                }
            ).encode()
        )

    turns = DiartHttpClient(
        "http://127.0.0.1:8765",
        timeout_seconds=12,
        opener=opener,
    ).diarize("2026-07-15__test", "SYS")

    assert captured == {
        "url": "http://127.0.0.1:8765/v1/diarize",
        "body": {"meeting_id": "2026-07-15__test", "source": "SYS"},
        "timeout": 12.0,
    }
    assert [turn.speaker for turn in turns] == ["SPEAKER_00", "SPEAKER_01"]


@pytest.mark.parametrize(
    "payload",
    [
        {"ok": False, "turns": []},
        {"ok": True, "turns": "bad"},
        {"ok": True, "turns": [{"speaker": "admin", "start": 0, "end": 1}]},
        {"ok": True, "turns": [{"speaker": "SPEAKER_00", "start": 2, "end": 1}]},
    ],
)
def test_turn_parser_rejects_malformed_payload(payload: dict) -> None:
    with pytest.raises(DiartClientError):
        parse_diart_turns(payload)


def test_overlap_assignment_uses_largest_overlap_and_preserves_technical_source() -> None:
    segments = [_segment(1.0, 4.0), _segment(5.0, 6.0), _segment(0.0, 1.0, source="MIC")]
    turns = [
        DiartSpeakerTurn("SPEAKER_00", 0.0, 2.0),
        DiartSpeakerTurn("SPEAKER_01", 2.0, 4.5),
    ]

    assigned = assign_diart_speakers(segments, turns)

    assert assigned[0].metadata == {
        "speaker": "SPEAKER_01",
        "speaker_label": "SPEAKER_01",
        "speaker_source": "diart",
        "speaker_overlap_seconds": 2.0,
    }
    assert assigned[1].metadata == {}
    assert assigned[2].source == "MIC"
    assert assigned[2].metadata == {}


def test_turn_artifact_is_atomic_and_path_free(tmp_path: Path) -> None:
    path = tmp_path / "live_diarization.SYS.json"
    write_diart_turns_atomic(
        path,
        meeting_id="meeting-1",
        source="SYS",
        turns=[DiartSpeakerTurn("SPEAKER_00", 0.0, 1.0)],
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["turns"] == [{"speaker": "SPEAKER_00", "start": 0.0, "end": 1.0}]
    assert "path" not in json.dumps(payload).lower()
    assert not list(tmp_path.glob("*.tmp"))


def _load_sidecar_module():
    path = ROOT / "scripts" / "51_diart_service.py"
    spec = importlib.util.spec_from_file_location("meetingagent_diart_sidecar", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sidecar_safe_audio_path_rejects_traversal_and_accepts_expected_wav(tmp_path: Path) -> None:
    sidecar = _load_sidecar_module()
    root = tmp_path / "meetings"
    audio = root / "meeting-1" / "source" / "live_audio.SYS.wav"
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b"RIFF")
    assert sidecar._safe_audio_path(root, "meeting-1", "SYS") == audio.resolve()
    with pytest.raises(sidecar.DiartServiceError):
        sidecar._safe_audio_path(root, "../escape", "SYS")
    with pytest.raises(sidecar.DiartServiceError):
        sidecar._safe_audio_path(root, "meeting-1", "MIC")


def test_sidecar_normalizes_labels_by_first_timeline_appearance() -> None:
    sidecar = _load_sidecar_module()

    class Segment:
        def __init__(self, start: float, end: float) -> None:
            self.start = start
            self.end = end

    rows = sidecar._normalize_tracks(
        [
            (Segment(2.0, 3.0), None, "raw-b"),
            (Segment(0.0, 1.0), None, "raw-a"),
            (Segment(1.02, 2.0), None, "raw-a"),
        ]
    )
    assert rows == [
        {"speaker": "SPEAKER_00", "start": 0.0, "end": 2.0},
        {"speaker": "SPEAKER_01", "start": 2.0, "end": 3.0},
    ]
