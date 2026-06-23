from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.observability.review_queue import (  # noqa: E402
    VALID_LABELS,
    ReviewQueue,
    _safe_run_fields,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_runs(path: Path, runs: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in runs:
            fh.write(json.dumps(r) + "\n")


def _make_run(run_id: str, **kwargs) -> dict:
    return {
        "run_id": run_id,
        "created_at": "2026-06-20T10:00:00+00:00",
        "query": f"query for {run_id}",
        "mode": "hybrid",
        "top_k": 8,
        "status": "answered",
        "answer_preview": "some answer",
        "answer_chars": 42,
        "sources": [],
        "search_status": "ok",
        "guard_decision": "allow",
        "llm_model": "test-model",
        "llm_called": True,
        "llm_finish_reason": "stop",
        "validation_errors": [],
        "semantic_warnings": {},
        "prompt_sources": "SECRET INTERNAL PROMPT",
        "used_context_chars": 100,
        "max_context_chars": 9000,
        "latency_ms": 150,
        "manual_label": None,
        "manual_issue": None,
        **kwargs,
    }


# ---------------------------------------------------------------------------
# VALID_LABELS
# ---------------------------------------------------------------------------

def test_valid_labels_set() -> None:
    expected = {"correct", "false_refuse", "false_clarify", "bad_source", "needs_case", "off_topic_ok", "needs_review"}
    assert VALID_LABELS == expected


# ---------------------------------------------------------------------------
# _safe_run_fields
# ---------------------------------------------------------------------------

def test_safe_run_fields_removes_prompt_sources() -> None:
    run = _make_run("r1")
    out = _safe_run_fields(run)
    assert "prompt_sources" not in out


def test_safe_run_fields_removes_manual_label_and_issue() -> None:
    run = _make_run("r1", manual_label="old", manual_issue="old issue")
    out = _safe_run_fields(run)
    assert "manual_label" not in out
    assert "manual_issue" not in out


def test_safe_run_fields_strips_path_from_sources() -> None:
    run = _make_run("r1")
    run["sources"] = [
        {"source_ref": "S1", "title": "Doc", "path": "/secret/path/to/file.md", "score": 0.9}
    ]
    out = _safe_run_fields(run)
    assert out["sources"][0].get("path") is None
    assert out["sources"][0]["source_ref"] == "S1"


def test_safe_run_fields_keeps_safe_source_fields() -> None:
    run = _make_run("r1")
    run["sources"] = [{"source_ref": "S1", "title": "T", "score": 0.9, "bucket": "primary", "text_preview": "text"}]
    out = _safe_run_fields(run)
    s = out["sources"][0]
    assert s["title"] == "T"
    assert s["score"] == 0.9


# ---------------------------------------------------------------------------
# list_runs
# ---------------------------------------------------------------------------

def test_list_runs_empty_when_no_file(tmp_path: Path) -> None:
    q = ReviewQueue(runs_path=tmp_path / "runs.jsonl", labels_path=tmp_path / "labels.jsonl")
    assert q.list_runs() == []


def test_list_runs_returns_newest_first(tmp_path: Path) -> None:
    runs_path = tmp_path / "runs.jsonl"
    _write_runs(runs_path, [_make_run("r1"), _make_run("r2"), _make_run("r3")])
    q = ReviewQueue(runs_path=runs_path, labels_path=tmp_path / "labels.jsonl")
    result = q.list_runs(limit=10)
    assert [r["run_id"] for r in result] == ["r3", "r2", "r1"]


def test_list_runs_respects_limit(tmp_path: Path) -> None:
    runs_path = tmp_path / "runs.jsonl"
    _write_runs(runs_path, [_make_run(f"r{i}") for i in range(20)])
    q = ReviewQueue(runs_path=runs_path, labels_path=tmp_path / "labels.jsonl")
    result = q.list_runs(limit=5)
    assert len(result) == 5


def test_list_runs_filter_by_status(tmp_path: Path) -> None:
    runs_path = tmp_path / "runs.jsonl"
    _write_runs(runs_path, [
        _make_run("r1", status="answered"),
        _make_run("r2", status="refused"),
    ])
    q = ReviewQueue(runs_path=runs_path, labels_path=tmp_path / "labels.jsonl")
    result = q.list_runs(status="refused")
    assert len(result) == 1
    assert result[0]["run_id"] == "r2"


def test_list_runs_filter_by_guard_decision(tmp_path: Path) -> None:
    runs_path = tmp_path / "runs.jsonl"
    _write_runs(runs_path, [
        _make_run("r1", guard_decision="allow"),
        _make_run("r2", guard_decision="refuse"),
    ])
    q = ReviewQueue(runs_path=runs_path, labels_path=tmp_path / "labels.jsonl")
    result = q.list_runs(guard_decision="refuse")
    assert len(result) == 1
    assert result[0]["run_id"] == "r2"


def test_list_runs_injects_current_label(tmp_path: Path) -> None:
    runs_path = tmp_path / "runs.jsonl"
    labels_path = tmp_path / "labels.jsonl"
    _write_runs(runs_path, [_make_run("r1")])
    q = ReviewQueue(runs_path=runs_path, labels_path=labels_path)
    q.set_label("r1", "correct", labeled_by="admin")
    result = q.list_runs()
    assert result[0]["current_label"] == "correct"


def test_list_runs_filter_by_label(tmp_path: Path) -> None:
    runs_path = tmp_path / "runs.jsonl"
    labels_path = tmp_path / "labels.jsonl"
    _write_runs(runs_path, [_make_run("r1"), _make_run("r2")])
    q = ReviewQueue(runs_path=runs_path, labels_path=labels_path)
    q.set_label("r1", "correct", labeled_by="admin")
    result = q.list_runs(label="correct")
    assert len(result) == 1
    assert result[0]["run_id"] == "r1"


def test_list_runs_does_not_expose_prompt_internals(tmp_path: Path) -> None:
    runs_path = tmp_path / "runs.jsonl"
    _write_runs(runs_path, [_make_run("r1")])
    q = ReviewQueue(runs_path=runs_path, labels_path=tmp_path / "labels.jsonl")
    result = q.list_runs()
    assert "prompt_sources" not in result[0]


# ---------------------------------------------------------------------------
# set_label
# ---------------------------------------------------------------------------

def test_set_label_writes_to_sidecar(tmp_path: Path) -> None:
    q = ReviewQueue(runs_path=tmp_path / "runs.jsonl", labels_path=tmp_path / "labels.jsonl")
    rec = q.set_label("r1", "correct", manual_issue="typo", comment="good run", labeled_by="admin@x.com")
    assert rec["run_id"] == "r1"
    assert rec["label"] == "correct"
    assert rec["manual_issue"] == "typo"
    assert rec["comment"] == "good run"
    assert rec["labeled_by"] == "admin@x.com"
    assert "labeled_at" in rec
    lines = (tmp_path / "labels.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1


def test_set_label_latest_wins(tmp_path: Path) -> None:
    q = ReviewQueue(runs_path=tmp_path / "runs.jsonl", labels_path=tmp_path / "labels.jsonl")
    q.set_label("r1", "needs_review", labeled_by="u1")
    q.set_label("r1", "correct", labeled_by="u2")
    labels = q._load_labels()
    assert labels["r1"]["label"] == "correct"


def test_set_label_appends_not_overwrites(tmp_path: Path) -> None:
    q = ReviewQueue(runs_path=tmp_path / "runs.jsonl", labels_path=tmp_path / "labels.jsonl")
    q.set_label("r1", "correct", labeled_by="u1")
    q.set_label("r2", "bad_source", labeled_by="u1")
    lines = (tmp_path / "labels.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2


# ---------------------------------------------------------------------------
# export_joined
# ---------------------------------------------------------------------------

def test_export_joined_empty(tmp_path: Path) -> None:
    q = ReviewQueue(runs_path=tmp_path / "runs.jsonl", labels_path=tmp_path / "labels.jsonl")
    assert q.export_joined() == []


def test_export_joined_includes_unlabeled_runs(tmp_path: Path) -> None:
    runs_path = tmp_path / "runs.jsonl"
    _write_runs(runs_path, [_make_run("r1"), _make_run("r2")])
    q = ReviewQueue(runs_path=runs_path, labels_path=tmp_path / "labels.jsonl")
    result = q.export_joined()
    assert len(result) == 2
    assert all(r["current_label"] is None for r in result)


def test_export_joined_merges_label(tmp_path: Path) -> None:
    runs_path = tmp_path / "runs.jsonl"
    labels_path = tmp_path / "labels.jsonl"
    _write_runs(runs_path, [_make_run("r1"), _make_run("r2")])
    q = ReviewQueue(runs_path=runs_path, labels_path=labels_path)
    q.set_label("r2", "false_refuse", labeled_by="admin")
    result = q.export_joined()
    by_id = {r["run_id"]: r for r in result}
    assert by_id["r1"]["current_label"] is None
    assert by_id["r2"]["current_label"] == "false_refuse"


def test_export_joined_does_not_expose_prompt_internals(tmp_path: Path) -> None:
    runs_path = tmp_path / "runs.jsonl"
    _write_runs(runs_path, [_make_run("r1")])
    q = ReviewQueue(runs_path=runs_path, labels_path=tmp_path / "labels.jsonl")
    result = q.export_joined()
    assert "prompt_sources" not in result[0]


# ---------------------------------------------------------------------------
# Bounded read
# ---------------------------------------------------------------------------

def test_bounded_read_skips_partial_first_line(tmp_path: Path) -> None:
    runs_path = tmp_path / "runs.jsonl"
    runs = [_make_run(f"r{i}") for i in range(10)]
    _write_runs(runs_path, runs)
    # Full read returns all records with no parse errors.
    q_full = ReviewQueue(runs_path=runs_path, labels_path=tmp_path / "labels.jsonl")
    result_full = q_full._read_jsonl_tail(runs_path)
    assert len(result_full) == 10
    assert all(isinstance(r, dict) for r in result_full)
    # Bounded read returns only complete lines — no partial JSON.
    q_small = ReviewQueue(runs_path=runs_path, labels_path=tmp_path / "labels.jsonl", max_bytes=200)
    result_small = q_small._read_jsonl_tail(runs_path)
    assert all(isinstance(r, dict) for r in result_small)


def test_bounded_read_returns_empty_for_missing_file(tmp_path: Path) -> None:
    q = ReviewQueue(runs_path=tmp_path / "missing.jsonl", labels_path=tmp_path / "labels.jsonl")
    assert q._read_jsonl_tail(tmp_path / "missing.jsonl") == []
