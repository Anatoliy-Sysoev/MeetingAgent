from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.search.models import SearchRequest  # noqa: E402
from asu_june_bot.search.service import SearchService  # noqa: E402


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def run_query(question: dict[str, Any]) -> str:
    return f"Согласно ФТТ: {question.get('query')}"


def status_by_question(review_rows: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    statuses: dict[str, dict[str, str]] = defaultdict(dict)
    for row in review_rows:
        if row.get("category") == "integration_ftt":
            statuses[str(row.get("id"))][str(row.get("model"))] = str(row.get("status"))
    return statuses


def source_summary(source: dict[str, Any], bucket: str) -> dict[str, Any]:
    metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
    return {
        "bucket": bucket,
        "document_type": source.get("document_type") or metadata.get("document_type"),
        "path": source.get("document") or source.get("path") or metadata.get("relative_path"),
        "title": source.get("title") or metadata.get("title"),
        "section": source.get("section") or metadata.get("section"),
        "requirement_id": source.get("requirement_id") or metadata.get("requirement_id"),
        "score": source.get("score"),
    }


def suspected_failure_reason(types: list[str], status_values: list[str]) -> str:
    has_ftt = "ФТТ" in types
    if not has_ftt:
        return "ftt_missing_from_context"
    if any(status in {"no_answer", "validation_failed"} for status in status_values):
        return "ftt_present_but_answer_gate_failed"
    if types and types[0] != "ФТТ":
        return "ftt_present_but_not_top1"
    return "needs_manual_review"


def build_audit(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    questions = [row for row in read_jsonl(args.questions) if row.get("category") == "integration_ftt"]
    statuses = status_by_question(read_jsonl(args.review)) if args.review else {}
    service = SearchService(work_root=ROOT)
    audit_rows: list[dict[str, Any]] = []

    for question in questions:
        response = service.search(
            SearchRequest(
                query=run_query(question),
                mode=args.mode,
                top_k=args.top_k,
                chunks_path=str(args.chunks),
                index_dir=str(args.index),
                no_guard=True,
                include_diagnostics=True,
            )
        )
        context = response.context
        sources: list[dict[str, Any]] = []
        for bucket in ("primary_sources", "supporting_sources"):
            for item in context.get(bucket) or []:
                if isinstance(item, dict):
                    sources.append(source_summary(item, bucket))

        types = [str(source.get("document_type") or "unknown") for source in sources[:5]]
        model_statuses = statuses.get(str(question.get("id")), {})
        audit_rows.append(
            {
                "id": question.get("id"),
                "query": question.get("query"),
                "search_status": response.status,
                "model_statuses": model_statuses,
                "top1_document_type": types[0] if types else None,
                "top_sources_document_types": types,
                "has_ftt_source": "ФТТ" in types,
                "has_soi_ad_source": "СоИ AD" in types,
                "has_soi_nsi_source": "СоИ Справочники" in types,
                "primary_sources": [source for source in sources if source["bucket"] == "primary_sources"],
                "supporting_sources": [source for source in sources if source["bucket"] == "supporting_sources"],
                "suspected_failure_reason": suspected_failure_reason(types, list(model_statuses.values())),
            }
        )

    summary = {
        "rows": len(audit_rows),
        "top1_document_type": dict(Counter(str(row["top1_document_type"]) for row in audit_rows)),
        "suspected_failure_reason": dict(Counter(str(row["suspected_failure_reason"]) for row in audit_rows)),
        "has_ftt_source": sum(1 for row in audit_rows if row["has_ftt_source"]),
        "has_soi_ad_source": sum(1 for row in audit_rows if row["has_soi_ad_source"]),
        "has_soi_nsi_source": sum(1 for row in audit_rows if row["has_soi_nsi_source"]),
        "model_statuses": {
            model: dict(Counter(str(row["model_statuses"].get(model)) for row in audit_rows if model in row["model_statuses"]))
            for model in sorted({model for row in audit_rows for model in row["model_statuses"]})
        },
    }
    return audit_rows, summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit integration_ftt source selection through the current SearchService")
    parser.add_argument("--questions", required=True, type=Path)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--chunks", required=True, type=Path)
    parser.add_argument("--index", required=True, type=Path)
    parser.add_argument("--out-jsonl", required=True, type=Path)
    parser.add_argument("--out-summary", required=True, type=Path)
    parser.add_argument("--mode", default="hybrid", choices=["hybrid", "bm25", "vector"])
    parser.add_argument("--top-k", default=8, type=int)
    args = parser.parse_args()

    rows, summary = build_audit(args)
    write_jsonl(args.out_jsonl, rows)
    args.out_summary.parent.mkdir(parents=True, exist_ok=True)
    args.out_summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
