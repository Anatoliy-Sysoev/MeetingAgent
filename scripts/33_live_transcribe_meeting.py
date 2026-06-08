from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


STATUS_TRANSCRIBING = "transcribing"
STATUS_TRANSCRIBED = "transcribed"
STATUS_FAILED = "failed"
SUPPORTED_ENGINES = {"vosk"}
VALID_SOURCES = {"MIC", "SYS", "MIX"}


class LiveTranscribeError(RuntimeError):
    def __init__(self, message: str, stage: str = "runtime") -> None:
        super().__init__(message)
        self.stage = stage


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


ROOT = repo_root()
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from meeting_agent.live_transcription import LiveSessionReport, write_live_artifacts  # noqa: E402
from meeting_agent.live_transcription.vosk_backend import VoskBackendError, VoskLiveConfig, transcribe_vosk_live  # noqa: E402


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def validate_schema(data: dict[str, Any]) -> None:
    schema_path = ROOT / "configs" / "schemas" / "meeting.schema.json"
    schema = read_json(schema_path)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(data)


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def relative_path(meeting_dir: Path, path: Path) -> str:
    return path.resolve().relative_to(meeting_dir.resolve()).as_posix()


def ensure_can_write(meeting_dir: Path, force: bool) -> None:
    live_segments = meeting_dir / "transcript" / "live" / "live_segments.jsonl"
    if live_segments.exists() and not force:
        raise LiveTranscribeError(
            "Live transcript already exists. Use --force to overwrite transcript/live outputs.",
            stage="preflight",
        )


def update_source_tracks(meeting: dict[str, Any], source: str) -> None:
    source_data = dict(meeting.get("source", {}))
    if source in {"MIC", "SYS"}:
        tracks = list(source_data.get("audio_tracks") or [])
        if source not in tracks:
            tracks.append(source)
        source_data["audio_tracks"] = tracks
    if source == "MIX":
        tracks = list(source_data.get("derived_tracks") or [])
        if source not in tracks:
            tracks.append(source)
        source_data["derived_tracks"] = tracks
    meeting["source"] = source_data


def update_meeting_artifacts(meeting: dict[str, Any], meeting_dir: Path, written: dict[str, Path], source: str) -> None:
    artifacts = dict(meeting.get("artifacts", {}))
    for key in ("live_segments", "live_partials", "live_transcript", "live_srt", "live_vtt", "live_report"):
        if key in written:
            artifacts[key] = relative_path(meeting_dir, written[key])
    meeting["artifacts"] = artifacts
    rag = dict(meeting.get("rag", {}))
    no_index = list(rag.get("no_index_artifacts") or [])
    for key in ("live_segments", "live_partials", "live_transcript", "live_srt", "live_vtt"):
        value = artifacts.get(key)
        if isinstance(value, str) and value not in no_index:
            no_index.append(value)
    rag["no_index_artifacts"] = no_index
    meeting["rag"] = rag
    update_source_tracks(meeting, source)
    meeting["processing_status"] = STATUS_TRANSCRIBED
    meeting["updated_at"] = now_iso()
    meeting.pop("last_error", None)


def mark_failed(meeting_path: Path, meeting: dict[str, Any] | None, exc: BaseException, stage: str, mutate: bool) -> None:
    if not mutate or meeting is None:
        return
    meeting["processing_status"] = STATUS_FAILED
    meeting["updated_at"] = now_iso()
    meeting["last_error"] = {
        "stage": stage,
        "message": str(exc),
        "type": type(exc).__name__,
        "timestamp": now_iso(),
    }
    write_json_atomic(meeting_path, meeting)


