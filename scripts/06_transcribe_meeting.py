from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


def load_transcribe22():
    module_path = Path(__file__).resolve().with_name("22_transcribe_meeting.py")
    spec = importlib.util.spec_from_file_location("meeting_transcribe_22_compat", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load canonical transcriber: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["meeting_transcribe_22_compat"] = module
    spec.loader.exec_module(module)
    return module


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Deprecated compatibility wrapper. Use scripts/22_transcribe_meeting.py --engine faster-whisper.",
    )
    parser.add_argument("--meeting-dir", required=True, help="Path to meeting folder.")
    parser.add_argument("--model", default=None, help="faster-whisper model name.")
    parser.add_argument("--compute-type", default="int8", help="CTranslate2 compute type.")
    parser.add_argument("--language", default="ru", help="Audio language.")
    parser.add_argument("--dry-run", action="store_true", help="Validate inputs without transcription.")
    parser.add_argument("--force", action="store_true", help="Retry or overwrite existing transcript.")
    parser.add_argument("--resume", action="store_true", help="Resume supported cached work where possible.")
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args(sys.argv[1:])
    transcribe22 = load_transcribe22()
    forwarded = [
        "--meeting-dir",
        args.meeting_dir,
        "--engine",
        "faster-whisper",
        "--language",
        args.language,
        "--compute-type",
        args.compute_type,
    ]
    if args.model:
        forwarded.extend(["--model", args.model])
    if args.dry_run:
        forwarded.append("--dry-run")
    if args.force:
        forwarded.append("--force")
    if args.resume:
        forwarded.append("--resume")
    return int(transcribe22.main_with_argv(forwarded))


if __name__ == "__main__":
    raise SystemExit(main())
