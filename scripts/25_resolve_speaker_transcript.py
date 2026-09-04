#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from meeting_agent.meetings.service import MeetingsService  # noqa: E402
from meeting_agent.speakers.rebuild import (  # noqa: E402
    ensure_source_revision,
    mark_stage_revision,
    speaker_curation_requested,
)


class ResolveSpeakerTranscriptError(RuntimeError):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    _atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def _atomic_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    content = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    _atomic_text(path, content)


def _timecode(seconds: float | None) -> str:
    total = max(0, int(seconds or 0))
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


def _render(rows: list[dict[str, Any]], *, markdown: bool) -> str:
    lines = ["# Curated speaker transcript", ""] if markdown else []
    for row in rows:
        display = row.get("speaker_name") or row["speaker"]
        role = str(row.get("speaker_role") or "").strip()
        company = str(row.get("speaker_company") or "").strip()
        suffix = ", ".join(value for value in (role, company) if value)
        if suffix:
            display = f"{display} ({suffix})"
        lines.append(f"[{_timecode(row['start'])}] {display}: {row['text']}")
    return "\n".join(lines).rstrip() + "\n"


def run(meeting_dir: Path) -> int:
    meeting_dir = meeting_dir.resolve()
    card_path = meeting_dir / "meeting.json"
    if not card_path.is_file():
        raise ResolveSpeakerTranscriptError("meeting.json not found")
    card = json.loads(card_path.read_text(encoding="utf-8"))
    if not isinstance(card, dict):
        raise ResolveSpeakerTranscriptError("meeting.json root must be an object")
    meeting_id = str(card.get("meeting_id") or "")
    if meeting_dir.name != meeting_id:
        raise ResolveSpeakerTranscriptError("meeting directory does not match meeting_id")

    service = MeetingsService(meetings_root=meeting_dir.parent)
    transcript = service.get_transcript_segments(meeting_id)
    if transcript is None or not transcript.get("segments"):
        raise ResolveSpeakerTranscriptError("speaker transcript is unavailable")
    overrides = service.get_speaker_overrides(meeting_id) or {}
    current_overrides = overrides.get("current") or {}
    track_revision = speaker_curation_requested(card, current_overrides)
    if track_revision:
        ensure_source_revision(
            card,
            meeting_dir=meeting_dir,
            overrides=current_overrides,
        )
    mapping = card.get("speaker_mapping")
    mapping = mapping if isinstance(mapping, dict) else {}
    rows: list[dict[str, Any]] = []
    for item in transcript["segments"]:
        label = str(item.get("speaker_label") or "SPEAKER_UNKNOWN")
        mapped = mapping.get(label) if isinstance(mapping.get(label), dict) else {}
        rows.append(
            {
                "utterance_id": str(item["segment_id"]),
                "segment_id": str(item["segment_id"]),
                "speaker": label,
                "automatic_speaker": str(
                    item.get("automatic_speaker_label") or label
                ),
                "speaker_overridden": bool(item.get("speaker_overridden")),
                "speaker_name": str(mapped.get("name") or label),
                "speaker_role": str(mapped.get("role") or ""),
                "speaker_company": str(mapped.get("company") or ""),
                "source": str(item.get("source") or "MIX"),
                "start": float(item.get("start_sec") or 0.0),
                "end": float(item.get("end_sec") or item.get("start_sec") or 0.0),
                "text": str(item.get("text") or "").strip(),
            }
        )
    rows = [row for row in rows if row["text"]]
    if not rows:
        raise ResolveSpeakerTranscriptError("resolved transcript has no text")

    transcript_dir = meeting_dir / "transcript"
    jsonl_path = transcript_dir / "resolved_speaker_transcript.jsonl"
    txt_path = transcript_dir / "resolved_speaker_transcript.txt"
    md_path = transcript_dir / "resolved_speaker_transcript.md"
    _atomic_jsonl(jsonl_path, rows)
    _atomic_text(txt_path, _render(rows, markdown=False))
    _atomic_text(md_path, _render(rows, markdown=True))

    artifacts = card.get("artifacts")
    artifacts = dict(artifacts) if isinstance(artifacts, dict) else {}
    artifacts.update(
        {
            "resolved_speaker_transcript": "transcript/resolved_speaker_transcript.jsonl",
            "resolved_speaker_transcript_txt": "transcript/resolved_speaker_transcript.txt",
            "resolved_speaker_transcript_md": "transcript/resolved_speaker_transcript.md",
        }
    )
    card["artifacts"] = artifacts
    card["processing_status"] = "processing"
    card["updated_at"] = _now_iso()
    card.pop("last_error", None)
    if track_revision:
        mark_stage_revision(card, "resolve_speakers")
    schema = json.loads(
        (ROOT / "configs" / "schemas" / "meeting.schema.json").read_text(encoding="utf-8")
    )
    jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(card)
    _atomic_json(card_path, card)
    print("resolved speaker transcript complete")
    print(f"utterances: {len(rows)}")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Materialize curated speaker labels without changing raw ASR/diarization."
    )
    parser.add_argument("--meeting-dir", required=True)
    return parser.parse_args(argv)


def main() -> int:
    try:
        return run(Path(parse_args(sys.argv[1:]).meeting_dir))
    except Exception as exc:
        print(f"ERROR[resolve_speakers]: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
