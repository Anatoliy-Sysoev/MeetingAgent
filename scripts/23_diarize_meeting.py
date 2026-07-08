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

from meeting_agent.diarization import normalize_intervals  # noqa: E402
from meeting_agent.diarization.sherpa_backend import (  # noqa: E402
    SherpaDiarizationConfig,
    SherpaDiarizationError,
    diarize_wav,
    validate_model_paths,
    validate_runtime_dependencies,
)


OUTPUT_DIARIZATION = "transcript/diarization.jsonl"
OUTPUT_REPORT = "transcript/diarization_report.json"
DEFAULT_AUDIO = "source/audio_16k_mono.wav"


class DiarizeMeetingError(RuntimeError):
    def __init__(self, message: str, stage: str = "diarization") -> None:
        super().__init__(message)
        self.stage = stage


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


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


def choose_audio(meeting_dir: Path, meeting: dict[str, Any], explicit_audio: str | None) -> Path:
    if explicit_audio:
        audio_path = resolve_path(explicit_audio, base=meeting_dir)
        if not audio_path.exists():
            raise DiarizeMeetingError(f"Audio file not found: {audio_path}", stage="preflight")
        return audio_path

    preferred = meeting_dir / DEFAULT_AUDIO
    if preferred.exists():
        return preferred

    for media in meeting.get("source", {}).get("media_files", []):
        if media.get("media_type") != "audio":
            continue
        media_path = meeting_dir / str(media.get("path") or "")
        if media_path.exists():
            return media_path

    raise DiarizeMeetingError(
        "No normalized audio found. Run scripts/21_extract_audio.py first or pass --audio-path.",
        stage="preflight",
    )


def update_meeting(meeting: dict[str, Any]) -> None:
    artifacts = dict(meeting.get("artifacts", {}))
    artifacts["diarization"] = OUTPUT_DIARIZATION
    artifacts["diarization_report"] = OUTPUT_REPORT
    meeting["artifacts"] = artifacts
    meeting["updated_at"] = now_iso()
    meeting.pop("last_error", None)
    if meeting.get("processing_status") == "failed":
        meeting["processing_status"] = "transcribed"


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


def build_config(args: argparse.Namespace) -> SherpaDiarizationConfig:
    models_dir = resolve_path(args.models_dir, base=ROOT)
    return SherpaDiarizationConfig(
        segmentation_model=resolve_path(args.segmentation_model, base=models_dir),
        embedding_model=resolve_path(args.embedding_model, base=models_dir),
        num_speakers=args.num_speakers,
        min_speakers=args.min_speakers,
        max_speakers=args.max_speakers,
        cluster_threshold=args.cluster_threshold,
        min_duration_on=args.min_duration_on,
        min_duration_off=args.min_duration_off,
        num_threads=args.num_threads,
    )


def run(args: argparse.Namespace) -> int:
    if args.backend != "sherpa-onnx":
        raise DiarizeMeetingError(f"Unsupported backend: {args.backend}", stage="preflight")

    schema_path = ROOT / "configs" / "schemas" / "meeting.schema.json"
    meeting_dir = resolve_meeting_dir(args.meeting_dir)
    meeting_path = meeting_dir / "meeting.json"
    if not meeting_path.exists():
        raise DiarizeMeetingError(f"meeting.json not found: {meeting_path}", stage="preflight")

    meeting = read_json(meeting_path)
    validate_schema(meeting, schema_path)
    audio_path = choose_audio(meeting_dir, meeting, args.audio_path)
    output_jsonl = meeting_dir / OUTPUT_DIARIZATION
    output_report = meeting_dir / OUTPUT_REPORT
    if output_jsonl.exists() and not args.force:
        raise DiarizeMeetingError(
            f"Diarization already exists: {output_jsonl}. Use --force to overwrite.",
            stage="preflight",
        )

    config = build_config(args)
    if args.dry_run:
        try:
            validate_model_paths(config)
            validate_runtime_dependencies()
        except SherpaDiarizationError as exc:
            raise DiarizeMeetingError(str(exc), stage="preflight") from exc
        print("diarization dry-run ok")
        print(f"meeting_dir: {meeting_dir}")
        print(f"audio: {audio_path}")
        print(f"backend: {args.backend}")
        print(f"segmentation_model: {config.segmentation_model}")
        print(f"embedding_model: {config.embedding_model}")
        return 0

    try:
        validate_model_paths(config)
        result = diarize_wav(audio_path, config)
        intervals, warnings = normalize_intervals(
            [interval.to_dict() for interval in result.intervals],
            backend=result.report.backend,
        )
        report_data = result.report.to_dict()
        report_data["warnings"] = list(report_data.get("warnings") or []) + warnings
        write_jsonl(output_jsonl, [interval.to_dict() for interval in intervals])
        write_json_atomic(output_report, report_data)
        update_meeting(meeting)
        validate_schema(meeting, schema_path)
        write_json_atomic(meeting_path, meeting)
    except SherpaDiarizationError as exc:
        mark_failed(meeting_path, meeting, exc, "diarization")
        raise DiarizeMeetingError(str(exc), stage="diarization") from exc
    except Exception as exc:
        mark_failed(meeting_path, meeting, exc, getattr(exc, "stage", "diarization"))
        raise

    print("diarization complete")
    print(f"intervals: {len(intervals)}")
    print(f"jsonl: {output_jsonl}")
    print(f"report: {output_report}")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run optional local speaker diarization for a MeetingAgent meeting card.",
    )
    parser.add_argument("--meeting-dir", required=True, help="Path to meeting folder.")
    parser.add_argument("--backend", default="sherpa-onnx", choices=["sherpa-onnx"])
    parser.add_argument("--audio-path", help="Explicit WAV path. Defaults to source/audio_16k_mono.wav.")
    parser.add_argument("--models-dir", default="models/diarization", help="Directory with diarization models.")
    parser.add_argument(
        "--segmentation-model",
        default="sherpa-onnx-pyannote-segmentation-3-0/model.onnx",
    )
    parser.add_argument("--embedding-model", default="wespeaker_en_voxceleb_resnet34_LM.onnx")
    parser.add_argument("--num-speakers", type=int, help="Known number of speakers. Omit for auto.")
    parser.add_argument("--min-speakers", type=int, help="Reserved for future backends.")
    parser.add_argument("--max-speakers", type=int, help="Reserved for future backends.")
    parser.add_argument("--cluster-threshold", type=float, default=0.5)
    parser.add_argument("--min-duration-on", type=float, default=0.3)
    parser.add_argument("--min-duration-off", type=float, default=0.5)
    parser.add_argument("--num-threads", type=int, default=1)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main() -> int:
    try:
        return run(parse_args(sys.argv[1:]))
    except DiarizeMeetingError as exc:
        print(f"ERROR[{exc.stage}]: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR[runtime]: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
