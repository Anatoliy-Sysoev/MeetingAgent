from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from meeting_agent.diarization import assign_speaker, normalize_intervals  # noqa: E402
from meeting_agent.speakers import (  # noqa: E402
    SpeakerOverrideStore,
    mark_speaker_inputs_changed,
    speaker_curation_requested,
)


DEFAULT_SPEAKER = "SPEAKER_UNKNOWN"
DEFAULT_SOURCE = "MIX"


class MergeSpeakersError(RuntimeError):
    def __init__(self, message: str, stage: str = "speaker_merge") -> None:
        super().__init__(message)
        self.stage = stage


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def repo_root() -> Path:
    return ROOT


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(path)


def validate_schema(data: dict[str, Any], schema_path: Path) -> None:
    schema = read_json(schema_path)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(data)


def resolve_meeting_dir(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def resolve_path(value: str, *, base: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_number, line in enumerate(fh, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                rows.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise MergeSpeakersError(
                    f"Invalid JSONL at {path}:{line_number}: {exc}",
                    stage="read_segments",
                ) from exc
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def format_time(seconds: float) -> str:
    total = max(0, int(seconds))
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


def normalize_speaker_mapping(meeting: dict[str, Any]) -> dict[str, dict[str, str]]:
    raw_mapping = meeting.get("speaker_mapping")
    if not isinstance(raw_mapping, dict):
        return {}

    mapping: dict[str, dict[str, str]] = {}
    for label, raw_entry in raw_mapping.items():
        if not isinstance(label, str) or not isinstance(raw_entry, dict):
            continue
        name = str(raw_entry.get("name") or "").strip()
        role = str(raw_entry.get("role") or "").strip()
        if name or role:
            mapping[label] = {"name": name, "role": role}
    return mapping


def display_speaker(label: str, mapping: dict[str, dict[str, str]]) -> str:
    entry = mapping.get(label) or {}
    name = entry.get("name") or label
    role = entry.get("role") or ""
    if role:
        return f"{name} ({role})"
    return name


def build_utterances(
    segments: list[dict[str, Any]],
    diarization_intervals: list[Any] | None = None,
    *,
    min_overlap_ratio: float = 0.3,
) -> list[dict[str, Any]]:
    utterances: list[dict[str, Any]] = []
    intervals = diarization_intervals or []
    for index, segment in enumerate(segments, start=1):
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        try:
            start = round(float(segment["start"]), 3)
            end = round(float(segment["end"]), 3)
        except (KeyError, TypeError, ValueError) as exc:
            raise MergeSpeakersError(
                f"Segment {index} must have numeric start/end.",
                stage="validate_segments",
            ) from exc
        if end < start:
            raise MergeSpeakersError(
                f"Segment {index} has end before start.",
                stage="validate_segments",
            )

        speaker = DEFAULT_SPEAKER
        speaker_overlap_seconds = 0.0
        speaker_overlap_ratio = 0.0
        if intervals:
            speaker, speaker_overlap_seconds, speaker_overlap_ratio = assign_speaker(
                {"start": start, "end": end},
                intervals,
                min_overlap_ratio=min_overlap_ratio,
            )

        utterances.append(
            {
                "utterance_id": f"utt-{len(utterances) + 1:06d}",
                "segment_index": index - 1,
                "speaker": speaker,
                "speaker_name": speaker,
                "source": str(segment.get("source") or DEFAULT_SOURCE),
                "start": start,
                "end": end,
                "text": text,
                "speaker_overlap_seconds": speaker_overlap_seconds,
                "speaker_overlap_ratio": speaker_overlap_ratio,
            }
        )
    if not utterances:
        raise MergeSpeakersError("No non-empty transcript segments found.", stage="validate_segments")
    return utterances


def build_text(
    utterances: list[dict[str, Any]],
    *,
    speaker_mapping: dict[str, dict[str, str]] | None = None,
) -> str:
    mapping = speaker_mapping or {}
    lines = ["# Speaker transcript", ""]
    for utterance in utterances:
        speaker_label = str(
            utterance.get("speaker")
            or utterance.get("speaker_name")
            or DEFAULT_SPEAKER
        )
        lines.append(
            "[{time}] {speaker}: {text}".format(
                time=format_time(float(utterance["start"])),
                speaker=display_speaker(speaker_label, mapping),
                text=utterance["text"],
            )
        )
    return "\n".join(lines).rstrip() + "\n"


def update_meeting(meeting: dict[str, Any], meeting_dir: Path) -> None:
    artifacts = dict(meeting.get("artifacts", {}))
    artifacts["speaker_transcript"] = "transcript/speaker_transcript.jsonl"
    meeting["artifacts"] = artifacts
    overrides = SpeakerOverrideStore(
        meeting_dir / "transcript" / "speaker_overrides.json",
        str(meeting["meeting_id"]),
    ).current()
    if speaker_curation_requested(meeting, overrides):
        mark_speaker_inputs_changed(
            meeting,
            meeting_dir=meeting_dir,
            overrides=overrides,
        )
    meeting["updated_at"] = now_iso()
    meeting.pop("last_error", None)


def load_diarization_intervals(path: Path | None) -> tuple[list[Any], list[str]]:
    if path is None or not path.exists():
        return [], []
    raw_intervals = read_jsonl(path)
    return normalize_intervals(raw_intervals, backend="external")


def mark_failed(meeting_path: Path, meeting: dict[str, Any], exc: BaseException, stage: str) -> None:
    meeting["processing_status"] = "failed"
    meeting["updated_at"] = now_iso()
    meeting["last_error"] = {
        "stage": stage,
        "message": str(exc),
        "type": type(exc).__name__,
        "timestamp": now_iso(),
    }
    write_json_atomic(meeting_path, meeting)


def run(args: argparse.Namespace) -> int:
    root = repo_root()
    schema_path = root / "configs" / "schemas" / "meeting.schema.json"
    meeting_dir = resolve_meeting_dir(args.meeting_dir)
    meeting_path = meeting_dir / "meeting.json"
    if not meeting_path.exists():
        raise MergeSpeakersError(f"meeting.json not found: {meeting_path}", stage="preflight")

    meeting = read_json(meeting_path)
    validate_schema(meeting, schema_path)
    segments_rel = meeting.get("artifacts", {}).get("segments", "transcript/segments.jsonl")
    segments_path = meeting_dir / segments_rel
    if not segments_path.exists():
        raise MergeSpeakersError(f"segments.jsonl not found: {segments_path}", stage="preflight")
    diarization_path: Path | None = None
    if args.diarization_path:
        diarization_path = resolve_path(args.diarization_path, base=meeting_dir)
    else:
        diarization_rel = meeting.get("artifacts", {}).get("diarization", "transcript/diarization.jsonl")
        candidate = meeting_dir / diarization_rel
        if candidate.exists():
            diarization_path = candidate

    output_jsonl = meeting_dir / "transcript" / "speaker_transcript.jsonl"
    output_txt = meeting_dir / "transcript" / "speaker_transcript.txt"
    if output_jsonl.exists() and not args.force:
        raise MergeSpeakersError(
            f"Speaker transcript already exists: {output_jsonl}. Use --force to overwrite.",
            stage="preflight",
        )

    try:
        intervals, interval_warnings = load_diarization_intervals(diarization_path)
        utterances = build_utterances(
            read_jsonl(segments_path),
            intervals,
            min_overlap_ratio=args.min_overlap_ratio,
        )
        write_jsonl(output_jsonl, utterances)
        output_txt.write_text(
            build_text(utterances, speaker_mapping=normalize_speaker_mapping(meeting)),
            encoding="utf-8",
        )
        update_meeting(meeting, meeting_dir)
        validate_schema(meeting, schema_path)
        write_json_atomic(meeting_path, meeting)
    except Exception as exc:
        mark_failed(meeting_path, meeting, exc, getattr(exc, "stage", "speaker_merge"))
        raise

    print("speaker transcript complete")
    print(f"utterances: {len(utterances)}")
    print(f"diarization_intervals: {len(intervals)}")
    if interval_warnings:
        print(f"diarization_warnings: {len(interval_warnings)}")
    print(f"jsonl: {output_jsonl}")
    print(f"text: {output_txt}")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a diarization-lite speaker transcript from ASR segments.",
    )
    parser.add_argument("--meeting-dir", required=True, help="Path to meeting folder.")
    parser.add_argument("--diarization-path", help="Explicit diarization JSONL path. Defaults to meeting artifact.")
    parser.add_argument("--min-overlap-ratio", type=float, default=0.3)
    parser.add_argument("--force", action="store_true", help="Overwrite existing speaker transcript.")
    return parser.parse_args(argv)


def main() -> int:
    try:
        return run(parse_args(sys.argv[1:]))
    except MergeSpeakersError as exc:
        print(f"ERROR[{exc.stage}]: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR[runtime]: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
