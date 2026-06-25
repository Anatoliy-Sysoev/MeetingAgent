from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.evals.guard_cases import GuardCaseExporter  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in records:
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


def _make_label(run_id: str, label: str, **kwargs) -> dict:
    return {
        "run_id": run_id,
        "label": label,
        "manual_issue": None,
        "comment": None,
        "labeled_at": "2026-06-20T11:00:00+00:00",
        "labeled_by": "admin",
        **kwargs,
    }


def _make_exporter(tmp_path: Path, runs: list[dict], labels: list[dict]) -> GuardCaseExporter:
    runs_path = tmp_path / "chat_runs.jsonl"
    labels_path = tmp_path / "chat_run_labels.jsonl"
    _write_jsonl(runs_path, runs)
    _write_jsonl(labels_path, labels)
    return GuardCaseExporter(runs_path=runs_path, labels_path=labels_path)


# ---------------------------------------------------------------------------
# Label → case field mapping
# ---------------------------------------------------------------------------

def test_false_refuse_exports_allow(tmp_path: Path) -> None:
    exp = _make_exporter(tmp_path,
        runs=[_make_run("r1", guard_decision="refuse")],
        labels=[_make_label("r1", "false_refuse")],
    )
    cases = exp.export_cases()
    assert len(cases) == 1
    assert cases[0]["expected_guard_decision"] == "allow"
    assert cases[0]["case_type"] == "guard_false_refuse"
    assert cases[0]["needs_manual_expected"] is False


def test_false_clarify_exports_allow(tmp_path: Path) -> None:
    exp = _make_exporter(tmp_path,
        runs=[_make_run("r1", guard_decision="clarify")],
        labels=[_make_label("r1", "false_clarify")],
    )
    cases = exp.export_cases()
    assert cases[0]["expected_guard_decision"] == "allow"
    assert cases[0]["case_type"] == "guard_false_clarify"
    assert cases[0]["needs_manual_expected"] is False


def test_bad_source_preserves_observed_guard(tmp_path: Path) -> None:
    exp = _make_exporter(tmp_path,
        runs=[_make_run("r1", guard_decision="allow")],
        labels=[_make_label("r1", "bad_source")],
    )
    cases = exp.export_cases()
    assert cases[0]["expected_guard_decision"] == "allow"
    assert cases[0]["case_type"] == "retrieval_bad_source"
    assert cases[0]["needs_manual_expected"] is False


def test_off_topic_ok_needs_manual(tmp_path: Path) -> None:
    exp = _make_exporter(tmp_path,
        runs=[_make_run("r1")],
        labels=[_make_label("r1", "off_topic_ok")],
    )
    cases = exp.export_cases()
    assert cases[0]["expected_guard_decision"] is None
    assert cases[0]["needs_manual_expected"] is True


def test_needs_case_is_candidate(tmp_path: Path) -> None:
    exp = _make_exporter(tmp_path,
        runs=[_make_run("r1")],
        labels=[_make_label("r1", "needs_case")],
    )
    cases = exp.export_cases()
    assert cases[0]["case_type"] == "candidate"
    assert cases[0]["needs_manual_expected"] is True


def test_needs_review_needs_manual(tmp_path: Path) -> None:
    exp = _make_exporter(tmp_path,
        runs=[_make_run("r1")],
        labels=[_make_label("r1", "needs_review")],
    )
    cases = exp.export_cases()
    assert cases[0]["case_type"] == "needs_review"
    assert cases[0]["needs_manual_expected"] is True


# ---------------------------------------------------------------------------
# Filtering: correct
# ---------------------------------------------------------------------------

def test_skips_correct_by_default(tmp_path: Path) -> None:
    exp = _make_exporter(tmp_path,
        runs=[_make_run("r1")],
        labels=[_make_label("r1", "correct")],
    )
    cases = exp.export_cases()
    assert cases == []


def test_includes_correct_with_flag(tmp_path: Path) -> None:
    exp = _make_exporter(tmp_path,
        runs=[_make_run("r1", guard_decision="allow")],
        labels=[_make_label("r1", "correct")],
    )
    cases = exp.export_cases(include_correct=True)
    assert len(cases) == 1
    assert cases[0]["case_type"] == "positive_regression"
    assert cases[0]["expected_guard_decision"] == "allow"


