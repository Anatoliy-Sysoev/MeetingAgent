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
from meeting_agent.live_transcription.schema import SOURCE_ARTIFACT_KEYS  # noqa: E402
from meeting_agent.live_transcription.audio_archive import (  # noqa: E402
    DEFAULT_ARCHIVE_MAX_BYTES,
    DEFAULT_ARCHIVE_MIN_FREE_BYTES,
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


def ensure_can_write(
    meeting_dir: Path,
    source: str,
    force: bool,
    *,
    capture_audio: bool,
) -> None:
    live_segments = meeting_dir / "transcript" / "live" / f"live_segments.{source}.jsonl"
    live_audio = meeting_dir / "source" / f"live_audio.{source}.wav"
    if (live_segments.exists() or (capture_audio and live_audio.exists())) and not force:
        raise LiveTranscribeError(
            f"Live recording for source {source} already exists. Use --force to overwrite that source.",
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


def update_meeting_artifacts(
    meeting: dict[str, Any],
    meeting_dir: Path,
    written: dict[str, Path],
    source: str,
    *,
    duration_seconds: float,
) -> None:
    artifacts = dict(meeting.get("artifacts", {}))
    source_keys = SOURCE_ARTIFACT_KEYS[source]
    for key in (
        "live_segments",
        "live_partials",
        "live_transcript",
        "live_srt",
        "live_vtt",
        "live_report",
        "live_audio",
    ):
        if key in written and key in source_keys:
            artifacts[source_keys[key]] = relative_path(meeting_dir, written[key])
    meeting["artifacts"] = artifacts
    rag = dict(meeting.get("rag", {}))
    no_index = list(rag.get("no_index_artifacts") or [])
    for key in (
        "live_segments",
        "live_partials",
        "live_transcript",
        "live_srt",
        "live_vtt",
        "live_audio",
    ):
        if key not in source_keys:
            continue
        value = artifacts.get(source_keys[key])
        if isinstance(value, str) and value not in no_index:
            no_index.append(value)
    rag["no_index_artifacts"] = no_index
    meeting["rag"] = rag
    update_source_tracks(meeting, source)
    audio_path = written.get("live_audio")
    if audio_path is not None:
        source_data = dict(meeting.get("source") or {})
        raw_media = source_data.get("media_files")
        media_files = [
            dict(item) for item in raw_media if isinstance(item, dict)
        ] if isinstance(raw_media, list) else []
        audio_rel = relative_path(meeting_dir, audio_path)
        media_entry = {
            "path": audio_rel,
            "media_type": "audio",
            "duration_seconds": round(max(0.0, duration_seconds), 3),
        }
        for index, item in enumerate(media_files):
            if item.get("path") == audio_rel:
                media_files[index] = media_entry
                break
        else:
            media_files.append(media_entry)
        source_data["media_files"] = media_files
        meeting["source"] = source_data
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
        model_path = resolve_path(args.model_path)
        input_wav = resolve_path(args.input_wav) if args.input_wav else None
        ensure_can_write(
            meeting_dir,
            args.source,
            args.force,
            capture_audio=input_wav is None and args.source in {"MIC", "SYS"},
        )
        audio_archive_path = (
            meeting_dir / "source" / f"live_audio.{args.source}.wav"
            if input_wav is None and args.source in {"MIC", "SYS"}
            else None
        )

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
                    mic_queue_max_blocks=args.mic_queue_max_blocks,
                    partials_max=args.partials_max,
                    save_partials=not args.no_partials,
                    vad=args.vad,
                    silero_vad=SileroVadConfig(
                        threshold=args.vad_threshold,
                        min_speech_ms=args.vad_min_speech_ms,
                        min_silence_ms=args.vad_min_silence_ms,
                        speech_pad_ms=args.vad_speech_pad_ms,
                    ),
                    audio_archive_path=audio_archive_path,
                    audio_archive_max_bytes=args.audio_archive_max_bytes,
                    audio_archive_min_free_bytes=args.audio_archive_min_free_bytes,
                )
            )
        except VoskBackendError as exc:
            raise LiveTranscribeError(str(exc), stage="vosk") from exc

        finished_at = now_iso()
        warnings = [] if result.segments else ["no_final_segments"]
        for warning in result.metrics.get("vad_warnings") or []:
            if isinstance(warning, str) and warning and warning not in warnings:
                warnings.append(warning)
        if int(result.metrics.get("mic_queue_dropped_frames") or 0) > 0:
            warnings.append("mic_audio_dropped")
        if int(result.metrics.get("input_status_events") or 0) > 0:
            warnings.append("mic_input_status_events")
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
            warnings=warnings,
            backend_metrics=result.metrics,
        )
        output_dir = meeting_dir / "transcript" / "live"
        written = write_live_artifacts(output_dir, result.segments, result.partials, report, source=args.source)
        if audio_archive_path is not None:
            if (
                result.audio_archive_path is None
                or result.audio_archive_path.resolve() != audio_archive_path.resolve()
                or not result.audio_archive_path.is_file()
            ):
                raise LiveTranscribeError(
                    "Live audio archive was not finalized.", stage="audio_archive"
                )
            written["live_audio"] = result.audio_archive_path

        update_meeting_artifacts(
            meeting,
            meeting_dir,
            written,
            args.source,
            duration_seconds=report.duration_seconds,
        )
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
    parser.add_argument(
        "--mic-queue-max-blocks",
        type=int,
        default=32,
        help="Bounded MIC callback queue capacity in audio blocks (1..1024).",
    )
    parser.add_argument(
        "--partials-max",
        type=int,
        default=1_000,
        help="Bounded number of partial hypotheses retained in memory (1..10000).",
    )
    parser.add_argument(
        "--audio-archive-max-bytes",
        type=int,
        default=DEFAULT_ARCHIVE_MAX_BYTES,
        help="Maximum source-scoped live WAV payload size.",
    )
    parser.add_argument(
        "--audio-archive-min-free-bytes",
        type=int,
        default=DEFAULT_ARCHIVE_MIN_FREE_BYTES,
        help="Free-space reserve maintained while writing the live WAV.",
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
    if not 1 <= args.mic_queue_max_blocks <= 1_024:
        parser.error("--mic-queue-max-blocks must be in the range 1..1024.")
    if not 1 <= args.partials_max <= 10_000:
        parser.error("--partials-max must be in the range 1..10000.")
    if not 1 <= args.audio_archive_max_bytes <= 4_000_000_000:
        parser.error("--audio-archive-max-bytes must be in the range 1..4000000000.")
    if not 0 <= args.audio_archive_min_free_bytes <= 1_000_000_000_000:
        parser.error(
            "--audio-archive-min-free-bytes must be in the range 0..1000000000000."
        )
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
