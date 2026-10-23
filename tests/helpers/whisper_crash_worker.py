"""Subprocess fixture: real CLI/checkpoint/export code, deterministic ASR model."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

from meeting_agent.transcription import faster_whisper_backend as backend
from meeting_agent.transcription.checkpoints import atomic_json

ROOT = Path(__file__).resolve().parents[2]


def main():
    meeting_dir = Path(sys.argv[1])
    mode = sys.argv[2]

    class Model:
        def transcribe(self, samples, **kwargs):
            index = round(float(samples[min(16000, len(samples) - 1)]) * 32768 / 1000) - 1
            with (meeting_dir / "calls.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"block": index}) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            if mode == "crash" and index == 1:
                atomic_json(meeting_dir / "ready.json", {"waiting": True})
                while True:
                    time.sleep(0.1)
            offset = 0 if index == 0 else 1
            segment = SimpleNamespace(start=offset + 0.05, end=offset + 0.9, text=f"piece{index}",
                words=[SimpleNamespace(start=offset + 0.05, end=offset + 0.9, word=f"piece{index}")])
            return iter([segment]), SimpleNamespace()

    backend.load_model = lambda config: Model()
    spec = importlib.util.spec_from_file_location("crash_transcribe", ROOT / "scripts/22_transcribe_meeting.py")
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    script.transcription_config = lambda: {}
    if mode == "export_failure":
        write = script.write_transcript_exports
        def fail_after_exports(*args, **kwargs):
            from meeting_agent.meetings.ingest_lock import IngestLockTimeoutError
            from meeting_agent.transcription.checkpoints import CheckpointStore
            try:
                with CheckpointStore(meeting_dir).lock():
                    raise AssertionError("CLI released its lock before publication")
            except IngestLockTimeoutError:
                pass
            write(*args, **kwargs)
            raise OSError("simulated publication crash")
        script.write_transcript_exports = fail_after_exports
    args = ["--meeting-dir", str(meeting_dir), "--engine", "faster-whisper",
            "--model", "test-model", "--whisper-block-seconds", "2",
            "--progress-path", "runtime/progress/test.json"]
    if mode in {"resume", "dry_run"}:
        args.append("--resume")
    if mode == "force":
        args.append("--force")
    if mode == "dry_run":
        args.append("--dry-run")
    return script.main_with_argv(args)


if __name__ == "__main__":
    raise SystemExit(main())
