from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def merge_resolved_turns(
    segments: Sequence[Mapping[str, Any]], *, max_gap_sec: float = 1.5
) -> list[dict[str, Any]]:
    if isinstance(max_gap_sec, bool) or not isinstance(max_gap_sec, (int, float)):
        raise ValueError("max_gap_sec must be numeric")
    if not 0 <= float(max_gap_sec) <= 30:
        raise ValueError("max_gap_sec must be between 0 and 30")
    turns: list[dict[str, Any]] = []
    for segment in segments:
        current = _new_turn(segment, len(turns))
        if turns and _can_merge(turns[-1], current, float(max_gap_sec)):
            _merge_into(turns[-1], current)
        else:
            turns.append(current)
    return turns


def render_resolved_turns_text(turns: Sequence[Mapping[str, Any]], *, markdown: bool = False) -> str:
    lines = ["# Resolved speaker transcript", ""] if markdown else []
    for turn in turns:
        start = _format_time(float(turn["start_sec"]))
        speaker = str(turn.get("speaker") or turn.get("speaker_label") or "SPEAKER_UNKNOWN")
        role = str(turn.get("speaker_role") or "").strip()
        who = f"{speaker} ({role})" if role else speaker
        prefix = f"- **[{start}] {who}:**" if markdown else f"[{start}] {who}:"
        lines.append(f"{prefix} {str(turn.get('text') or '').strip()}")
    return "\n".join(lines).rstrip() + "\n"


def _new_turn(segment: Mapping[str, Any], index: int) -> dict[str, Any]:
    segment_id = str(segment.get("segment_id") or "")
    if not segment_id:
        raise ValueError("resolved segment requires segment_id")
    start = segment.get("start_sec")
    end = segment.get("end_sec")
    return {
        "turn_id": f"turn-{index + 1:06d}",
        "segment_id": segment_id,
        "segment_ids": [segment_id],
        "utterance_ids": [segment_id],
        "start_sec": float(start) if start is not None else None,
        "end_sec": float(end) if end is not None else None,
        "speaker": segment.get("speaker"),
        "speaker_label": segment.get("speaker_label"),
        "speaker_role": segment.get("speaker_role"),
        "speaker_mapped": bool(segment.get("speaker_mapped")),
        "source": str(segment.get("source") or "MIX"),
        "text": str(segment.get("text") or "").strip(),
        "speaker_overridden": bool(segment.get("speaker_overridden")),
        "automatic_speaker_labels": [segment.get("automatic_speaker_label")]
        if segment.get("automatic_speaker_label")
        else [],
    }


def _can_merge(previous: Mapping[str, Any], current: Mapping[str, Any], max_gap: float) -> bool:
    previous_end = previous.get("end_sec")
    current_start = current.get("start_sec")
    if previous_end is None or current_start is None:
        return False
    gap = float(current_start) - float(previous_end)
    return (
        bool(previous.get("speaker_label"))
        and previous.get("speaker_label") != "SPEAKER_UNKNOWN"
        and previous.get("speaker_label") == current.get("speaker_label")
        and previous.get("source") == current.get("source")
        and 0 <= gap <= max_gap
    )


def _merge_into(target: dict[str, Any], current: Mapping[str, Any]) -> None:
    target["segment_ids"].extend(current["segment_ids"])
    target["utterance_ids"].extend(current["utterance_ids"])
    target["end_sec"] = current["end_sec"]
    target["text"] = " ".join(part for part in (target["text"], current["text"]) if part)
    target["speaker_overridden"] = bool(
        target["speaker_overridden"] or current["speaker_overridden"]
    )
    for label in current["automatic_speaker_labels"]:
        if label not in target["automatic_speaker_labels"]:
            target["automatic_speaker_labels"].append(label)


def _format_time(seconds: float) -> str:
    total = max(0, int(seconds))
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"
