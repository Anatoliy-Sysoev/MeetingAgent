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
STATUS_PROCESSING = "processing"
STATUS_FAILED = "failed"
SUPPORTED_ENGINES = {"vosk"}
SOURCE_ARTIFACT_KEYS = {
    "MIC": {
        "live_segments": "live_segments_mic",
        "live_partials": "live_partials_mic",
        "live_transcript": "live_transcript_mic",
        "live_srt": "live_srt_mic",
        "live_vtt": "live_vtt_mic",
        "live_report": "live_report_mic",
    },
    "SYS": {
        "live_segments": "live_segments_sys",
        "live_partials": "live_partials_sys",
        "live_transcript": "live_transcript_sys",
        "live_srt": "live_srt_sys",
        "live_vtt": "live_vtt_sys",
        "live_report": "live_report_sys",
    },
    "MIX": {
        "live_segments": "live_segments_mix",
        "live_partials": "live_partials_mix",
        "live_transcript": "live_transcript_mix",
        "live_srt": "live_srt_mix",
        "live_vtt": "live_vtt_mix",
        "live_report": "live_report_mix",
    },
}


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

from meeting_agent.live_transcription import (  # noqa: E402
    VALID_LIVE_SOURCES,
    LiveSessionReport,
    list_audio_devices,
    preflight_audio_source,
    write_live_artifacts,
)
from meeting_agent.live_transcription.vad import SileroVadConfig  # noqa: E402
from meeting_agent.live_transcription.vosk_backend import VoskBackendError, VoskLiveConfig, transcribe_vosk_live  # noqa: E402


VALID_SOURCES = set(VALID_LIVE_SOURCES)


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


def ensure_can_write(meeting_dir: Path, source: str, force: bool) -> None:
    live_segments = meeting_dir / "transcript" / "live" / f"live_segments.{source}.jsonl"
    if live_segments.exists() and not force:
        raise LiveTranscribeError(
            f"Live transcript for source {source} already exists. Use --force to overwrite that source.",
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
    source_keys = SOURCE_ARTIFACT_KEYS[source]
    for key in ("live_segments", "live_partials", "live_transcript", "live_srt", "live_vtt", "live_report"):
        if key in written:
            artifacts[source_keys[key]] = relative_path(meeting_dir, written[key])
    meeting["artifacts"] = artifacts
    rag = dict(meeting.get("rag", {}))
    no_index = list(rag.get("no_index_artifacts") or [])
    for key in ("live_segments", "live_partials", "live_transcript", "live_srt", "live_vtt"):
        value = artifacts.get(source_keys[key])
        if isinstance(value, str) and value not in no_index:
            no_index.append(value)
    rag["no_index_artifacts"] = no_index
    meeting["rag"] = rag
    update_source_tracks(meeting, source)
    meeting["processing_status"] = STATUS_PROCESSING
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
    if args.list_audio_sources:
        payload = {
            "devices": [device.to_dict() for device in list_audio_devices()],
            "sources": [
                preflight_audio_source(source).to_dict()
                for source in sorted(VALID_SOURCES)
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if args.preflight_source:
        result = preflight_audio_source(
            args.source,
            audio_device_index=args.audio_device_index,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0 if result.available else 2

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
        ensure_can_write(meeting_dir, args.source, args.force)
        model_path = resolve_path(args.model_path)
        input_wav = resolve_path(args.input_wav) if args.input_wav else None

        if input_wav is None and not args.dry_run:
            audio_preflight = preflight_audio_source(
                args.source,
                audio_device_index=args.audio_device_index,
            )
            if not audio_preflight.available:
                raise LiveTranscribeError(
                    f"Audio source {args.source} is unavailable: {audio_preflight.reason}",
                    stage="preflight",
                )

        if args.dry_run:
            print("dry-run ok")
            print(f"meeting_dir: {meeting_dir}")
            print(f"engine: {args.engine}")
            print(f"model_path: {model_path}")
            print(f"source: {args.source}")
            if args.audio_device_index is not None:
                print(f"audio_device_index: {args.audio_device_index}")
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
                    audio_device_index=args.audio_device_index,
                    save_partials=not args.no_partials,
                    vad=args.vad,
                    silero_vad=SileroVadConfig(
                        threshold=args.vad_threshold,
                        min_speech_ms=args.vad_min_speech_ms,
                        min_silence_ms=args.vad_min_silence_ms,
                        speech_pad_ms=args.vad_speech_pad_ms,
                    ),
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
        written = write_live_artifacts(output_dir, result.segments, result.partials, report, source=args.source)

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
        exc = LiveTranscribeError("Interrupted before live backend could finalize.", stage="runtime")
        mark_failed(meeting_path, meeting, exc, exc.stage, mutate_on_error)
        print(f"ERROR[{exc.stage}]: {exc}", file=sys.stderr)
        return 130
    except Exception as exc:
        mark_failed(meeting_path, meeting, exc, "runtime", mutate_on_error)
        print(f"ERROR[runtime]: {exc}", file=sys.stderr)
        return 1


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MeetingAgent live transcription entrypoint.")
    parser.add_argument("--meeting-dir", help="Path to meeting folder.")
    parser.add_argument("--engine", default="vosk", choices=sorted(SUPPORTED_ENGINES))
    parser.add_argument("--model-path", help="Path to local Vosk model directory.")
    parser.add_argument("--source", default="MIC", choices=sorted(VALID_SOURCES), help="Audio source label.")
    parser.add_argument(
        "--audio-device-index",
        type=int,
        default=None,
        help="Optional source-specific device index from --list-audio-sources.",
    )
    parser.add_argument("--input-wav", help="Optional mono 16 kHz PCM WAV for deterministic smoke runs.")
    parser.add_argument("--duration-sec", type=float, default=None, help="Limit live capture or WAV simulation duration.")
    parser.add_argument("--sample-rate", type=int, default=16_000)
    parser.add_argument("--block-ms", type=int, default=300)
    parser.add_argument("--vad", default="none", choices=["none", "silero"], help="Optional VAD preprocessing mode.")
    parser.add_argument("--vad-threshold", type=float, default=0.5, help="Silero VAD speech threshold.")
    parser.add_argument("--vad-min-speech-ms", type=int, default=250)
    parser.add_argument("--vad-min-silence-ms", type=int, default=100)
    parser.add_argument("--vad-speech-pad-ms", type=int, default=100)
    parser.add_argument("--no-partials", action="store_true", help="Do not write live partial hypotheses.")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    discovery = parser.add_mutually_exclusive_group()
    discovery.add_argument(
        "--list-audio-sources",
        action="store_true",
        help="List local devices plus MIC/SYS/MIX source readiness and exit.",
    )
    discovery.add_argument(
        "--preflight-source",
        action="store_true",
        help="Preflight the selected live source without starting capture.",
    )
    args = parser.parse_args(argv)
    if args.audio_device_index is not None and args.audio_device_index < 0:
        parser.error("--audio-device-index must be non-negative.")
    if not args.list_audio_sources and not args.preflight_source:
        if not args.meeting_dir:
            parser.error(
                "--meeting-dir is required unless --list-audio-sources or "
                "--preflight-source is used."
            )
        if not args.model_path:
            parser.error(
                "--model-path is required unless --list-audio-sources or "
                "--preflight-source is used."
            )
    return args


def main() -> int:
    return run(parse_args(sys.argv[1:]))


def main_with_argv(argv: list[str]) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
