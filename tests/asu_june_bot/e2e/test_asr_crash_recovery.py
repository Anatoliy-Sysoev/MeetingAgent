from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import time
import wave
from pathlib import Path

from meeting_agent.jobs.readiness import _stage_done
from meeting_agent.transcription.publication import transcript_is_complete

ROOT = Path(__file__).resolve().parents[3]
WORKER = ROOT / "tests/helpers/whisper_crash_worker.py"


def make_meeting(root):
    directory = root / "2026-10-21__crash-test"
    (directory / "source").mkdir(parents=True)
    audio = directory / "source/audio_16k_mono.wav"
    with wave.open(str(audio), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        for index, seconds in enumerate((2, 2, 1)):
            handle.writeframes(struct.pack("<h", (index + 1) * 1000) * (seconds * 16000))
    card = dict(schema_version=1, meeting_id=directory.name, title="Synthetic crash test",
        date="2026-10-21", source={"kind": "offline_record", "media_files": [
            {"path": "source/audio_16k_mono.wav", "media_type": "audio"}]},
        processing_status="new", participants=[], artifacts={}, classification={}, links={},
        retention={"policy": "default"}, rag={"index_policy": "structured_artifacts_and_final_transcript"},
        created_at="2026-10-21T00:00:00Z", updated_at="2026-10-21T00:00:00Z")
    (directory / "meeting.json").write_text(json.dumps(card), encoding="utf-8")
    return directory


def launch(directory, mode):
    environment = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONUTF8": "1"}
    return subprocess.Popen([sys.executable, str(WORKER), str(directory), mode],
                            cwd=ROOT, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def finish(process, expected=0):
    try:
        out, error = process.communicate(timeout=40)
        assert process.returncode == expected, (out.decode("utf-8"), error.decode("utf-8"))
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)


def read_lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_actual_worker_termination_resumes_and_matches_uninterrupted_result(tmp_path):
    directory = make_meeting(tmp_path / "interrupted")
    process = launch(directory, "crash")
    try:
        deadline = time.monotonic() + 35
        while not (directory / "ready.json").exists() and time.monotonic() < deadline:
            if process.poll() is not None:
                finish(process)
                raise AssertionError("worker exited before crash point")
            time.sleep(0.05)
        assert (directory / "ready.json").exists(), "worker did not reach crash point"
        # Another CLI cannot overwrite a live attempt, even if called outside API.
        finish(launch(directory, "resume"), expected=1)
        assert len(read_lines(directory / "calls.jsonl")) == 2
        process.terminate()
        process.wait(timeout=10)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
    assert not (directory / "transcript/segments.jsonl").exists()
    assert not _stage_done("transcribe", directory, {})
    finish(launch(directory, "resume"))
    assert [line["block"] for line in read_lines(directory / "calls.jsonl")] == [0, 1, 1, 2]
    rows = read_lines(directory / "transcript/segments.jsonl")
    assert [line["start"] for line in rows] == [0.05, 2.05, 4.05]
    assert transcript_is_complete(directory)
    reference = make_meeting(tmp_path / "reference")
    finish(launch(reference, "normal"))
    assert rows == read_lines(reference / "transcript/segments.jsonl")


def test_export_failure_resumes_without_asr_and_dry_run_does_not_mutate(tmp_path):
    directory = make_meeting(tmp_path)
    finish(launch(directory, "export_failure"), expected=1)
    assert (directory / "transcript/segments.jsonl").exists()
    assert not _stage_done("transcribe", directory, {})
    before = {p.relative_to(directory): p.read_bytes() for p in directory.rglob("*") if p.is_file()}
    finish(launch(directory, "dry_run"))
    after = {p.relative_to(directory): p.read_bytes() for p in directory.rglob("*") if p.is_file()}
    assert before == after
    finish(launch(directory, "resume"))
    assert len(read_lines(directory / "calls.jsonl")) == 3
    assert transcript_is_complete(directory)
    report = json.loads((directory / "transcript/transcription_report.json").read_text(encoding="utf-8"))
    assert report["backend_metrics"]["blocks_reused"] == 3


def test_force_creates_new_generation_and_reprocesses_audio(tmp_path):
    directory = make_meeting(tmp_path)
    finish(launch(directory, "normal"))
    checkpoint = directory / "transcript/_whisper/manifest.json"
    first = json.loads(checkpoint.read_text(encoding="utf-8"))["generation"]
    finish(launch(directory, "force"))
    second = json.loads(checkpoint.read_text(encoding="utf-8"))["generation"]
    assert first != second
    assert (checkpoint.parent / first).is_dir()
    assert len(read_lines(directory / "calls.jsonl")) == 6
