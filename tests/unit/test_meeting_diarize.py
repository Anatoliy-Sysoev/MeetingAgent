from __future__ import annotations

import argparse
import importlib.util
import json
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[2]


def load_script(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ingest = load_script("meeting_ingest_20_for_diarize", "scripts/20_ingest_meeting.py")
diarize23 = load_script("meeting_diarize_23", "scripts/23_diarize_meeting.py")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_meeting(meeting: dict) -> None:
    schema = read_json(REPO_ROOT / "configs" / "schemas" / "meeting.schema.json")
    Draft202012Validator(schema).validate(meeting)


def write_tiny_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 1600)


def make_meeting(tmp_path: Path) -> Path:
    source = tmp_path / "source.wav"
    write_tiny_wav(source)
    meetings_root = tmp_path / "meetings"
    ingest.run(
        argparse.Namespace(
            file=str(source),
            title="Diarize Smoke",
            date="2026-06-08",
            meeting_id=None,
            meetings_root=str(meetings_root),
            retention_policy="default",
            force=False,
        )
    )
    meeting_dir = meetings_root / "2026-06-08__diarize-smoke"
    normalized_audio = meeting_dir / "source" / "audio_16k_mono.wav"
    write_tiny_wav(normalized_audio)
    meeting = read_json(meeting_dir / "meeting.json")
    meeting["source"]["media_files"].append({"path": "source/audio_16k_mono.wav", "media_type": "audio"})
    (meeting_dir / "meeting.json").write_text(json.dumps(meeting, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return meeting_dir


def make_models_dir(tmp_path: Path) -> Path:
    models_dir = tmp_path / "models"
    (models_dir / "sherpa-onnx-pyannote-segmentation-3-0").mkdir(parents=True)
    (models_dir / "sherpa-onnx-pyannote-segmentation-3-0" / "model.onnx").write_bytes(b"fake")
    (models_dir / "wespeaker_en_voxceleb_resnet34_LM.onnx").write_bytes(b"fake")
    return models_dir


def make_args(meeting_dir: Path, models_dir: Path, *, dry_run: bool = True):
    return argparse.Namespace(
        meeting_dir=str(meeting_dir),
        backend="sherpa-onnx",
        audio_path=None,
        models_dir=str(models_dir),
        segmentation_model="sherpa-onnx-pyannote-segmentation-3-0/model.onnx",
        embedding_model="wespeaker_en_voxceleb_resnet34_LM.onnx",
        num_speakers=None,
        min_speakers=None,
        max_speakers=None,
        cluster_threshold=0.5,
        min_duration_on=0.3,
        min_duration_off=0.5,
        num_threads=1,
        force=False,
        dry_run=dry_run,
    )


def test_diarize_dry_run_does_not_mutate_meeting(
    tmp_path: Path, monkeypatch
) -> None:
    meeting_dir = make_meeting(tmp_path)
    models_dir = make_models_dir(tmp_path)
    before = read_json(meeting_dir / "meeting.json")
    monkeypatch.setattr(diarize23, "validate_runtime_config", lambda _config: None)

    code = diarize23.run(make_args(meeting_dir, models_dir, dry_run=True))

    assert code == 0
    after = read_json(meeting_dir / "meeting.json")
    validate_meeting(after)
    assert after == before
    assert not (meeting_dir / "transcript" / "diarization.jsonl").exists()


def test_diarize_dry_run_checks_runtime_dependencies(
    tmp_path: Path, monkeypatch
) -> None:
    meeting_dir = make_meeting(tmp_path)
    models_dir = make_models_dir(tmp_path)

    def fail_runtime(_config) -> None:
        raise diarize23.SherpaDiarizationError(
            "sherpa-onnx diarization dependencies are not installed (sherpa_onnx)."
        )

    monkeypatch.setattr(diarize23, "validate_runtime_config", fail_runtime)

    try:
        diarize23.run(make_args(meeting_dir, models_dir, dry_run=True))
    except diarize23.DiarizeMeetingError as exc:
        assert exc.stage == "preflight"
        assert "dependencies are not installed" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("dry-run must fail when runtime dependencies are missing")

    after = read_json(meeting_dir / "meeting.json")
    validate_meeting(after)
    assert after["processing_status"] == "new"
    assert not (meeting_dir / "transcript" / "diarization.jsonl").exists()


def test_diarize_real_run_validates_runtime_and_publishes_outputs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    meeting_dir = make_meeting(tmp_path)
    models_dir = make_models_dir(tmp_path)
    validated = []

    def validate_runtime(config) -> None:
        validated.append(config)

    fake_report = SimpleNamespace(
        backend="sherpa-onnx",
        to_dict=lambda: {"backend": "sherpa-onnx", "warnings": []},
    )
    fake_result = SimpleNamespace(intervals=[], report=fake_report)
    monkeypatch.setattr(diarize23, "validate_runtime_config", validate_runtime)
    monkeypatch.setattr(diarize23, "diarize_wav", lambda _audio, _config: fake_result)

    code = diarize23.run(make_args(meeting_dir, models_dir, dry_run=False))

    assert code == 0
    assert len(validated) == 1
    assert (meeting_dir / "transcript" / "diarization.jsonl").read_text(
        encoding="utf-8"
    ) == ""
    report = read_json(meeting_dir / "transcript" / "diarization_report.json")
    assert report == {
        "backend": "sherpa-onnx",
        "warnings": [],
        "requested_num_speakers": None,
        "actual_num_speakers": 0,
    }
    meeting = read_json(meeting_dir / "meeting.json")
    validate_meeting(meeting)
    assert meeting["artifacts"]["diarization"] == "transcript/diarization.jsonl"
    assert meeting["diarization_summary"] == {
        "requested_num_speakers": None,
        "actual_num_speakers": 0,
        "backend": "sherpa-onnx",
        "updated_at": meeting["diarization_summary"]["updated_at"],
    }


def test_diarize_cli_rejects_out_of_range_speaker_count() -> None:
    with pytest.raises(SystemExit):
        diarize23.parse_args(["--meeting-dir", "meeting", "--num-speakers", "21"])