# ---------------------------------------------------------------------------
# Filtering: unlabeled
# ---------------------------------------------------------------------------

def test_skips_unlabeled_runs(tmp_path: Path) -> None:
    exp = _make_exporter(tmp_path,
        runs=[_make_run("r1"), _make_run("r2")],
        labels=[_make_label("r1", "false_refuse")],
    )
    cases = exp.export_cases()
    assert len(cases) == 1
    assert cases[0]["run_id"] == "r1"


# ---------------------------------------------------------------------------
# Latest label wins
# ---------------------------------------------------------------------------

def test_latest_label_wins(tmp_path: Path) -> None:
    runs_path = tmp_path / "chat_runs.jsonl"
    labels_path = tmp_path / "chat_run_labels.jsonl"
    _write_jsonl(runs_path, [_make_run("r1")])
    _write_jsonl(labels_path, [
        _make_label("r1", "false_refuse"),
        _make_label("r1", "needs_review"),
    ])
    exp = GuardCaseExporter(runs_path=runs_path, labels_path=labels_path)
    cases = exp.export_cases()
    assert len(cases) == 1
    assert cases[0]["label"] == "needs_review"


# ---------------------------------------------------------------------------
# Field preservation: manual_issue and comment
# ---------------------------------------------------------------------------

def test_manual_issue_and_comment_preserved(tmp_path: Path) -> None:
    exp = _make_exporter(tmp_path,
        runs=[_make_run("r1")],
        labels=[_make_label("r1", "false_refuse", manual_issue="ticket-42", comment="needs fix")],
    )
    cases = exp.export_cases()
    assert cases[0]["manual_issue"] == "ticket-42"
    assert cases[0]["comment"] == "needs fix"


# ---------------------------------------------------------------------------
# Security: no prompt internals, no source paths
# ---------------------------------------------------------------------------

def test_prompt_sources_not_exported(tmp_path: Path) -> None:
    exp = _make_exporter(tmp_path,
        runs=[_make_run("r1", prompt_sources="TOP SECRET")],
        labels=[_make_label("r1", "false_refuse")],
    )
    cases = exp.export_cases()
    case_str = json.dumps(cases[0])
    assert "TOP SECRET" not in case_str
    assert "prompt_sources" not in cases[0]


def test_source_path_not_exported(tmp_path: Path) -> None:
    run = _make_run("r1")
    run["sources"] = [{"source_ref": "S1", "title": "Doc", "path": "/secret/path.md", "score": 0.9}]
    exp = _make_exporter(tmp_path, runs=[run], labels=[_make_label("r1", "false_refuse")])
    cases = exp.export_cases()
    assert "/secret/path.md" not in json.dumps(cases[0])


def test_source_refs_and_titles_exported_safely(tmp_path: Path) -> None:
    run = _make_run("r1")
    run["sources"] = [
        {"source_ref": "REF-1", "title": "Title One", "path": "/secret/path.md", "score": 0.9},
        {"source_ref": "REF-2", "title": "Title Two", "score": 0.7},
    ]
    exp = _make_exporter(tmp_path, runs=[run], labels=[_make_label("r1", "false_refuse")])
    cases = exp.export_cases()
    assert cases[0]["source_refs"] == ["REF-1", "REF-2"]
    assert cases[0]["source_titles"] == ["Title One", "Title Two"]


# ---------------------------------------------------------------------------
# Original runs file unchanged
# ---------------------------------------------------------------------------

def test_original_runs_file_unchanged(tmp_path: Path) -> None:
    runs_path = tmp_path / "chat_runs.jsonl"
    labels_path = tmp_path / "chat_run_labels.jsonl"
    _write_jsonl(runs_path, [_make_run("r1")])
    _write_jsonl(labels_path, [_make_label("r1", "false_refuse")])
    original_content = runs_path.read_bytes()

    out_path = tmp_path / "cases.jsonl"
    exp = GuardCaseExporter(runs_path=runs_path, labels_path=labels_path)
    exp.write_cases(out_path)

    assert runs_path.read_bytes() == original_content


