from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def load_script(name: str):
    path = ROOT / "scripts" / "diagnostics" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_check_index_coverage_matches_document_type_and_terms() -> None:
    module = load_script("check_index_coverage")
    chunks = [
        {
            "chunk_id": "c1",
            "document_type": "ФТТ",
            "relative_path": "ФТТ.docx",
            "text": "Требование 1.1 относится к Этап 3 (ФТ3).",
            "requirement_id": "1.1",
            "table_id": "Table 8",
        }
    ]
    gold = [
        {
            "id": "Q030",
            "required_sources": [{"document_type": "ФТТ", "requirement_id": "1.1"}],
            "expected_answer_facts": ["Этап 3", "ФТ3"],
            "negative_facts": ["Этап 1", "ФТ1"],
        }
    ]

    report = module.build_report(gold, chunks)

    assert report["failed"] == 0
    assert report["ok"] == 1


def test_check_index_coverage_reports_missing_terms() -> None:
    module = load_script("check_index_coverage")
    chunks = [{"chunk_id": "c1", "document_type": "ФТТ", "text": "Требование 1.1"}]
    gold = [{"id": "Q030", "required_sources": [{"document_type": "ФТТ"}], "expected_answer_facts": ["Этап 3"]}]

    report = module.build_report(gold, chunks)

    assert report["failed"] == 1
    assert report["failed_ids"] == ["Q030"]
    assert report["results"][0]["missing_terms"] == ["Этап 3"]


def test_pivot_manual_review_counts_by_model_status_and_verdict() -> None:
    module = load_script("pivot_manual_review")
    rows = [
        {"model": "m4", "category": "ftt", "status": "answered", "review_verdict": "ok"},
        {"model": "m4", "category": "ftt", "status": "no_answer", "review_verdict": "low_score"},
        {"model": "m9", "category": "cta", "status": "answered", "review_verdict": "ok"},
    ]

    pivot = module.build_pivot(rows)

    assert pivot["rows"] == 3
    assert pivot["by_model"] == {"m4": 2, "m9": 1}
    assert pivot["by_status"] == {"answered": 2, "no_answer": 1}
    assert pivot["review_verdict_by_category"]["ftt"] == {"low_score": 1, "ok": 1}
