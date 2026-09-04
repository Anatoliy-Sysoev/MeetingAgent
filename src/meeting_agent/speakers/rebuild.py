from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SPEAKER_REBUILD_STAGES = (
    "resolve_speakers",
    "chunk",
    "enrich",
    "index",
    "analyze",
    "index_artifacts",
)

_STAGE_REVISION_KEYS = {
    "resolve_speakers": "resolved_revision",
    "chunk": "chunks_revision",
    "enrich": "enriched_revision",
    "index": "chunk_index_revision",
    "analyze": "analysis_revision",
    "index_artifacts": "artifact_index_revision",
}

_STAGE_PREREQUISITE_KEYS = {
    "chunk": ("resolved_revision",),
    "enrich": ("chunks_revision",),
    "index": ("enriched_revision",),
    "analyze": ("enriched_revision",),
    "index_artifacts": (
        "chunk_index_revision",
        "analysis_revision",
    ),
}

_CHUNK_INDEX_MARKERS = {
    "transcript/chunks.jsonl",
    "artifacts/enriched_chunks.jsonl",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as fh:
            while block := fh.read(1024 * 1024):
                digest.update(block)
    except OSError:
        digest.update(b"missing")
    return digest.hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def compute_source_revision(
    meeting_dir: Path,
    card: Mapping[str, Any],
    overrides: Mapping[str, Any] | None,
) -> str:
    """Hash every input that can change resolved speaker attribution."""
    artifacts = card.get("artifacts")
    artifact_map = artifacts if isinstance(artifacts, Mapping) else {}
    raw_rel = str(
        artifact_map.get("speaker_transcript")
        or "transcript/speaker_transcript.jsonl"
    ).replace("\\", "/")
    rel_path = Path(raw_rel)
    raw_path = meeting_dir / "__invalid_speaker_transcript_path__"
    if not rel_path.is_absolute() and ".." not in rel_path.parts:
        candidate = (meeting_dir / rel_path).resolve()
        try:
            candidate.relative_to(meeting_dir.resolve())
            raw_path = candidate
        except ValueError:
            pass
    payload = {
        "speaker_mapping": card.get("speaker_mapping")
        if isinstance(card.get("speaker_mapping"), Mapping)
        else {},
        "overrides": overrides if isinstance(overrides, Mapping) else {},
        "raw_speaker_transcript_sha256": _file_sha256(raw_path),
    }
    return hashlib.sha256(_canonical(payload)).hexdigest()


def speaker_curation_requested(
    card: Mapping[str, Any],
    overrides: Mapping[str, Any] | None,
) -> bool:
    """Return whether revision tracking is relevant for this meeting."""
    mapping = card.get("speaker_mapping")
    return bool(
        isinstance(card.get("speaker_curation"), Mapping)
        or (isinstance(mapping, Mapping) and mapping)
        or (isinstance(overrides, Mapping) and overrides)
    )


def mark_speaker_inputs_changed(
    card: dict[str, Any],
    *,
    meeting_dir: Path,
    overrides: Mapping[str, Any] | None,
) -> str:
    """Mark all speaker-dependent outputs stale without deleting raw evidence."""
    revision = compute_source_revision(meeting_dir, card, overrides)
    previous = card.get("speaker_curation")
    state = dict(previous) if isinstance(previous, Mapping) else {}
    state.update(
        {
            "source_revision": revision,
            "state": (
                "current"
                if state.get("artifact_index_revision") == revision
                else "stale"
            ),
            "updated_at": _now_iso(),
        }
    )
    card["speaker_curation"] = state

    # A stale marker must not be advertised as a current index. The physical
    # index is atomically replaced by the later index stages.
    rag = card.get("rag")
    rag_state = dict(rag) if isinstance(rag, Mapping) else {}
    indexed = rag_state.get("indexed_artifacts")
    if isinstance(indexed, list):
        structured = {
            str((card.get("artifacts") or {}).get(key) or f"artifacts/{key}.json")
            for key in ("decisions", "tasks", "risks", "open_questions")
        }
        rag_state["indexed_artifacts"] = [
            value
            for value in indexed
            if str(value) not in _CHUNK_INDEX_MARKERS | structured
        ]
    card["rag"] = rag_state
    return revision


def ensure_source_revision(
    card: dict[str, Any],
    *,
    meeting_dir: Path,
    overrides: Mapping[str, Any] | None,
) -> str:
    current = card.get("speaker_curation")
    computed = compute_source_revision(meeting_dir, card, overrides)
    if not isinstance(current, Mapping) or current.get("source_revision") != computed:
        return mark_speaker_inputs_changed(
            card,
            meeting_dir=meeting_dir,
            overrides=overrides,
        )
    return computed


def mark_stage_revision(card: dict[str, Any], stage: str) -> None:
    key = _STAGE_REVISION_KEYS.get(stage)
    state = card.get("speaker_curation")
    if key is None or not isinstance(state, dict):
        return
    revision = state.get("source_revision")
    if not isinstance(revision, str) or len(revision) != 64:
        return
    if any(
        state.get(required_key) != revision
        for required_key in _STAGE_PREREQUISITE_KEYS.get(stage, ())
    ):
        return
    state[key] = revision
    state["updated_at"] = _now_iso()
    state["state"] = (
        "current"
        if stage == "index_artifacts"
        and all(state.get(value) == revision for value in _STAGE_REVISION_KEYS.values())
        else "rebuilding"
    )


def stage_revision_is_current(card: Mapping[str, Any], stage: str) -> bool | None:
    """Return None for legacy cards, otherwise whether this stage is current."""
    key = _STAGE_REVISION_KEYS.get(stage)
    state = card.get("speaker_curation")
    if key is None or not isinstance(state, Mapping):
        return None
    revision = state.get("source_revision")
    if not isinstance(revision, str):
        return False
    return state.get(key) == revision


def stage_prerequisites_are_current(
    card: Mapping[str, Any], stage: str
) -> bool | None:
    state = card.get("speaker_curation")
    required = _STAGE_PREREQUISITE_KEYS.get(stage)
    if required is None or not isinstance(state, Mapping):
        return None
    revision = state.get("source_revision")
    if not isinstance(revision, str):
        return False
    return all(state.get(key) == revision for key in required)


def speaker_outputs_stale(card: Mapping[str, Any]) -> bool:
    state = card.get("speaker_curation")
    return bool(isinstance(state, Mapping) and state.get("state") != "current")


def speaker_search_outputs_stale(card: Mapping[str, Any]) -> bool:
    state = card.get("speaker_curation")
    if not isinstance(state, Mapping):
        return False
    revision = state.get("source_revision")
    return not isinstance(revision, str) or state.get("chunk_index_revision") != revision


def rebuild_status(card: Mapping[str, Any]) -> dict[str, Any]:
    state = card.get("speaker_curation")
    if not isinstance(state, Mapping):
        return {
            "state": "not_initialized",
            "needs_rebuild": False,
            "stages": [],
        }
    revision = state.get("source_revision")
    stages = [
        {
            "stage": stage,
            "current": bool(revision and state.get(key) == revision),
        }
        for stage, key in _STAGE_REVISION_KEYS.items()
    ]
    return {
        "state": str(state.get("state") or "stale"),
        "needs_rebuild": any(not item["current"] for item in stages),
        "updated_at": state.get("updated_at"),
        "stages": stages,
    }
