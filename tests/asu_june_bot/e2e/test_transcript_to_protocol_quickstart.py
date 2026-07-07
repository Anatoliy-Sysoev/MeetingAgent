from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SAMPLE_DIR = ROOT / "examples" / "meeting_dataset" / "synthetic-support-handoff"


def _run(*args: str) -> None:
    result = subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _reset_runtime_card(meeting_dir: Path) -> None:
    card_path = meeting_dir / "meeting.json"
    card = json.loads(card_path.read_text(encoding="utf-8"))
    card["processing_status"] = "processing"
    card["artifacts"] = {}
    card["rag"] = {"index_policy": "do_not_index"}
    card_path.write_text(json.dumps(card, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_transcript_to_protocol_quickstart_on_public_sample(tmp_path: Path) -> None:
    meeting_dir = tmp_path / "2026-01-15__synthetic-support-handoff"
    shutil.copytree(SAMPLE_DIR, meeting_dir)
    _reset_runtime_card(meeting_dir)

    _run(
        "scripts/22_transcribe_meeting.py",
        "--meeting-dir",
        str(meeting_dir),
        "--engine",
        "from-segments",
        "--segments-path",
        str(SAMPLE_DIR / "transcript" / "segments.jsonl"),
        "--language",
        "en",
        "--force",
    )
    _run("scripts/24_merge_transcript_speakers.py", "--meeting-dir", str(meeting_dir), "--force")
    _run("scripts/26_chunk_meeting.py", "--meeting-dir", str(meeting_dir), "--force")
    _run("scripts/27_enrich_meeting_chunks.py", "--meeting-dir", str(meeting_dir), "--force")
    _run("scripts/29_analyze_meeting.py", "--meeting-dir", str(meeting_dir), "--mode", "extractive", "--force")

    protocol = (meeting_dir / "artifacts" / "protocol.md").read_text(encoding="utf-8")
    tasks = json.loads((meeting_dir / "artifacts" / "tasks.json").read_text(encoding="utf-8"))
    risks = json.loads((meeting_dir / "artifacts" / "risks.json").read_text(encoding="utf-8"))
    questions = json.loads((meeting_dir / "artifacts" / "open_questions.json").read_text(encoding="utf-8"))

    assert "Протокол встречи" in protocol
    assert (meeting_dir / "artifacts" / "summary.md").exists()
    assert tasks["items"]
    assert risks["items"]
    assert questions["items"]
    assert tasks["items"][0]["source_refs"][0]["timecode_start"]