def run(args: argparse.Namespace) -> int:
    meeting_dir = resolve_path(args.meeting_dir)
    meeting_path = meeting_dir / "meeting.json"
    meeting: dict[str, Any] | None = None
    mutate_on_error = False
    started_at = now_iso()
    started = time.time()

    try:
        if args.engine not in SUPPORTED_ENGINES:
            raise LiveTranscribeError(f"Unsupported live engine: {args.engine}", stage="preflight")
        if args.source not in VALID_SOURCES:
            raise LiveTranscribeError(f"Unsupported source: {args.source}", stage="preflight")
        if not meeting_path.exists():
            raise LiveTranscribeError(f"meeting.json not found: {meeting_path}", stage="preflight")

        meeting = read_json(meeting_path)
        validate_schema(meeting)
        ensure_can_write(meeting_dir, args.force)
        model_path = resolve_path(args.model_path)
        input_wav = resolve_path(args.input_wav) if args.input_wav else None

        if args.dry_run:
            print("dry-run ok")
            print(f"meeting_dir: {meeting_dir}")
            print(f"engine: {args.engine}")
            print(f"model_path: {model_path}")
            print(f"source: {args.source}")
            if input_wav:
                print(f"input_wav: {input_wav}")
            return 0

        mutate_on_error = True
        meeting["processing_status"] = STATUS_TRANSCRIBING
        meeting["updated_at"] = now_iso()
        meeting.pop("last_error", None)
        write_json_atomic(meeting_path, meeting)

        try:
            result = transcribe_vosk_live(
                VoskLiveConfig(
                    model_path=model_path,
                    source=args.source,
                    sample_rate=args.sample_rate,
                    block_ms=args.block_ms,
                    duration_sec=args.duration_sec,
                    input_wav=input_wav,
                    save_partials=not args.no_partials,
                )
            )
        except VoskBackendError as exc:
            raise LiveTranscribeError(str(exc), stage="vosk") from exc

        finished_at = now_iso()
        report = LiveSessionReport(
            engine=args.engine,
            model=model_path.name,
            source=args.source,
            sample_rate=args.sample_rate,
            block_ms=args.block_ms,
            duration_seconds=float(result.metrics.get("duration") or 0.0),
            segments_count=len(result.segments),
            partials_count=len(result.partials),
            chars_count=sum(len(segment.text) for segment in result.segments),
            started_at=started_at,
            finished_at=finished_at,
            elapsed_seconds=round(time.time() - started, 3),
            warnings=[] if result.segments else ["no_final_segments"],
            backend_metrics=result.metrics,
        )
        output_dir = meeting_dir / "transcript" / "live"
        written = write_live_artifacts(output_dir, result.segments, result.partials, report)

        update_meeting_artifacts(meeting, meeting_dir, written, args.source)
        validate_schema(meeting)
        write_json_atomic(meeting_path, meeting)

        print("live transcription complete")
        print(f"engine: {args.engine}")
        print(f"segments: {len(result.segments)}")
        print(f"partials: {len(result.partials)}")
        print(f"report: {written['live_report']}")
        return 0
    except LiveTranscribeError as exc:
        mark_failed(meeting_path, meeting, exc, exc.stage, mutate_on_error)
        print(f"ERROR[{exc.stage}]: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        exc = LiveTranscribeError("Interrupted by user.", stage="runtime")
        mark_failed(meeting_path, meeting, exc, exc.stage, mutate_on_error)
        print(f"ERROR[{exc.stage}]: {exc}", file=sys.stderr)
        return 130
    except Exception as exc:
        mark_failed(meeting_path, meeting, exc, "runtime", mutate_on_error)
        print(f"ERROR[runtime]: {exc}", file=sys.stderr)
        return 1


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MeetingAgent live transcription entrypoint.")
    parser.add_argument("--meeting-dir", required=True, help="Path to meeting folder.")
    parser.add_argument("--engine", default="vosk", choices=sorted(SUPPORTED_ENGINES))
    parser.add_argument("--model-path", required=True, help="Path to local Vosk model directory.")
    parser.add_argument("--source", default="MIC", choices=sorted(VALID_SOURCES), help="Audio source label.")
    parser.add_argument("--input-wav", help="Optional mono 16 kHz PCM WAV for deterministic smoke runs.")
    parser.add_argument("--duration-sec", type=float, default=None, help="Limit live capture or WAV simulation duration.")
    parser.add_argument("--sample-rate", type=int, default=16_000)
    parser.add_argument("--block-ms", type=int, default=300)
    parser.add_argument("--no-partials", action="store_true", help="Do not write live partial hypotheses.")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main() -> int:
    return run(parse_args(sys.argv[1:]))


def main_with_argv(argv: list[str]) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
