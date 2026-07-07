from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from meeting_agent.evaluation.summary_benchmark import (  # noqa: E402
    evaluate_candidate_dir,
    load_benchmark_cases,
    write_report,
)


CASES_PATH = ROOT / "eval" / "cases" / "meeting_summary_synthetic.jsonl"
SCRIPT_PATH = ROOT / "scripts" / "44_evaluate_meeting_summary.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("meeting_summary_eval_44", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _source_ref(segment_index: int = 1) -> dict:
    return {
        "kind": "transcript_segment",
        "path": "transcript/segments.jsonl",
        "segment_index": segment_index,
        "start": 1.0,
        "timecode_start": "00:00:01",
        "chunk_id": "chunk-001",
    }


def _artifact(items: list[dict]) -> dict:
    return {
        "schema_version": 1,
        "meeting_id": "2026-01-15__synthetic",
        "generated_at": "2026-01-15T10:00:00+00:00",
        "items": items,
    }


def _write_case_artifacts(base: Path, case_id: str, *, grounded: bool = True) -> None:
    artifacts = base / case_id / "artifacts"
    artifacts.mkdir(parents=True)
    refs = [_source_ref()] if grounded else []
    review = {"confidence": 0.9, "needs_review": False}
    if case_id == "synthetic-support-handoff":
        summary = "Итоги: первая линия использует единый шаблон, нужен тестовый доступ."
        decisions = [
            {
                "decision_id": "DEC-001",
                "title": "Единый шаблон",
                "decision": "Использовать единый шаблон регистрации обращения.",
                "status": "accepted",
                "source_refs": refs,
                **review,
            }
        ]
        tasks = [
            {
                "task_id": "TASK-001",
                "title": "Подготовить инструкцию",
                "description": "Подготовить инструкцию для операторов до пятницы.",
                "status": "open",
                "source_refs": refs,
                **review,
            }
        ]
        risks = [
            {
                "risk_id": "RISK-001",
                "title": "Нет тестового доступа",
                "description": "Без тестового доступа операторы не проверят статусы заявок.",
                "impact": "medium",
                "probability": "medium",
                "status": "open",
                "source_refs": refs,
                **review,
            }
        ]
        questions = [
            {
                "question_id": "Q-001",
                "question": "Кто выдаёт тестовый доступ?",
                "status": "open",
                "source_refs": refs,
                **review,
            }
        ]
    else:
        summary = "Итоги: релиз переносится на среду из-за миграции данных; риск rollback больше часа."
        decisions = [
            {
                "decision_id": "DEC-001",
                "title": "Перенос релиза",
                "decision": "Перенести релиз на среду.",
                "status": "accepted",
                "source_refs": refs,
                **review,
            }
        ]
        tasks = [
            {
                "task_id": "TASK-001",
                "title": "Smoke checklist",
                "description": "Подготовить smoke checklist и отправить результаты.",
                "status": "open",
                "source_refs": refs,
                **review,
            }
        ]
        risks = [
            {
                "risk_id": "RISK-001",
                "title": "Rollback больше часа",
                "description": "Rollback занимает больше часа после обновления базы.",
                "impact": "high",
                "probability": "medium",
                "status": "open",
                "source_refs": refs,
                **review,
            }
        ]
        questions = [
            {
                "question_id": "Q-001",
                "question": "Кто принимает финальное решение по go или no-go?",
                "status": "open",
                "source_refs": refs,
                **review,
            }
        ]
    (artifacts / "summary.md").write_text(summary, encoding="utf-8")
    (artifacts / "protocol.md").write_text(summary, encoding="utf-8")
    (artifacts / "decisions.json").write_text(json.dumps(_artifact(decisions), ensure_ascii=False), encoding="utf-8")
    (artifacts / "tasks.json").write_text(json.dumps(_artifact(tasks), ensure_ascii=False), encoding="utf-8")
    (artifacts / "risks.json").write_text(json.dumps(_artifact(risks), ensure_ascii=False), encoding="utf-8")
    (artifacts / "open_questions.json").write_text(json.dumps(_artifact(questions), ensure_ascii=False), encoding="utf-8")


def test_load_public_synthetic_cases() -> None:
    cases = load_benchmark_cases(CASES_PATH)

    assert [case.case_id for case in cases] == [
        "synthetic-support-handoff",
        "synthetic-release-readiness",
    ]
    assert all(case.transcript for case in cases)


def test_evaluate_candidate_dir_passes_valid_artifacts(tmp_path: Path) -> None:
    cases = load_benchmark_cases(CASES_PATH)
    for case in cases:
        _write_case_artifacts(tmp_path, case.case_id)

    report = evaluate_candidate_dir(cases=cases, candidate_dir=tmp_path, provider="test", model="synthetic")

    assert report.passed is True
    assert report.score == 1.0
    assert all(result.score == 1.0 for result in report.results)


def test_missing_source_refs_fails_grounding_check(tmp_path: Path) -> None:
    cases = load_benchmark_cases(CASES_PATH)
    for case in cases:
        _write_case_artifacts(tmp_path, case.case_id, grounded=False)

    report = evaluate_candidate_dir(cases=cases, candidate_dir=tmp_path, provider="test", model="synthetic")

    assert report.passed is False
    assert any(
        check.name == "structured_source_refs" and not check.passed
        for result in report.results
        for check in result.checks
    )


def test_write_report_outputs_json_and_markdown(tmp_path: Path) -> None:
    cases = load_benchmark_cases(CASES_PATH)
    for case in cases:
        _write_case_artifacts(tmp_path / "candidate", case.case_id)
    report = evaluate_candidate_dir(cases=cases, candidate_dir=tmp_path / "candidate", provider="test")

    paths = write_report(report, tmp_path / "reports")

    assert json.loads(paths["json"].read_text(encoding="utf-8"))["score"] == 1.0
    assert "Meeting Summary Benchmark Report" in paths["markdown"].read_text(encoding="utf-8")


def test_cli_returns_zero_for_passing_candidate(tmp_path: Path) -> None:
    script = _load_script()
    cases = load_benchmark_cases(CASES_PATH)
    for case in cases:
        _write_case_artifacts(tmp_path / "candidate", case.case_id)

    code = script.run(
        script.parse_args(
            [
                "--cases",
                str(CASES_PATH),
                "--candidate-dir",
                str(tmp_path / "candidate"),
                "--provider",
                "test",
                "--model",
                "synthetic",
                "--out-dir",
                str(tmp_path / "reports"),
            ]
        )
    )

    assert code == 0
    assert (tmp_path / "reports" / "meeting_summary_benchmark_report.json").exists()
