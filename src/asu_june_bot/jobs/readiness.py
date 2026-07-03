"""Pipeline readiness map for one meeting (MA-MEETING-STAGE-READINESS, #114).

Read-only overlay over the existing stage catalog and preflights: for every
runnable stage it reports whether the stage is already ``done`` (its output
marker exists), ``ready`` to run, or ``blocked`` (a prerequisite artifact is
missing).  The UI consumes this map instead of guessing pipeline state from
files.

No filesystem paths appear in the returned payload — reasons are short
machine-readable tokens plus the human-readable preflight message (which is
path-free by design).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from asu_june_bot.jobs.runner import STAGE_COMMANDS, STAGE_METADATA

# Relative output markers proving a stage has already completed.
# Sources: scripts/21–29 output contracts (see each script's artifacts update).
_DONE_MARKERS: dict[str, str] = {
    "extract_audio": "source/audio_16k_mono.wav",
    "transcribe": "transcript/segments.jsonl",
    "diarize": "transcript/diarization.jsonl",
    "merge": "transcript/speaker_transcript.jsonl",
    "chunk": "transcript/chunks.jsonl",
    "enrich": "artifacts/enriched_chunks.jsonl",
    "analyze": "artifacts/summary.md",
    # "index" is detected via meeting.json rag.indexed_artifacts (see below).
}

# Short machine-readable block reasons per stage (issue #114 rules).
_BLOCK_TOKENS: dict[str, str] = {
    "extract_audio": "source_media_missing",
    "transcribe": "audio_missing",
    "diarize": "audio_missing",
    "merge": "transcript_missing",
    "chunk": "merged_transcript_missing",
    "enrich": "chunks_missing",
    "index": "enriched_chunks_missing",
    "analyze": "enriched_chunks_missing",
}

_AUDIO_MARKER = "source/audio_16k_mono.wav"


def _read_card(meeting_dir: Path) -> dict[str, Any]:
    card = meeting_dir / "meeting.json"
    try:
        data = json.loads(card.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001 — unreadable card treated as empty
        return {}


def _marker_exists(meeting_dir: Path, rel: str) -> bool:
    target = (meeting_dir / rel).resolve()
    try:
        target.relative_to(meeting_dir.resolve())
    except ValueError:
        return False
    return target.exists()


def _stage_done(stage: str, meeting_dir: Path, card: dict[str, Any]) -> bool:
    if stage == "index":
        rag = card.get("rag")
        indexed = rag.get("indexed_artifacts") if isinstance(rag, dict) else None
        return bool(indexed)
    marker = _DONE_MARKERS.get(stage)
    return bool(marker and _marker_exists(meeting_dir, marker))


def _stage_blocked_reason(stage: str, meeting_dir: Path) -> str | None:
    """Return the human-readable block detail, or None when runnable.

    Reuses runner preflights where they exist; transcribe/diarize add the
    readiness-level audio requirement (#114: no audio → blocked).
    """
    if stage in ("transcribe", "diarize") and not _marker_exists(meeting_dir, _AUDIO_MARKER):
        return "normalized audio not found; run extract_audio first"
    preflight = STAGE_COMMANDS.get(stage, {}).get("preflight")
    if preflight is not None:
        return preflight(meeting_dir)
    return None


def pipeline_readiness(meeting_id: str, meeting_dir: Path) -> dict[str, Any]:
    """Build the readiness map for all runnable stages of one meeting."""
    card = _read_card(meeting_dir)
    stages: list[dict[str, Any]] = []
    ordered = sorted(
        (s for s in STAGE_COMMANDS if s in STAGE_METADATA),
        key=lambda s: STAGE_METADATA[s]["order"],
    )
    last_error = card.get("last_error") if isinstance(card.get("last_error"), dict) else None
    failed_stage = str(last_error.get("stage")) if last_error else None
    for stage in ordered:
        meta = STAGE_METADATA[stage]
        done = _stage_done(stage, meeting_dir, card)
        block_detail = _stage_blocked_reason(stage, meeting_dir)
        if done:
            state, can_run = "done", False
            reason = "already_done"
            detail = "stage output already exists; re-run requires force"
        elif block_detail is not None:
            state, can_run = "blocked", False
            reason = _BLOCK_TOKENS.get(stage, "prerequisite_missing")
            detail = block_detail
        elif failed_stage == stage:
            # Previous run of this stage failed (#120); prerequisites are met,
            # so the stage can be retried right away.
            state, can_run = "ready_for_retry", True
            reason = "previous_failed"
            detail = str(last_error.get("message") or "previous run failed")
        else:
            state, can_run = "ready", True
            reason = None
            detail = None
        stages.append(
            {
                "stage": stage,
                "label": meta["label"],
                "state": state,
                "can_run": can_run,
                "reason": reason,
                "detail": detail,
                "required_artifacts": list(meta["requires"]),
                "produced_artifacts": list(meta["outputs"]),
                "order": meta["order"],
            }
        )
    return {
        "meeting_id": meeting_id,
        "status": card.get("status"),
        "stages": stages,
    }
