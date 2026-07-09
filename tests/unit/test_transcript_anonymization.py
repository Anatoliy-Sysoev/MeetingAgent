from __future__ import annotations

import importlib.util
import json
import sys
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from meeting_agent.transcription.anonymize import (
    AnonymizationOptions,
    TranscriptAnonymizer,
    load_terms_file,
    read_jsonl_rows,
)


SCRIPT_PATH = ROOT / "scripts" / "43_anonymize_transcript.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("anonymize_transcript_43", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def test_anonymizer_replaces_common_sensitive_values() -> None:
    anonymizer = TranscriptAnonymizer(
        AnonymizationOptions(custom_terms={"org": ["НОВАТЭК"], "identifier": ["Паспорт проекта"]})
    )

    text = (
        "Денис Белецкий из НОВАТЭК отправил denis@example.com. "
        "Файл C:\\Users\\Person\\Secret\\doc.docx, ссылка https://example.test/a, код FTT-MA-08."
    )
    result = anonymizer.result_for_text(text)

    assert "Денис Белецкий" not in result.text
    assert "НОВАТЭК" not in result.text
    assert "denis@example.com" not in result.text
    assert "C:\\Users\\Person\\Secret" not in result.text
    assert "https://example.test/a" not in result.text
    assert "FTT-MA-08" not in result.text
    assert "[PERSON_001]" in result.text
    assert "[ORG_001]" in result.text
    assert "[EMAIL_001]" in result.text
    assert "[PATH_001]" in result.text
    assert "[URL_001]" in result.text
    assert "[ID_001]" in result.text


def test_public_report_has_no_original_values_or_hashes(tmp_path: Path) -> None:
    script = _load_script()
    input_path = tmp_path / "segments.jsonl"
    _write_jsonl(
        input_path,
        [
            {
                "segment_id": "seg-000001",
                "start": 0,
                "end": 1,
                "speaker_name": "Денис Белецкий",
                "text": "Денис Белецкий сказал: смотри ООО «Ромашка».",
                "metadata": {"source_path": "C:\\Users\\Person\\internal.docx"},
            }
        ],
    )
    out_dir = tmp_path / "out"

    rc = script.main_with_args if hasattr(script, "main_with_args") else None
    assert rc is None
    code = script.run(script.parse_args(["--input", str(input_path), "--out-dir", str(out_dir)]))

    assert code == 0
    rows = read_jsonl_rows(out_dir / "anonymized_segments.jsonl")
    rendered = json.dumps(rows, ensure_ascii=False)
    assert "Денис Белецкий" not in rendered
    assert "Ромашка" not in rendered
    assert "C:\\Users\\Person" not in rendered

    report = json.loads((out_dir / "anonymization_report.json").read_text(encoding="utf-8"))
    report_text = json.dumps(report, ensure_ascii=False)
    assert "Денис Белецкий" not in report_text
    assert "Ромашка" not in report_text
    assert "C:\\Users\\Person" not in report_text
    assert "original_sha256" not in report["replacements"][0]
    assert not (out_dir / "anonymization_mapping.private.json").exists()


def test_jsonl_speakers_and_source_are_anonymized_unless_technical(tmp_path: Path) -> None:
    script = _load_script()
    input_path = tmp_path / "segments.jsonl"
    _write_jsonl(
        input_path,
        [
            {
                "segment_id": "seg-000001",
                "speaker": "Денис Белецкий",
                "speakers": ["SPEAKER_01", "Иван Петров"],
                "source": "C:\\Users\\Person\\meeting.mp4",
                "text": "Иван Петров прислал ivan@example.com",
            },
            {
                "segment_id": "seg-000002",
                "speaker": "SPEAKER_UNKNOWN",
                "speakers": ["SPEAKER_02"],
                "source": "MIX",
                "text": "Техническая строка",
            },
        ],
    )
    out_dir = tmp_path / "out"

    code = script.run(script.parse_args(["--input", str(input_path), "--out-dir", str(out_dir)]))

    assert code == 0
    rows = read_jsonl_rows(out_dir / "anonymized_segments.jsonl")
    rendered = json.dumps(rows, ensure_ascii=False)
    assert "Денис Белецкий" not in rendered
    assert "Иван Петров" not in rendered
    assert "ivan@example.com" not in rendered
    assert "C:\\Users\\Person" not in rendered
    assert rows[0]["speakers"][0] == "SPEAKER_01"
    assert rows[1]["speaker"] == "SPEAKER_UNKNOWN"
    assert rows[1]["speakers"] == ["SPEAKER_02"]
    assert rows[1]["source"] == "MIX"


