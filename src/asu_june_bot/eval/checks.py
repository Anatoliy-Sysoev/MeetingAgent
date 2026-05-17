from __future__ import annotations

import re

from asu_june_bot.chat.models import ChatResponse

from .models import CheckResult, EvalCase

SOURCE_REF_RE = re.compile(r"\[S\d+")


def run_checks(case: EvalCase, response: ChatResponse) -> list[CheckResult]:
    return [
        check_status(case, response),
        check_llm_called(case, response),
        check_must_include(case, response),
        check_must_not_include(case, response),
        check_citations(case, response),
        check_min_sources(case, response),
        check_source_titles(case, response),
    ]


def check_status(case: EvalCase, response: ChatResponse) -> CheckResult:
    if response.status == case.expected_status:
        return CheckResult("status", True)
    return CheckResult("status", False, f"expected={case.expected_status}, actual={response.status}")


def check_llm_called(case: EvalCase, response: ChatResponse) -> CheckResult:
    actual = bool((response.diagnostics or {}).get("llm_called"))
    if actual == case.expected_llm_called:
        return CheckResult("llm_called", True)
    return CheckResult("llm_called", False, f"expected={case.expected_llm_called}, actual={actual}")


def check_must_include(case: EvalCase, response: ChatResponse) -> CheckResult:
    if not case.must_include:
        return CheckResult("must_include", True, "skipped")
    answer = (response.answer or "").lower()
    missing = [item for item in case.must_include if item.lower() not in answer]
    if not missing:
        return CheckResult("must_include", True)
    return CheckResult("must_include", False, "missing: " + ", ".join(missing))


def check_must_not_include(case: EvalCase, response: ChatResponse) -> CheckResult:
    if not case.must_not_include:
        return CheckResult("must_not_include", True, "skipped")
    answer = (response.answer or "").lower()
    found = [item for item in case.must_not_include if item.lower() in answer]
    if not found:
        return CheckResult("must_not_include", True)
    return CheckResult("must_not_include", False, "forbidden: " + ", ".join(found))


def check_citations(case: EvalCase, response: ChatResponse) -> CheckResult:
    if not case.expected_citation_required:
        return CheckResult("citations", True, "skipped")
    answer = response.answer or ""
    if SOURCE_REF_RE.search(answer):
        return CheckResult("citations", True)
    return CheckResult("citations", False, "expected citation [Sx]")


def check_min_sources(case: EvalCase, response: ChatResponse) -> CheckResult:
    if case.expected_min_sources is None:
        return CheckResult("min_sources", True, "skipped")
    actual = len(response.sources or [])
    if actual >= int(case.expected_min_sources):
        return CheckResult("min_sources", True, f"actual={actual}")
    return CheckResult("min_sources", False, f"expected>={case.expected_min_sources}, actual={actual}")


def _source_search_text(source: object) -> str:
    fields = [
        getattr(source, "title", None),
        getattr(source, "path", None),
        getattr(source, "section", None),
        getattr(source, "requirement_id", None),
        getattr(source, "source_type", None),
        getattr(source, "text_preview", None),
    ]
    return " ".join(str(value or "") for value in fields).lower()


def check_source_titles(case: EvalCase, response: ChatResponse) -> CheckResult:
    if not case.expected_source_title_contains:
        return CheckResult("source_titles", True, "skipped")
    source_texts = [_source_search_text(source) for source in response.sources]
    missing = []
    for expected in case.expected_source_title_contains:
        expected_lower = expected.lower()
        if not any(expected_lower in text for text in source_texts):
            missing.append(expected)
    if not missing:
        return CheckResult("source_titles", True)
    return CheckResult("source_titles", False, "missing source text contains: " + ", ".join(missing))
