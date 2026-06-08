from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as f:
        for line_no, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def norm(text: Any) -> str:
    return " ".join(str(text or "").lower().replace("ё", "е").split())


def contains_no_answer(text: str) -> bool:
    normalized = norm(text)
    return "данных недостаточно" in normalized or "недостаточно для ответа" in normalized


def hit_groups(row: dict[str, Any], field: str) -> bool | None:
    value = row.get(field)
    if isinstance(value, bool) or value is None:
        return value
    return None


def answer_has_expected(row: dict[str, Any]) -> bool:
    answer = norm(row.get("answer_preview"))
    groups = row.get("required_anchor_groups") or []
    if not groups:
        return True
    for group in groups:
        alternatives = [norm(item) for item in group if str(item or "").strip()]
        if alternatives and not any(item in answer for item in alternatives):
            return False
    return True


def classify(row: dict[str, Any]) -> tuple[str, str]:
    status = str(row.get("status") or "")
    answer = str(row.get("answer_preview") or "")
    has_corpus = hit_groups(row, "has_required_terms_in_corpus")
    has_context = hit_groups(row, "has_required_terms_in_context")
    has_prompt = hit_groups(row, "has_required_terms_in_prompt")
    llm_called = row.get("llm_called")

    if status == "refused":
        return "incorrect", "false_refusal"
    if status == "clarify":
        return "incorrect", "false_clarify"
    if status == "validation_failed":
        return "incorrect", "validation_bug"
    if status == "truncated":
        return "incorrect", "truncated"
    if status in {"llm_error", "llm_empty_response", "search_error"}:
        return "incorrect", status
    if not has_corpus:
        return "unverified", "corpus_missing"
    if not has_context:
        return "incorrect", "context_missing_required_anchor"
    if not has_prompt:
        return "incorrect", "prompt_missing_required_anchor"
    if status == "no_answer" or contains_no_answer(answer):
        return "incorrect", "false_no_answer"
    if status == "answered" and answer_has_expected(row):
        if llm_called is False:
            return "correct", "deterministic_answer"
        return "correct", "answered_with_required_anchors"
    if status == "answered":
        return "partial", "answered_missing_anchor_in_preview"
    return "unverified", "manual_review_needed"


def build_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        verdict, issue = classify(row)
        enriched = dict(row)
        enriched["review_verdict"] = verdict
        enriched["review_issue"] = issue
        enriched["review_comment"] = (
            f"Auto-graded from anchor audit: status={row.get('status')}, "
            f"corpus={row.get('has_required_terms_in_corpus')}, "
            f"context={row.get('has_required_terms_in_context')}, "
            f"prompt={row.get('has_required_terms_in_prompt')}, "
            f"llm_called={row.get('llm_called')}."
        )
        out.append(enriched)
    return out


def build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_verdict = Counter(str(row.get("review_verdict")) for row in rows)
    by_issue = Counter(str(row.get("review_issue")) for row in rows)
    by_status = Counter(str(row.get("status")) for row in rows)
    by_category: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        by_category[str(row.get("category") or "unknown")][str(row.get("review_verdict"))] += 1
    return {
        "rows": len(rows),
        "by_status": dict(sorted(by_status.items())),
        "by_review_verdict": dict(sorted(by_verdict.items())),
        "by_review_issue": dict(sorted(by_issue.items())),
        "review_verdict_by_category": {key: dict(sorted(counter.items())) for key, counter in sorted(by_category.items())},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Auto-grade anchor audit JSONL into a pivot-ready review JSONL.")
    parser.add_argument("--audit", required=True, type=Path)
    parser.add_argument("--out-review", required=True, type=Path)
    parser.add_argument("--out-summary", type=Path)
    args = parser.parse_args()

    rows = build_rows(read_jsonl(args.audit))
    write_jsonl(args.out_review, rows)
    summary = build_summary(rows)
    if args.out_summary:
        args.out_summary.parent.mkdir(parents=True, exist_ok=True)
        args.out_summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