# ---------------------------------------------------------------------------
# Limit
# ---------------------------------------------------------------------------

def test_limit_caps_output(tmp_path: Path) -> None:
    runs = [_make_run(f"r{i}") for i in range(10)]
    labels = [_make_label(f"r{i}", "false_refuse") for i in range(10)]
    exp = _make_exporter(tmp_path, runs=runs, labels=labels)
    cases = exp.export_cases(limit=3)
    assert len(cases) == 3


# ---------------------------------------------------------------------------
# filter_labels
# ---------------------------------------------------------------------------

def test_filter_labels_restricts_output(tmp_path: Path) -> None:
    exp = _make_exporter(tmp_path,
        runs=[_make_run("r1"), _make_run("r2")],
        labels=[_make_label("r1", "false_refuse"), _make_label("r2", "bad_source")],
    )
    cases = exp.export_cases(filter_labels=frozenset({"bad_source"}))
    assert len(cases) == 1
    assert cases[0]["run_id"] == "r2"


# ---------------------------------------------------------------------------
# write_cases summary
# ---------------------------------------------------------------------------

def test_write_cases_returns_summary(tmp_path: Path) -> None:
    exp = _make_exporter(tmp_path,
        runs=[_make_run("r1"), _make_run("r2")],
        labels=[_make_label("r1", "false_refuse")],
    )
    out_path = tmp_path / "cases.jsonl"
    summary = exp.write_cases(out_path)
    assert summary["runs_read"] == 2
    assert summary["labels_read"] == 1
    assert summary["cases_written"] == 1
    assert summary["skipped_unlabeled"] == 1
    assert out_path.exists()
    lines = out_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1


def test_write_cases_skipped_correct_count(tmp_path: Path) -> None:
    exp = _make_exporter(tmp_path,
        runs=[_make_run("r1"), _make_run("r2")],
        labels=[_make_label("r1", "false_refuse"), _make_label("r2", "correct")],
    )
    out_path = tmp_path / "cases.jsonl"
    summary = exp.write_cases(out_path)
    assert summary["skipped_correct"] == 1
    assert summary["cases_written"] == 1


# ---------------------------------------------------------------------------
# Bounded read
# ---------------------------------------------------------------------------

def test_bounded_read_enforced(tmp_path: Path) -> None:
    runs_path = tmp_path / "chat_runs.jsonl"
    runs = [_make_run(f"r{i}") for i in range(10)]
    _write_jsonl(runs_path, runs)
    exp = GuardCaseExporter(
        runs_path=runs_path,
        labels_path=tmp_path / "labels.jsonl",
        max_bytes=200,
    )
    result = exp._read_jsonl_tail(runs_path)
    # Only complete records (no partial JSON) — bounded read is enforced.
    assert all(isinstance(r, dict) for r in result)
    assert len(result) < 10  # bounded, so fewer records


def test_bounded_read_missing_file(tmp_path: Path) -> None:
    exp = GuardCaseExporter(
        runs_path=tmp_path / "missing.jsonl",
        labels_path=tmp_path / "labels.jsonl",
    )
    assert exp._read_jsonl_tail(tmp_path / "missing.jsonl") == []


# ---------------------------------------------------------------------------
# Invalid / malformed JSONL lines are skipped
# ---------------------------------------------------------------------------

def test_malformed_jsonl_lines_skipped(tmp_path: Path) -> None:
    runs_path = tmp_path / "chat_runs.jsonl"
    labels_path = tmp_path / "chat_run_labels.jsonl"
    with runs_path.open("w", encoding="utf-8") as fh:
        fh.write("NOT VALID JSON\n")
        fh.write(json.dumps(_make_run("r1")) + "\n")
        fh.write("{broken\n")
    _write_jsonl(labels_path, [_make_label("r1", "false_refuse")])
    exp = GuardCaseExporter(runs_path=runs_path, labels_path=labels_path)
    cases = exp.export_cases()
    assert len(cases) == 1
    assert cases[0]["run_id"] == "r1"