def test_private_mapping_is_explicit_opt_in(tmp_path: Path) -> None:
    script = _load_script()
    input_path = tmp_path / "segments.jsonl"
    _write_jsonl(input_path, [{"segment_id": "seg-1", "start": 0, "end": 1, "text": "Антон Васильев"}])
    out_dir = tmp_path / "out"

    code = script.run(
        script.parse_args(
            ["--input", str(input_path), "--out-dir", str(out_dir), "--write-private-map"]
        )
    )

    assert code == 0
    private_map = json.loads((out_dir / "anonymization_mapping.private.json").read_text(encoding="utf-8"))
    assert private_map["replacements"][0]["original"] == "Антон Васильев"


def test_markdown_input_supported(tmp_path: Path) -> None:
    script = _load_script()
    input_path = tmp_path / "transcript.md"
    input_path.write_text("# Встреча\n\n[00:00:01] Сергей Иванов открыл https://example.test\n", encoding="utf-8")
    out_dir = tmp_path / "out"

    code = script.run(script.parse_args(["--input", str(input_path), "--out-dir", str(out_dir)]))

    assert code == 0
    anonymized = (out_dir / "anonymized_transcript.md").read_text(encoding="utf-8")
    assert "Сергей Иванов" not in anonymized
    assert "https://example.test" not in anonymized
    assert "[PERSON_001]" in anonymized
    assert "[URL_001]" in anonymized


def test_meeting_dir_defaults_to_transcript_anonymized(tmp_path: Path) -> None:
    script = _load_script()
    meeting_dir = tmp_path / "meeting"
    transcript_dir = meeting_dir / "transcript"
    transcript_dir.mkdir(parents=True)
    (meeting_dir / "meeting.json").write_text(
        json.dumps(
            {
                "meeting_id": "m1",
                "title": "Паспорт проекта",
                "artifacts": {"segments": "transcript/segments.jsonl"},
                "speaker_mapping": {"SPEAKER_01": {"name": "Анатолий Сысоев", "role": "PO"}},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _write_jsonl(
        transcript_dir / "segments.jsonl",
        [{"segment_id": "seg-1", "start": 0, "end": 1, "speaker": "SPEAKER_01", "text": "Анатолий Сысоев: задача"}],
    )

    code = script.run(script.parse_args(["--meeting-dir", str(meeting_dir)]))

    assert code == 0
    assert (transcript_dir / "anonymized" / "anonymized_segments.jsonl").exists()
    rows = read_jsonl_rows(transcript_dir / "anonymized" / "anonymized_segments.jsonl")
    assert rows[0]["speaker"] == "SPEAKER_01"
    assert "Анатолий" not in rows[0]["text"]


def test_existing_output_requires_force(tmp_path: Path) -> None:
    script = _load_script()
    input_path = tmp_path / "segments.jsonl"
    _write_jsonl(input_path, [{"segment_id": "seg-1", "start": 0, "end": 1, "text": "text"}])
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "anonymized_segments.jsonl").write_text("existing", encoding="utf-8")

    with pytest.raises(script.AnonymizeTranscriptError, match="--force"):
        script.run(script.parse_args(["--input", str(input_path), "--out-dir", str(out_dir)]))


def test_terms_file_validation(tmp_path: Path) -> None:
    path = tmp_path / "terms.json"
    path.write_text(json.dumps({"unknown": ["value"]}), encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported"):
        load_terms_file(path)


def test_cli_stdout_does_not_print_absolute_paths(tmp_path: Path) -> None:
    script = _load_script()
    input_path = tmp_path / "segments.jsonl"
    _write_jsonl(input_path, [{"segment_id": "seg-1", "start": 0, "end": 1, "text": "text"}])
    out_dir = tmp_path / "out"
    stdout = StringIO()

    with redirect_stdout(stdout):
        code = script.run(script.parse_args(["--input", str(input_path), "--out-dir", str(out_dir)]))

    assert code == 0
    rendered = stdout.getvalue()
    assert str(tmp_path) not in rendered
    assert str(input_path) not in rendered
