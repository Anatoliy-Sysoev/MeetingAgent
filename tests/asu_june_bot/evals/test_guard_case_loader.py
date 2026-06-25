from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.evals.guard_case_loader import (  # noqa: E402
    GuardCaseValidationError,
    GuardRegressionCase,
    case_contains_forbidden_keys,
    load_guard_cases,
    validate_guard_case_payload,
)

FIXTURES = ROOT / "tests" / "fixtures" / "evals"
SAMPLE_FIXTURE = FIXTURES / "guard_v2_cases.sample.jsonl"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_payload(**overrides) -> dict:
    base = {
        "case_id": "run_r1",
        "run_id": "r1",
        "query": "What documents do I need?",
        "label": "false_refuse",
        "case_type": "guard_false_refuse",
        "observed_guard_decision": "refuse",
        "expected_guard_decision": "allow",
        "needs_manual_expected": False,
        "observed_status": "refused",
        "metadata": {"mode": "hybrid", "top_k": 8},
    }
    base.update(overrides)
    return base


def _write_jsonl(path: Path, lines: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for item in lines:
            fh.write((item if isinstance(item, str) else json.dumps(item)) + "\n")


# ---------------------------------------------------------------------------
# validate_guard_case_payload
# ---------------------------------------------------------------------------

def test_validate_valid_payload() -> None:
    case = validate_guard_case_payload(_valid_payload())
    assert isinstance(case, GuardRegressionCase)
    assert case.case_id == "run_r1"
    assert case.label == "false_refuse"
    assert case.needs_manual_expected is False


def test_validate_rejects_missing_required_field() -> None:
    payload = _valid_payload()
    del payload["query"]
    with pytest.raises(GuardCaseValidationError, match="Missing required fields"):
        validate_guard_case_payload(payload)


def test_validate_rejects_unknown_label() -> None:
    with pytest.raises(GuardCaseValidationError, match="Unknown label"):
        validate_guard_case_payload(_valid_payload(label="not_a_label"))


def test_validate_rejects_unknown_case_type() -> None:
    with pytest.raises(GuardCaseValidationError, match="Unknown case_type"):
        validate_guard_case_payload(_valid_payload(case_type="not_a_case_type"))


def test_validate_rejects_non_bool_needs_manual_expected() -> None:
    with pytest.raises(GuardCaseValidationError, match="needs_manual_expected must be bool"):
        validate_guard_case_payload(_valid_payload(needs_manual_expected="yes"))


def test_validate_rejects_non_dict_metadata() -> None:
    with pytest.raises(GuardCaseValidationError, match="metadata must be a dict"):
        validate_guard_case_payload(_valid_payload(metadata="bad"))


def test_validate_optional_fields_default() -> None:
    case = validate_guard_case_payload(_valid_payload())
    assert case.manual_issue is None
    assert case.comment is None
    assert case.source_refs == []
    assert case.source_titles == []
    assert case.answer_preview is None
    assert case.created_at is None


def test_validate_optional_fields_populated() -> None:
    case = validate_guard_case_payload(_valid_payload(
        manual_issue="ticket-7",
        comment="looks wrong",
        source_refs=["S1"],
        source_titles=["Doc One"],
        answer_preview="The answer is 42.",
        created_at="2026-06-20T10:00:00+00:00",
    ))
    assert case.manual_issue == "ticket-7"
    assert case.source_refs == ["S1"]
    assert case.created_at == "2026-06-20T10:00:00+00:00"


# ---------------------------------------------------------------------------
# case_contains_forbidden_keys
# ---------------------------------------------------------------------------

def test_forbidden_key_catches_prompt_sources() -> None:
    payload = _valid_payload()
    payload["prompt_sources"] = "SECRET"
    found = case_contains_forbidden_keys(payload)
    assert "prompt_sources" in found


def test_forbidden_key_catches_manual_label() -> None:
    payload = _valid_payload()
    payload["manual_label"] = "old_label"
    found = case_contains_forbidden_keys(payload)
    assert "manual_label" in found


def test_forbidden_key_catches_nested_source_path() -> None:
    payload = _valid_payload()
    payload["sources"] = [{"source_ref": "S1", "path": "/secret/path.md"}]
    found = case_contains_forbidden_keys(payload)
    assert any("path" in k for k in found)


def test_forbidden_key_clean_payload_returns_empty() -> None:
    assert case_contains_forbidden_keys(_valid_payload()) == []


# ---------------------------------------------------------------------------
# load_guard_cases — strict mode
# ---------------------------------------------------------------------------

def test_load_strict_valid_file(tmp_path: Path) -> None:
    p = tmp_path / "cases.jsonl"
    _write_jsonl(p, [_valid_payload()])
    cases = load_guard_cases(p)
    assert len(cases) == 1
    assert cases[0].run_id == "r1"


def test_load_strict_skips_blank_lines(tmp_path: Path) -> None:
    p = tmp_path / "cases.jsonl"
    _write_jsonl(p, ["", _valid_payload(), "   "])
    cases = load_guard_cases(p)
    assert len(cases) == 1


def test_load_strict_raises_on_malformed_json(tmp_path: Path) -> None:
    p = tmp_path / "cases.jsonl"
    _write_jsonl(p, [_valid_payload(), "NOT JSON"])
    with pytest.raises(GuardCaseValidationError, match="Malformed JSON"):
        load_guard_cases(p, strict=True)


def test_load_strict_raises_on_validation_error(tmp_path: Path) -> None:
    bad = _valid_payload(label="INVALID_LABEL")
    p = tmp_path / "cases.jsonl"
    _write_jsonl(p, [bad])
    with pytest.raises(GuardCaseValidationError, match="Unknown label"):
        load_guard_cases(p, strict=True)


def test_load_strict_raises_on_non_dict_line(tmp_path: Path) -> None:
    p = tmp_path / "cases.jsonl"
    _write_jsonl(p, ['["list", "not", "dict"]'])
    with pytest.raises(GuardCaseValidationError, match="expected JSON object"):
        load_guard_cases(p, strict=True)


def test_load_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_guard_cases(tmp_path / "missing.jsonl")


# ---------------------------------------------------------------------------
# load_guard_cases — non-strict mode
# ---------------------------------------------------------------------------

def test_load_non_strict_skips_malformed_json(tmp_path: Path) -> None:
    p = tmp_path / "cases.jsonl"
    _write_jsonl(p, [_valid_payload(), "NOT JSON", _valid_payload(case_id="run_r2", run_id="r2")])
    cases = load_guard_cases(p, strict=False)
    assert len(cases) == 2


def test_load_non_strict_skips_invalid_payload(tmp_path: Path) -> None:
    bad = _valid_payload(label="INVALID_LABEL")
    p = tmp_path / "cases.jsonl"
    _write_jsonl(p, [_valid_payload(), bad])
    cases = load_guard_cases(p, strict=False)
    assert len(cases) == 1


def test_load_non_strict_skips_non_dict_line(tmp_path: Path) -> None:
    p = tmp_path / "cases.jsonl"
    _write_jsonl(p, ['42', _valid_payload()])
    cases = load_guard_cases(p, strict=False)
    assert len(cases) == 1


# ---------------------------------------------------------------------------
# Sample fixture
# ---------------------------------------------------------------------------

def test_sample_fixture_loads() -> None:
    cases = load_guard_cases(SAMPLE_FIXTURE)
    assert len(cases) == 7


def test_sample_fixture_all_required_fields() -> None:
    cases = load_guard_cases(SAMPLE_FIXTURE)
    for c in cases:
        assert c.case_id
        assert c.run_id
        assert c.query
        assert c.label
        assert c.case_type
        assert isinstance(c.needs_manual_expected, bool)
        assert isinstance(c.metadata, dict)


def test_sample_fixture_no_forbidden_keys() -> None:
    with SAMPLE_FIXTURE.open(encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped:
                continue
            payload = json.loads(stripped)
            found = case_contains_forbidden_keys(payload)
            assert found == [], f"Forbidden keys {found} in case {payload.get('case_id')}"


def test_sample_fixture_no_filesystem_paths_in_values(tmp_path: Path) -> None:
    raw = SAMPLE_FIXTURE.read_text(encoding="utf-8")
    # Heuristic: no absolute path-like strings (Unix or Windows).
    import re
    matches = re.findall(r'["\s](/[a-zA-Z0-9_/.-]{5,}|[A-Za-z]:\\[^"\\]+)', raw)
    assert matches == [], f"Possible filesystem paths found: {matches}"


def test_sample_fixture_covers_all_labels() -> None:
    cases = load_guard_cases(SAMPLE_FIXTURE)
    labels = {c.label for c in cases}
    expected = {"false_refuse", "false_clarify", "bad_source", "off_topic_ok",
                "needs_case", "needs_review", "correct"}
    assert labels == expected


def test_sample_fixture_false_refuse_expects_allow() -> None:
    cases = load_guard_cases(SAMPLE_FIXTURE)
    fr = [c for c in cases if c.label == "false_refuse"]
    assert fr and all(c.expected_guard_decision == "allow" for c in fr)


def test_sample_fixture_false_clarify_expects_allow() -> None:
    cases = load_guard_cases(SAMPLE_FIXTURE)
    fc = [c for c in cases if c.label == "false_clarify"]
    assert fc and all(c.expected_guard_decision == "allow" for c in fc)


def test_sample_fixture_off_topic_ok_is_manual() -> None:
    cases = load_guard_cases(SAMPLE_FIXTURE)
    ot = [c for c in cases if c.label == "off_topic_ok"]
    assert ot and all(c.expected_guard_decision is None and c.needs_manual_expected for c in ot)


def test_sample_fixture_needs_case_is_manual() -> None:
    cases = load_guard_cases(SAMPLE_FIXTURE)
    nc = [c for c in cases if c.label == "needs_case"]
    assert nc and all(c.expected_guard_decision is None and c.needs_manual_expected for c in nc)


def test_sample_fixture_needs_review_is_manual() -> None:
    cases = load_guard_cases(SAMPLE_FIXTURE)
    nr = [c for c in cases if c.label == "needs_review"]
    assert nr and all(c.expected_guard_decision is None and c.needs_manual_expected for c in nr)


def test_sample_fixture_correct_is_positive_regression() -> None:
    cases = load_guard_cases(SAMPLE_FIXTURE)
    co = [c for c in cases if c.label == "correct"]
    assert co and all(c.case_type == "positive_regression" for c in co)
