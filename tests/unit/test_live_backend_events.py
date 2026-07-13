from __future__ import annotations

import json
import threading
import wave
from pathlib import Path

import meeting_agent.live_transcription.vosk_backend as backend
from meeting_agent.live_transcription.vosk_backend import VoskLiveConfig


class _PartialRecognizer:
    def __init__(self) -> None:
        self.index = 0

    def AcceptWaveform(self, _block: bytes) -> bool:
        self.index += 1
        return False

    def PartialResult(self) -> str:
        return json.dumps({"partial": f"draft {self.index}"})


def test_accept_block_bounds_partials_but_streams_each_event(tmp_path: Path) -> None:
    events: list[tuple[str, dict]] = []
    partials: list[dict] = []
    metrics: dict = {}
    config = VoskLiveConfig(
        model_path=tmp_path,
        partials_max=2,
        event_callback=lambda kind, payload: events.append((kind, payload)),
    )
    recognizer = _PartialRecognizer()

    for index in range(5):
        backend._accept_block(
            recognizer,
            b"\0\0" * 10,
            cursor_start=index * 0.1,
            cursor_end=(index + 1) * 0.1,
            config=config,
            model_label="test-model",
            segments=[],
            partials=partials,
            runtime_metrics=metrics,
        )

    assert [item["text"] for item in partials] == ["draft 4", "draft 5"]
    assert metrics["partials_dropped"] == 3
    assert [kind for kind, _payload in events] == ["partial"] * 5


def test_stop_event_exits_wav_capture_and_emits_final_result(
    tmp_path: Path,
    monkeypatch,
) -> None:
    model_path = tmp_path / "model"
    model_path.mkdir()
    wav_path = tmp_path / "input.wav"
    with wave.open(str(wav_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16_000)
        wav_file.writeframes(b"\0\0" * 16_000)

    stop_event = threading.Event()
    events: list[tuple[str, dict]] = []

    class FakeModel:
        def __init__(self, _path: str) -> None:
            pass

    class FakeRecognizer:
        def __init__(self, _model, _rate: float) -> None:
            pass

        def SetWords(self, _enabled: bool) -> None:
            pass

        def AcceptWaveform(self, _block: bytes) -> bool:
            return False

        def PartialResult(self) -> str:
            return '{"partial":"черновик"}'

        def FinalResult(self) -> str:
            return (
                '{"text":"финал","result":['
                '{"word":"финал","start":0.0,"end":0.2,"conf":0.9}]}'
            )

    monkeypatch.setattr(backend, "_load_vosk", lambda: (FakeRecognizer, FakeModel))

    def callback(kind: str, payload: dict) -> None:
        events.append((kind, payload))
        if kind == "partial":
            stop_event.set()

    result = backend.transcribe_vosk_live(
        VoskLiveConfig(
            model_path=model_path,
            input_wav=wav_path,
            block_ms=100,
            stop_event=stop_event,
            event_callback=callback,
        )
    )

    assert [kind for kind, _payload in events] == ["partial", "final"]
    assert result.metrics["stop_requested"] is True
    assert result.metrics["duration"] == 0.1
    assert result.segments[0].text == "финал"
