from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


ROOT = repo_root()
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from meeting_agent.transcription.anonymize import (  # noqa: E402
    AnonymizationOptions,
    TranscriptAnonymizer,
    build_report,
    load_terms_file,
    merge_terms,
    read_jsonl_rows,
    terms_from_meeting_card,
    write_json_atomic,
    write_jsonl_rows,
)


class AnonymizeTranscriptError(RuntimeError):
    pass


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AnonymizeTranscriptError(f"JSON file must contain an object: {path}")
    return data


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(path)


def parse_term(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise AnonymizeTranscriptError("--term must use kind=value format")
    kind, term = value.split("=", 1)
    kind = kind.strip().lower()
    term = " ".join(term.split())
    if not kind or not term:
        raise AnonymizeTranscriptError("--term must include both kind and value")
    return kind, term


def cli_terms(values: list[str]) -> dict[str, list[str]]:
    terms: dict[str, list[str]] = {}
    for value in values:
        kind, term = parse_term(value)
        terms.setdefault(kind, []).append(term)
    return terms


def default_input_for_meeting(meeting_dir: Path, meeting: dict[str, Any]) -> Path:
    artifacts = meeting.get("artifacts")
    if isinstance(artifacts, dict):
        value = artifacts.get("segments") or artifacts.get("transcript")
        if isinstance(value, str) and value:
            candidate = meeting_dir / value
            if candidate.exists():
                return candidate
    candidate = meeting_dir / "transcript" / "segments.jsonl"
    if candidate.exists():
        return candidate
    candidate = meeting_dir / "transcript" / "transcript.md"
    if candidate.exists():
        return candidate
    raise AnonymizeTranscriptError("No transcript input found in meeting directory")


def output_paths(input_path: Path, out_dir: Path) -> dict[str, Path]:
    suffix = input_path.suffix.lower()
    if suffix == ".jsonl":
        return {"anonymized_jsonl": out_dir / "anonymized_segments.jsonl"}
    if suffix in {".md", ".markdown"}:
        return {"anonymized_md": out_dir / "anonymized_transcript.md"}
    raise AnonymizeTranscriptError("Input must be .jsonl or .md")


def ensure_can_write(paths: dict[str, Path], force: bool) -> None:
    existing = [path for path in paths.values() if path.exists()]
    if existing and not force:
        joined = ", ".join(str(path) for path in existing)
        raise AnonymizeTranscriptError(f"Output already exists; use --force: {joined}")


def display_path(path: Path) -> str:
    resolved = path.resolve()
    for base in (Path.cwd().resolve(), ROOT.resolve()):
        try:
            return resolved.relative_to(base).as_posix()
        except ValueError:
            continue
    return resolved.name


def write_private_mapping(path: Path, anonymizer: TranscriptAnonymizer) -> None:
    payload = {
        "warning": "Private mapping contains original sensitive values. Do not commit or publish.",
        "replacements": [
            item.private_dict()
            for item in sorted(anonymizer.replacements.values(), key=lambda item: item.placeholder)
        ],
    }
    write_json_atomic(path, payload)


def run(args: argparse.Namespace) -> int:
    meeting_dir = resolve_path(args.meeting_dir) if args.meeting_dir else None
    meeting: dict[str, Any] = {}
    if meeting_dir is not None:
        meeting_path = meeting_dir / "meeting.json"
        if meeting_path.exists():
            meeting = read_json(meeting_path)
    input_path = resolve_path(args.input) if args.input else None
    if input_path is None:
        if meeting_dir is None:
            raise AnonymizeTranscriptError("Provide --input or --meeting-dir")
        input_path = default_input_for_meeting(meeting_dir, meeting)
    if not input_path.exists():
        raise AnonymizeTranscriptError(f"Input not found: {input_path}")

    out_dir = resolve_path(args.out_dir) if args.out_dir else (
        meeting_dir / "transcript" / "anonymized" if meeting_dir else input_path.parent / f"{input_path.stem}.anonymized"
    )
    paths = output_paths(input_path, out_dir)
    report_path = out_dir / "anonymization_report.json"
    private_map_path = out_dir / "anonymization_mapping.private.json"
    write_targets = dict(paths)
    write_targets["report"] = report_path
    if args.write_private_map:
        write_targets["private_map"] = private_map_path
    ensure_can_write(write_targets, args.force)

    terms = merge_terms(
        terms_from_meeting_card(meeting),
        load_terms_file(resolve_path(args.terms_file)) if args.terms_file else {},
        cli_terms(args.term or []),
    )
    anonymizer = TranscriptAnonymizer(
        AnonymizationOptions(
            custom_terms=terms,
            detect_person_names=not args.no_detect_names,
            detect_org_legal_names=not args.no_detect_orgs,
            detect_internal_identifiers=not args.no_detect_identifiers,
        )
    )

    rows_read: int | None = None
    markdown_chars: int | None = None
    if input_path.suffix.lower() == ".jsonl":
        rows = read_jsonl_rows(input_path)
        rows_read = len(rows)
        anonymized_rows = anonymizer.anonymize_rows(rows)
        write_jsonl_rows(paths["anonymized_jsonl"], anonymized_rows)
    else:
        markdown = input_path.read_text(encoding="utf-8")
        markdown_chars = len(markdown)
        write_text_atomic(paths["anonymized_md"], anonymizer.anonymize_text(markdown))

    report = build_report(
        input_path=input_path,
        output_files=paths,
        anonymizer=anonymizer,
        rows_read=rows_read,
        markdown_chars=markdown_chars,
    )
    write_json_atomic(report_path, report)
    if args.write_private_map:
        write_private_mapping(private_map_path, anonymizer)

    print("anonymization complete")
    print(f"input: {display_path(input_path)}")
    for key, path in paths.items():
        print(f"{key}: {display_path(path)}")
    print(f"report: {display_path(report_path)}")
    if args.write_private_map:
        print(f"private_map: {display_path(private_map_path)}")
    print(f"replacements: {report['replacements_count']}")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Anonymize MeetingAgent transcript JSONL or Markdown locally.")
    parser.add_argument("--meeting-dir", help="Meeting card directory. Defaults input/output to transcript artifacts.")
    parser.add_argument("--input", help="Input .jsonl or .md transcript.")
    parser.add_argument("--out-dir", help="Output directory. Default: transcript/anonymized for meeting cards.")
    parser.add_argument("--terms-file", help="JSON object with person/org/path/url/email/phone/identifier term lists.")
    parser.add_argument("--term", action="append", default=[], help="Extra term in kind=value format; repeatable.")
    parser.add_argument("--write-private-map", action="store_true", help="Write local-only mapping with original values.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing anonymized outputs.")
    parser.add_argument("--no-detect-names", action="store_true", help="Disable heuristic Cyrillic person-name detection.")
    parser.add_argument("--no-detect-orgs", action="store_true", help="Disable legal organization-name detection.")
    parser.add_argument("--no-detect-identifiers", action="store_true", help="Disable internal identifier detection.")
    return parser.parse_args(argv)


def main() -> int:
    try:
        return run(parse_args(sys.argv[1:]))
    except AnonymizeTranscriptError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
