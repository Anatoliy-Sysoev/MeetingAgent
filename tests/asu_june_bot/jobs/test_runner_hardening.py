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
    detail = "failed at C:\\Users\\Secret\\Documents\\meeting.json and /home/user/private.txt"

    result = _public_error_detail(detail, meeting_dir=tmp_path)

    assert "C:\\Users\\Secret" not in result
    assert "/home/user" not in result
    assert result.count("<path>") == 2


def test_last_error_writes_and_clears_atomically(tmp_path: Path) -> None:
    meeting_dir = tmp_path / "mtg"
    meeting_dir.mkdir()
    card_path = meeting_dir / "meeting.json"
    card_path.write_text(json.dumps({"meeting_id": "mtg"}, ensure_ascii=False), encoding="utf-8")

    _write_last_error(meeting_dir, stage="chunk", job_id="job-1", exit_code=1)
    written = json.loads(card_path.read_text(encoding="utf-8"))
    assert written["last_error"]["stage"] == "chunk"
    assert written["last_error"]["job_id"] == "job-1"
    assert not list(meeting_dir.glob(".meeting.json.*.tmp"))

    _clear_last_error(meeting_dir, stage="chunk")
    cleared = json.loads(card_path.read_text(encoding="utf-8"))
    assert "last_error" not in cleared
    assert not list(meeting_dir.glob(".meeting.json.*.tmp"))
