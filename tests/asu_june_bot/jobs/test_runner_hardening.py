from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.jobs.runner import (  # noqa: E402
    _merge_preflight,
    _chunk_preflight,
    _enrich_preflight,
    _index_preflight,
    _analyze_preflight,
    _path_variants,
    _public_error_detail,
    _redact_paths,
    _write_json_atomic,
    _write_last_error,
    _clear_last_error,
)


def make_meeting(tmp_path: Path, artifacts: object) -> Path:
    meeting_dir = tmp_path / "mtg"
    meeting_dir.mkdir()
    card = {
        "meeting_id": "mtg",
        "artifacts": artifacts,
    }
    (meeting_dir / "meeting.json").write_text(json.dumps(card), encoding="utf-8")
    return meeting_dir


# ---------------------------------------------------------------------------
# Bug 1: preflight does not crash on malformed artifacts
# ---------------------------------------------------------------------------

def test_runner_preflight_malformed_artifacts_list_does_not_raise(tmp_path):
    meeting_dir = make_meeting(tmp_path, ["foo", "bar"])
    result = _merge_preflight(meeting_dir)
    assert isinstance(result, str)


def test_runner_preflight_malformed_artifacts_string_does_not_raise(tmp_path):
    meeting_dir = make_meeting(tmp_path, "bad-string")
    result = _chunk_preflight(meeting_dir)
    assert isinstance(result, str)


def test_runner_preflight_malformed_artifacts_null_does_not_raise(tmp_path):
    meeting_dir = make_meeting(tmp_path, None)
    result = _enrich_preflight(meeting_dir)
    assert isinstance(result, str)


def test_runner_index_preflight_malformed_artifacts_string_does_not_raise(tmp_path):
    meeting_dir = make_meeting(tmp_path, "bad-string")
    result = _index_preflight(meeting_dir)
    assert isinstance(result, str)
    assert "enriched_chunks.jsonl not found" in result


def test_runner_analyze_preflight_malformed_artifacts_list_does_not_raise(tmp_path):
    meeting_dir = make_meeting(tmp_path, ["bad"])
    result = _analyze_preflight(meeting_dir)
    assert isinstance(result, str)
    assert "enriched_chunks.jsonl not found" in result


# ---------------------------------------------------------------------------
# Bug 3: path redaction covers slash/case variants
# ---------------------------------------------------------------------------

def test_stderr_redacts_native_path(tmp_path):
    root = tmp_path / "work"
    root.mkdir()
    line = f"Error reading {root}/meeting.json"
    result = _redact_paths(line, [root])
    assert str(root) not in result
    assert "<path>" in result


def test_stderr_redacts_slash_normalized_path(tmp_path):
    root = tmp_path / "work"
    root.mkdir()
    posix_str = str(root).replace("\\", "/")
    line = f"Error reading {posix_str}/meeting.json"
    result = _redact_paths(line, [root])
    assert posix_str not in result
    assert "<path>" in result


def test_stderr_redacts_uppercase_path_variant(tmp_path):
    root = tmp_path / "work"
    root.mkdir()
    upper_str = str(root).upper()
    line = f"Error reading {upper_str}\\meeting.json"
    result = _redact_paths(line, [root])
    assert upper_str not in result
    assert "<path>" in result


def test_stderr_redacts_mixed_separator_path(tmp_path):
    root = tmp_path / "work"
    root.mkdir()
    mixed = str(root).replace("/", "\\")
    line = f"path: {mixed}\\meeting.json"
    result = _redact_paths(line, [root])
    assert mixed not in result
    assert "<path>" in result


# ---------------------------------------------------------------------------
# _path_variants sanity checks
# ---------------------------------------------------------------------------

def test_path_variants_includes_posix_and_backslash(tmp_path):
    root = tmp_path / "mydir"
    root.mkdir()
    variants = _path_variants(root)
    native = str(root)
    posix = native.replace("\\", "/")
    assert posix in variants
    assert native in variants


def test_public_error_detail_redacts_unknown_absolute_paths(tmp_path: Path) -> None:
    detail = "failed at C:\\Users\\Secret Person\\Documents\\meeting.json"

    result = _public_error_detail(detail, meeting_dir=tmp_path)

    assert "C:\\Users\\Secret" not in result
    assert "Documents" not in result
    assert result.endswith("<path>")


def test_public_error_detail_is_bounded() -> None:
    result = _public_error_detail("x" * 1000)

    assert len(result) == 500
    assert result.endswith("...")


def test_atomic_json_replace_failure_preserves_original(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "meeting.json"
    original = '{"meeting_id":"original"}\n'
    path.write_text(original, encoding="utf-8", newline="")

    def fail_replace(_source: Path, _target: Path) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr("asu_june_bot.jobs.runner.os.replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        _write_json_atomic(path, {"meeting_id": "replacement"})

    assert path.read_text(encoding="utf-8") == original
    assert not list(tmp_path.glob(".meeting.json.*.tmp"))


def test_last_error_writes_and_clears_without_partial_files(tmp_path: Path) -> None:
    meeting_dir = tmp_path / "mtg"
    meeting_dir.mkdir()
    card_path = meeting_dir / "meeting.json"
    card_path.write_text('{"meeting_id":"mtg"}\n', encoding="utf-8", newline="")

    _write_last_error(meeting_dir, stage="chunk", job_id="job-1", exit_code=1)
    written = json.loads(card_path.read_text(encoding="utf-8"))
    assert written["last_error"]["stage"] == "chunk"
    assert written["last_error"]["job_id"] == "job-1"
    assert not list(meeting_dir.glob(".meeting.json.*.tmp"))

    _clear_last_error(meeting_dir, stage="chunk")
    cleared = json.loads(card_path.read_text(encoding="utf-8"))
    assert "last_error" not in cleared
    assert not list(meeting_dir.glob(".meeting.json.*.tmp"))
